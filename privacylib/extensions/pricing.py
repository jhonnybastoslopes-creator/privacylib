"""
privacylib/extensions/pricing.py — Cálculo de Kit e Descontos.

Persistido no MongoDB no documento `ext_pricing_config`:

    {
        "modo": "manual",                 # "manual" | "automatico"
        "auto": {"percent": 10.0, "min_extensoes": 3},
        "combos": [
            {"nome": "Combo FiveM", "extensoes": ["faccao", "loja"], "percent": 15.0}
        ]
    }

Regras (Req 3):
- Subtotal = soma dos preços das extensões selecionadas.
- Modo manual: aplica o combo cujo conjunto de extensões ⊆ seleção.
- Modo automático: aplica o percent se len(seleção) >= min_extensoes.
- Descontos NÃO são cumulativos: usa o de maior percent (Req 3.5).
- Total arredondado a 2 casas (Req 3.9).

_Requirements: 14.1, 14.3
"""
from privacylib.db.store import database as db
from privacylib.extensions import catalog

_DOC = "ext_pricing_config"

_DEFAULT = {
    "modo": "manual",
    "auto": {"percent": 10.0, "min_extensoes": 3},
    "combos": [],
}


def _load() -> dict:
    data = db.get_document(_DOC)
    if not isinstance(data, dict) or "modo" not in data:
        return dict(_DEFAULT)
    # Garantir chaves
    data.setdefault("modo", "manual")
    data.setdefault("auto", {"percent": 10.0, "min_extensoes": 3})
    data.setdefault("combos", [])
    return data


def _save(data: dict):
    db.save_document(_DOC, data)


# ─── Configuração (dono do bot — Req 7.4) ────────────────────────────────────
def obter_config() -> dict:
    return _load()


def definir_modo(modo: str):
    """modo = 'manual' | 'automatico'."""
    data = _load()
    data["modo"] = "automatico" if modo == "automatico" else "manual"
    _save(data)


def definir_auto(percent: float, min_extensoes: int):
    data = _load()
    data["auto"] = {"percent": float(percent), "min_extensoes": int(min_extensoes)}
    _save(data)


def add_combo(nome: str, extensoes: list[str], percent: float):
    data = _load()
    data["combos"].append({
        "nome": nome,
        "extensoes": list(extensoes),
        "percent": float(percent),
    })
    _save(data)


def remover_combo(indice: int) -> bool:
    data = _load()
    if 0 <= indice < len(data["combos"]):
        data["combos"].pop(indice)
        _save(data)
        return True
    return False


# ─── Cálculo (Req 3) ─────────────────────────────────────────────────────────
def _desconto_aplicavel(ext_ids: list[str], config: dict) -> tuple[float, str | None]:
    """
    Retorna (percent, nome) do maior desconto aplicável à seleção.
    Não-cumulativo: escolhe o de maior percent entre combos e automático.
    """
    selecao = set(ext_ids)
    melhor_percent = 0.0
    melhor_nome = None

    if config.get("modo") == "manual":
        for combo in config.get("combos", []):
            combo_exts = set(combo.get("extensoes", []))
            if combo_exts and combo_exts.issubset(selecao):
                p = float(combo.get("percent", 0.0))
                if p > melhor_percent:
                    melhor_percent = p
                    melhor_nome = combo.get("nome", "Combo")
    else:  # automatico
        auto = config.get("auto", {})
        min_ext = int(auto.get("min_extensoes", 0))
        if min_ext > 0 and len(selecao) >= min_ext:
            p = float(auto.get("percent", 0.0))
            if p > melhor_percent:
                melhor_percent = p
                melhor_nome = "Desconto automático"

    return melhor_percent, melhor_nome


def calcular_kit(ext_ids: list[str]) -> dict:
    """
    Calcula o valor de um kit de extensões.
    Retorna dict com itens, subtotal, desconto e total (2 casas).
    Se a seleção for vazia, retorna total 0 e itens vazios (o chamador bloqueia — Req 3.7).
    """
    config = _load()
    itens = []
    subtotal = 0.0

    for ext_id in ext_ids:
        ext = catalog.obter(ext_id)
        if not ext:
            continue
        preco = float(ext.get("preco_mensal", 0.0))
        subtotal += preco
        itens.append({
            "id": ext_id,
            "nome": ext.get("nome", ext_id),
            "preco": round(preco, 2),
            "duracao_dias": int(ext.get("duracao_dias", 30)),
            "emoji": ext.get("emoji", "🧩"),
        })

    desconto_percent, combo_nome = _desconto_aplicavel([i["id"] for i in itens], config)
    subtotal = round(subtotal, 2)
    desconto_valor = round(subtotal * desconto_percent / 100.0, 2)
    total = round(subtotal - desconto_valor, 2)

    return {
        "itens": itens,
        "subtotal": subtotal,
        "desconto_percent": desconto_percent,
        "desconto_valor": desconto_valor,
        "total": total,
        "combo_aplicado": combo_nome,
        "vazio": len(itens) == 0,
    }
