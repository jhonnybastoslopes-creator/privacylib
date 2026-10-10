"""
privacylib/extensions/subscriptions.py — Assinaturas de Extensões por Servidor.

Persistido no MongoDB no documento `ext_subscriptions`:

    {
        "servers": {
            "<guild_id>": {
                "extensions": {
                    "loja": {
                        "expires_at": 1735689600,   # Unix (int)
                        "activated_at": 1733097600,
                        "via": "payment",            # "payment" | "owner_manual"
                        "last_payment_id": "123..."
                    },
                    ...
                },
                "total_pago": 189.70                 # acumulado (para o dashboard)
            }
        }
    }

Regras principais:
- Renovação estende a partir da expiração atual se ainda válida (Req 2.4).
- Compra após expirar começa de agora (Req 2.5).
- Cada extensão é isolada — expirar uma não afeta as outras (Req 2.6, 5.5).
- Corte imediato ao expirar (sem período de graça).

_Requirements: 14.1, 14.3
"""
import time
from typing import Optional
from privacylib.db.store import database as db

_DOC = "ext_subscriptions"
_DIA = 86400


def _load() -> dict:
    data = db.get_document(_DOC)
    if not isinstance(data, dict) or "servers" not in data:
        return {"servers": {}}
    if not isinstance(data.get("servers"), dict):
        data["servers"] = {}
    return data


def _save(data: dict):
    db.save_document(_DOC, data)


def _server_entry(data: dict, guild_id: str) -> dict:
    servers = data["servers"]
    if str(guild_id) not in servers:
        servers[str(guild_id)] = {"extensions": {}, "total_pago": 0.0}
    entry = servers[str(guild_id)]
    if "extensions" not in entry or not isinstance(entry["extensions"], dict):
        entry["extensions"] = {}
    return entry


# ─── Consultas ───────────────────────────────────────────────────────────────
def ativa(guild_id: str, ext_id: str) -> bool:
    """True se a extensão está ativa e não expirada para o servidor (corte imediato)."""
    data = _load()
    entry = data["servers"].get(str(guild_id))
    if not entry:
        return False
    info = entry.get("extensions", {}).get(ext_id)
    if not info:
        return False
    expires_at = info.get("expires_at")
    if not expires_at:
        return False
    return int(time.time()) < int(expires_at)


def listar_ativas(guild_id: str) -> dict:
    """Retorna {ext_id: info} apenas das extensões ativas (não expiradas)."""
    data = _load()
    entry = data["servers"].get(str(guild_id))
    if not entry:
        return {}
    now = int(time.time())
    return {
        eid: info
        for eid, info in entry.get("extensions", {}).items()
        if info.get("expires_at") and now < int(info["expires_at"])
    }


def info_servidor(guild_id: str) -> dict:
    """Retorna a entrada completa do servidor (extensões + total pago). {} se não houver."""
    data = _load()
    return data["servers"].get(str(guild_id), {"extensions": {}, "total_pago": 0.0})


def listar_servidores() -> dict:
    """Retorna todos os servidores com assinaturas (para o dashboard do dono)."""
    return _load()["servers"]


# ─── Ativação ────────────────────────────────────────────────────────────────
def ativar(guild_id: str, ext_id: str, dias: int, via: str = "payment",
           payment_id: Optional[str] = None, valor: float = 0.0) -> int:
    """
    Ativa/renova UMA extensão. Retorna o novo `expires_at` (Unix).
    - Renova a partir da expiração atual se ainda válida (Req 2.4).
    - Começa de agora se expirada ou nova (Req 2.5).
    """
    data = _load()
    entry = _server_entry(data, guild_id)
    now = int(time.time())

    atual = entry["extensions"].get(ext_id, {})
    exp_atual = atual.get("expires_at")
    if exp_atual and int(exp_atual) > now:
        base = int(exp_atual)   # renovação: estende
    else:
        base = now              # nova ou expirada: começa agora

    novo_exp = base + int(dias) * _DIA
    entry["extensions"][ext_id] = {
        "expires_at": novo_exp,
        "activated_at": now,
        "via": via,
        "last_payment_id": payment_id,
    }
    if valor:
        entry["total_pago"] = round(float(entry.get("total_pago", 0.0)) + float(valor), 2)

    _save(data)
    return novo_exp


def ativar_kit(guild_id: str, ext_ids: list[str], dias_por_ext: dict[str, int],
               via: str = "payment", payment_id: Optional[str] = None,
               valor_total: float = 0.0) -> bool:
    """
    Ativa um conjunto de extensões de uma vez. Idempotente por `payment_id` (Req 4.6):
    se o mesmo payment_id já foi aplicado a qualquer extensão do servidor, não reaplica.
    Retorna True se ativou, False se já havia sido aplicado (idempotência).
    """
    data = _load()
    entry = _server_entry(data, guild_id)
    now = int(time.time())

    # Idempotência: se este payment_id já consta em alguma extensão, ignora.
    if payment_id:
        for info in entry["extensions"].values():
            if info.get("last_payment_id") == payment_id:
                return False

    for ext_id in ext_ids:
        dias = int(dias_por_ext.get(ext_id, 30))
        atual = entry["extensions"].get(ext_id, {})
        exp_atual = atual.get("expires_at")
        base = int(exp_atual) if (exp_atual and int(exp_atual) > now) else now
        entry["extensions"][ext_id] = {
            "expires_at": base + dias * _DIA,
            "activated_at": now,
            "via": via,
            "last_payment_id": payment_id,
        }

    if valor_total:
        entry["total_pago"] = round(float(entry.get("total_pago", 0.0)) + float(valor_total), 2)

    _save(data)
    return True


def revogar(guild_id: str, ext_id: str) -> bool:
    """Encerra imediatamente a assinatura de uma extensão (Req 7.3)."""
    data = _load()
    entry = data["servers"].get(str(guild_id))
    if not entry or ext_id not in entry.get("extensions", {}):
        return False
    del entry["extensions"][ext_id]
    _save(data)
    return True


# ─── Expiração ───────────────────────────────────────────────────────────────
def expirar_vencidas() -> list[tuple[str, str]]:
    """
    Remove as extensões cuja data de expiração já passou. Não remove dados de
    configuração dos módulos (Req 8.5) — apenas a assinatura.
    Retorna lista de (guild_id, ext_id) que expiraram, para log.
    """
    data = _load()
    now = int(time.time())
    expiradas: list[tuple[str, str]] = []
    mudou = False

    for gid, entry in data["servers"].items():
        exts = entry.get("extensions", {})
        for eid in list(exts.keys()):
            exp = exts[eid].get("expires_at")
            if exp and now >= int(exp):
                del exts[eid]
                expiradas.append((gid, eid))
                mudou = True

    if mudou:
        _save(data)
    return expiradas
