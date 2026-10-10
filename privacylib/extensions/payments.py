"""
privacylib/extensions/payments.py — Gateway de Pagamento das Extensões.

Reaproveita a integração Mercado Pago do projeto (mesmo padrão de
functions/plan_payments.py), adaptada para KITS de extensões e com suporte a
PIX, cartão de crédito e débito.

Documentos MongoDB:
- ext_payment_config    : {mercado_pago, metodos, log_channel_id}  (conta do dono)
- ext_pending_payments  : {payments: {payment_id: {...}}}
- ext_history           : {payments: [...]}  (máx. 500)

A conta de recebimento aqui é a do DONO do bot (marketplace), isolada da conta
da loja de cada servidor.

_Requirements: 14.1, 14.3
"""
import time
from typing import Optional

import aiohttp

from privacylib.db.store import database as db
from privacylib.extensions import catalog, pricing, subscriptions

_CFG = "ext_payment_config"
_PENDING = "ext_pending_payments"
_HISTORY = "ext_history"

_MP_BASE = "https://api.mercadopago.com"
_UA = "DiscordBot (https://privacymods.bot, 1.0)"


# ─── Configuração da conta do marketplace (só dono — Req 11.2) ───────────────
def get_config() -> dict:
    data = db.get_document(_CFG)
    if not isinstance(data, dict):
        data = {}
    data.setdefault("mercado_pago", {"access_token": None})
    data.setdefault("metodos", {"pix": True, "credito": True, "debito": True})
    data.setdefault("log_channel_id", None)
    return data


def save_access_token(access_token: str, user_id: str = None):
    data = get_config()
    data["mercado_pago"] = {
        "access_token": (access_token or "").strip() or None,
        "configured_at": int(time.time()),
        "configured_by": user_id,
    }
    db.save_document(_CFG, data)


def set_metodos(pix: bool = None, credito: bool = None, debito: bool = None):
    data = get_config()
    m = data["metodos"]
    if pix is not None:
        m["pix"] = bool(pix)
    if credito is not None:
        m["credito"] = bool(credito)
    if debito is not None:
        m["debito"] = bool(debito)
    data["metodos"] = m
    db.save_document(_CFG, data)


def metodos_habilitados() -> dict:
    return get_config().get("metodos", {"pix": True, "credito": True, "debito": True})


def set_log_channel(channel_id):
    data = get_config()
    data["log_channel_id"] = int(channel_id) if channel_id else None
    db.save_document(_CFG, data)


def get_log_channel() -> Optional[int]:
    return get_config().get("log_channel_id")


def configurada() -> bool:
    """True se há access token do Mercado Pago configurado."""
    token = get_config().get("mercado_pago", {}).get("access_token")
    return bool(token and token.strip())


def _token() -> Optional[str]:
    return get_config().get("mercado_pago", {}).get("access_token")


# ─── Pendentes / Histórico ───────────────────────────────────────────────────
def _save_pending(payment_id: str, record: dict):
    data = db.get_document(_PENDING)
    if not isinstance(data, dict):
        data = {"payments": {}}
    data.setdefault("payments", {})[payment_id] = record
    db.save_document(_PENDING, data)


def _get_pending(payment_id: str) -> Optional[dict]:
    data = db.get_document(_PENDING)
    if not isinstance(data, dict):
        return None
    return data.get("payments", {}).get(payment_id)


def _remove_pending(payment_id: str):
    data = db.get_document(_PENDING)
    if not isinstance(data, dict):
        return
    data.get("payments", {}).pop(payment_id, None)
    db.save_document(_PENDING, data)


def listar_pendentes() -> list:
    data = db.get_document(_PENDING)
    if not isinstance(data, dict):
        return []
    return list(data.get("payments", {}).values())


def _record_history(entry: dict):
    data = db.get_document(_HISTORY)
    if not isinstance(data, dict):
        data = {"payments": []}
    payments = data.get("payments", [])
    if not isinstance(payments, list):
        payments = []
    payments.append(entry)
    if len(payments) > 500:
        payments = payments[-500:]
    data["payments"] = payments
    db.save_document(_HISTORY, data)


def _update_history_status(payment_id: str, status: str, extra: dict = None):
    data = db.get_document(_HISTORY)
    if not isinstance(data, dict):
        return
    for entry in reversed(data.get("payments", [])):
        if entry.get("payment_id") == payment_id:
            entry["status"] = status
            if extra:
                entry.update(extra)
            break
    db.save_document(_HISTORY, data)


def get_history(guild_id: str = None) -> list:
    data = db.get_document(_HISTORY)
    if not isinstance(data, dict):
        return []
    payments = data.get("payments", [])
    if guild_id:
        return [p for p in payments if p.get("guild_id") == str(guild_id)]
    return payments


def receita_total() -> float:
    aprovados = [p for p in get_history() if p.get("status") == "approved"]
    return round(sum(float(p.get("valor", 0)) for p in aprovados), 2)


# ─── Criação de cobrança do kit ──────────────────────────────────────────────
async def criar_cobranca_kit(guild_id: str, user_id: str, ext_ids: list[str],
                             metodo: str, bot=None) -> dict:
    """
    Cria a cobrança de um kit de extensões.
    metodo: "pix" | "credito" | "debito".

    Retorna dict com:
      success, error?
      Para PIX:    payment_id, pix_copia_cola, qr_bytes, total, itens, desconto...
      Para cartão: payment_id, checkout_url, total, itens, desconto...
    """
    if not configurada():
        return {"success": False, "error": "Sistema de pagamento não configurado."}

    metodos = metodos_habilitados()
    if metodo not in ("pix", "credito", "debito") or not metodos.get(metodo, False):
        return {"success": False, "error": f"Método de pagamento '{metodo}' indisponível."}

    calc = pricing.calcular_kit(ext_ids)
    if calc.get("vazio") or calc.get("total", 0) <= 0:
        return {"success": False, "error": "Selecione ao menos uma extensão."}

    total = calc["total"]
    now = int(time.time())
    external_ref = f"ext_{guild_id}_{now}"
    token = _token()

    # duração por extensão (para ativar depois)
    dias_por_ext = {i["id"]: i.get("duracao_dias", 30) for i in calc["itens"]}

    base_record = {
        "guild_id": str(guild_id),
        "user_id": str(user_id),
        "ext_ids": [i["id"] for i in calc["itens"]],
        "dias_por_ext": dias_por_ext,
        "valor": total,
        "desconto_percent": calc.get("desconto_percent", 0.0),
        "metodo": metodo,
        "external_reference": external_ref,
        "status": "pending",
        "created_at": now,
        "expires_at": now + 1800,
    }

    if metodo == "pix":
        return await _criar_pix(token, external_ref, total, calc, base_record, bot)
    else:
        return await _criar_cartao(token, external_ref, total, calc, base_record, metodo)


async def _criar_pix(token, external_ref, total, calc, base_record, bot) -> dict:
    from privacylib.extensions import qr as qrgen

    url = f"{_MP_BASE}/v1/payments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": external_ref,
        "User-Agent": _UA,
    }
    body = {
        "transaction_amount": total,
        "payment_method_id": "pix",
        "description": "Extensões PrivacyBOT",
        "external_reference": external_ref,
        "payer": {"email": f"srv_{base_record['guild_id']}@bot.privacy.com"},
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as resp:
                if resp.status not in (200, 201):
                    txt = await resp.text()
                    print(f"[EXT_PAY] MP PIX erro {resp.status}: {txt[:200]}")
                    return {"success": False, "error": "Erro ao gerar pagamento PIX."}
                data = await resp.json()
    except Exception as e:
        print(f"[EXT_PAY] PIX request erro: {e}")
        return {"success": False, "error": "Pagamento temporariamente indisponível."}

    mp_id = str(data.get("id", ""))
    pix_info = data.get("point_of_interaction", {}).get("transaction_data", {})
    pix_copia_cola = pix_info.get("qr_code", "")

    # Gerar QR com a logo do bot (nunca falha; fallback sem logo)
    qr_bytes = None
    if pix_copia_cola:
        try:
            if bot is not None:
                qr_bytes = await qrgen.gerar_qr_com_logo(pix_copia_cola, bot)
            else:
                qr_bytes = await qrgen.gerar_qr_simples(pix_copia_cola)
        except Exception:
            qr_bytes = None

    base_record["payment_id"] = mp_id
    base_record["pix_copia_cola"] = pix_copia_cola
    _save_pending(mp_id, base_record)
    _record_history(dict(base_record, tipo="pix"))

    return {
        "success": True,
        "metodo": "pix",
        "payment_id": mp_id,
        "pix_copia_cola": pix_copia_cola,
        "qr_bytes": qr_bytes,
        "total": total,
        "itens": calc["itens"],
        "desconto_percent": calc.get("desconto_percent", 0.0),
        "desconto_valor": calc.get("desconto_valor", 0.0),
        "subtotal": calc.get("subtotal", total),
    }


async def _criar_cartao(token, external_ref, total, calc, base_record, metodo) -> dict:
    """
    Cria uma preference (checkout) do Mercado Pago para cartão de crédito/débito.
    O bot NÃO coleta dados de cartão — apenas devolve a URL do checkout seguro.
    """
    url = f"{_MP_BASE}/checkout/preferences"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": external_ref,
        "User-Agent": _UA,
    }
    # Restringe os tipos de pagamento conforme o método escolhido
    excluded = [{"id": "ticket"}, {"id": "bank_transfer"}]  # sem PIX/boleto no checkout de cartão
    payment_types = []
    if metodo == "credito":
        payment_types = [{"id": "debit_card"}, {"id": "prepaid_card"}]  # exclui débito/pré-pago
    elif metodo == "debito":
        payment_types = [{"id": "credit_card"}]  # exclui crédito

    body = {
        "items": [{
            "title": "Extensões PrivacyBOT",
            "quantity": 1,
            "unit_price": total,
            "currency_id": "BRL",
        }],
        "external_reference": external_ref,
        "payment_methods": {
            "excluded_payment_types": excluded + payment_types,
            "installments": 12 if metodo == "credito" else 1,
        },
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as resp:
                if resp.status not in (200, 201):
                    txt = await resp.text()
                    print(f"[EXT_PAY] MP cartão erro {resp.status}: {txt[:200]}")
                    return {"success": False, "error": "Erro ao gerar checkout de cartão."}
                data = await resp.json()
    except Exception as e:
        print(f"[EXT_PAY] Cartão request erro: {e}")
        return {"success": False, "error": "Pagamento temporariamente indisponível."}

    pref_id = str(data.get("id", ""))
    checkout_url = data.get("init_point") or data.get("sandbox_init_point")

    base_record["payment_id"] = pref_id
    base_record["preference_id"] = pref_id
    base_record["checkout_url"] = checkout_url
    _save_pending(pref_id, base_record)
    _record_history(dict(base_record, tipo=metodo))

    return {
        "success": True,
        "metodo": metodo,
        "payment_id": pref_id,
        "checkout_url": checkout_url,
        "total": total,
        "itens": calc["itens"],
        "desconto_percent": calc.get("desconto_percent", 0.0),
        "desconto_valor": calc.get("desconto_valor", 0.0),
        "subtotal": calc.get("subtotal", total),
    }


# ─── Verificação de status e ativação ────────────────────────────────────────
async def checar_status(payment_id: str) -> Optional[str]:
    """Consulta o status de um pagamento no Mercado Pago."""
    token = _token()
    if not token:
        return None
    url = f"{_MP_BASE}/v1/payments/{payment_id}"
    headers = {"Authorization": f"Bearer {token}", "User-Agent": _UA}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("status")
    except Exception:
        return None


async def buscar_por_referencia(external_ref: str) -> Optional[dict]:
    """
    Busca um pagamento aprovado pela external_reference (funciona para PIX e cartão).

    Usado para confirmar pagamentos de CARTÃO, cujo id salvo é o da preference
    (checkout) e não é consultável em /v1/payments/{id}. O checkout de cartão gera
    um pagamento real que fica pesquisável pela mesma external_reference.

    Retorna o dict do pagamento aprovado mais recente, ou None.
    """
    token = _token()
    if not token or not external_ref:
        return None
    url = f"{_MP_BASE}/v1/payments/search?external_reference={external_ref}&sort=date_created&criteria=desc"
    headers = {"Authorization": f"Bearer {token}", "User-Agent": _UA}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
    except Exception:
        return None

    results = data.get("results", []) if isinstance(data, dict) else []
    # Prioriza um pagamento aprovado.
    for pay in results:
        if pay.get("status") == "approved":
            return pay
    # Se nenhum aprovado, devolve o mais recente (para checar cancelado/recusado).
    return results[0] if results else None


async def on_aprovado(payment_id: str, bot=None) -> dict:
    """
    Processa a aprovação de um pagamento: ativa o kit (idempotente) e loga.
    Seguro para chamar mais de uma vez (idempotência via subscriptions.ativar_kit).
    Retorna dict com resultado.
    """
    record = _get_pending(payment_id)
    if not record:
        return {"success": False, "error": "Pagamento não encontrado nos pendentes."}

    guild_id = record["guild_id"]
    ext_ids = record["ext_ids"]
    dias_por_ext = record.get("dias_por_ext", {})
    valor = record.get("valor", 0.0)

    ativou = subscriptions.ativar_kit(
        guild_id, ext_ids, dias_por_ext,
        via="payment", payment_id=payment_id, valor_total=valor,
    )

    _update_history_status(payment_id, "approved", {
        "approved_at": int(time.time()),
    })
    _remove_pending(payment_id)

    # Log (import tardio para evitar ciclo); nunca falha o fluxo
    if ativou:
        try:
            from privacylib.extensions import logs
            await logs.registrar_compra(
                bot, guild_id, record.get("user_id"), ext_ids, valor,
                record.get("desconto_percent", 0.0), via="payment",
            )
        except Exception:
            pass

    return {"success": True, "ativou": ativou, "guild_id": guild_id, "ext_ids": ext_ids}
