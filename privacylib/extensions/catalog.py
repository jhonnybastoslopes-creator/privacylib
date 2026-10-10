"""
privacylib/extensions/catalog.py — Catálogo de Extensões.

Fonte da verdade das extensões vendáveis. Persistido no MongoDB no documento
`ext_catalog` com a forma:

    {
        "extensions": {
            "loja": {
                "id": "loja",
                "nome": "Loja",
                "descricao": "...",
                "preco_mensal": 29.90,     # BRL
                "duracao_dias": 30,
                "modulos": ["loja"],        # módulos internos que a extensão habilita
                "ativa": True,               # ativa/inativa para venda global
                "emoji": "🛒"
            },
            ...
        }
    }

Não depende de disnake — apenas da camada de banco (`privacylib.db.store`).

_Requirements: 14.1, 14.3
"""
from typing import Optional
from privacylib.db.store import database as db

_DOC = "ext_catalog"


# ─────────────────────────────────────────────────────────────────────────────
# Catálogo padrão (seed). Cada entrada mapeia uma funcionalidade vendável para os
# módulos internos que ela habilita. O Ticket básico e o /painel são NÚCLEO
# (gratuitos) e por isso NÃO aparecem aqui.
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_CATALOG = {
    "loja": {
        "nome": "Loja",
        "descricao": "Sistema de vendas completo: produtos, carrinho, cupons, saldo e cashback.",
        "preco_mensal": 29.90,
        "duracao_dias": 30,
        "modulos": ["loja"],
        "emoji": "🛒",
    },
    "loja_cartao": {
        "nome": "Loja — Cartão de Crédito/Débito",
        "descricao": "Permite que a loja do seu servidor aceite cartão de crédito e débito.",
        "preco_mensal": 14.90,
        "duracao_dias": 30,
        "modulos": ["loja_cartao"],
        "emoji": "💳",
    },
    "sorteios": {
        "nome": "Sorteios",
        "descricao": "Sorteios com requisitos, agendamento e re-sorteio.",
        "preco_mensal": 14.90,
        "duracao_dias": 30,
        "modulos": ["giveaways"],
        "emoji": "🎉",
    },
    "protecao": {
        "nome": "Proteção",
        "descricao": "Anti-raid, privatizações e proteção geral do servidor.",
        "preco_mensal": 24.90,
        "duracao_dias": 30,
        "modulos": ["protection"],
        "emoji": "🛡️",
    },
    "automacoes": {
        "nome": "Automações",
        "descricao": "Boas-vindas, moderação por IA, contadores, sugestões e mais.",
        "preco_mensal": 19.90,
        "duracao_dias": 30,
        "modulos": ["automations"],
        "emoji": "⚙️",
    },
    "faccao": {
        "nome": "Facção FiveM e SAMP",
        "descricao": "Gestão de organização FiveM: metas, farm, advertências, cofre e hierarquia.",
        "preco_mensal": 29.90,
        "duracao_dias": 30,
        "modulos": ["faccao"],
        "emoji": "🏴",
    },
    "formulario": {
        "nome": "Formulário",
        "descricao": "Formulários de inscrição/whitelist com prints e aprovação.",
        "preco_mensal": 14.90,
        "duracao_dias": 30,
        "modulos": ["formulario"],
        "emoji": "📝",
    },
    "rendimentos": {
        "nome": "Rendimentos",
        "descricao": "Relatórios e gráficos das vendas da loja.",
        "preco_mensal": 9.90,
        "duracao_dias": 30,
        "modulos": ["rendimentos"],
        "emoji": "📈",
    },
    "fists": {
        "nome": "Fists",
        "descricao": "Criador de imagens com moldura (estáticas e animadas) para GTA SA.",
        "preco_mensal": 14.90,
        "duracao_dias": 30,
        "modulos": ["fists"],
        "emoji": "🥊",
    },
    "moderacao": {
        "nome": "Moderação",
        "descricao": "Comandos de moderação: banir, expulsar, castigar, limpar, lock e mais.",
        "preco_mensal": 12.90,
        "duracao_dias": 30,
        "modulos": ["moderacao"],
        "emoji": "🔨",
    },
    "traducao_ticket": {
        "nome": "Tradução no Ticket",
        "descricao": "Tradução automática das mensagens dentro dos tickets.",
        "preco_mensal": 9.90,
        "duracao_dias": 30,
        "modulos": ["traducao_ticket"],
        "emoji": "🌐",
    },
    "ia_ticket": {
        "nome": "IA no Ticket",
        "descricao": "Atendimento inicial por IA (PrivacyAI) nos tickets.",
        "preco_mensal": 19.90,
        "duracao_dias": 30,
        "modulos": ["ia_ticket"],
        "emoji": "🤖",
    },
}


# ─── Acesso ao documento ─────────────────────────────────────────────────────
def _load() -> dict:
    data = db.get_document(_DOC)
    if not isinstance(data, dict):
        return {"extensions": {}}
    if "extensions" not in data or not isinstance(data.get("extensions"), dict):
        data = {"extensions": {}}
    return data


def _save(data: dict):
    db.save_document(_DOC, data)


# ─── API pública ─────────────────────────────────────────────────────────────
def seed_inicial() -> int:
    """
    Cria as extensões padrão que ainda não existirem no catálogo.
    Idempotente: não sobrescreve extensões já cadastradas (preserva preços editados).
    Retorna quantas extensões foram criadas.
    """
    data = _load()
    extensions = data["extensions"]
    criadas = 0
    for ext_id, base in DEFAULT_CATALOG.items():
        if ext_id in extensions:
            continue
        extensions[ext_id] = {
            "id": ext_id,
            "nome": base["nome"],
            "descricao": base["descricao"],
            "preco_mensal": float(base["preco_mensal"]),
            "duracao_dias": int(base["duracao_dias"]),
            "modulos": list(base["modulos"]),
            "ativa": True,
            "emoji": base.get("emoji", "🧩"),
        }
        criadas += 1
    if criadas:
        data["extensions"] = extensions
        _save(data)
    return criadas


def listar(incluir_inativas: bool = False) -> list[dict]:
    """Retorna a lista de extensões do catálogo (ordenada por nome)."""
    data = _load()
    itens = list(data["extensions"].values())
    if not incluir_inativas:
        itens = [e for e in itens if e.get("ativa", True)]
    return sorted(itens, key=lambda e: e.get("nome", ""))


def obter(ext_id: str) -> Optional[dict]:
    """Retorna uma extensão pelo id, ou None se não existir."""
    return _load()["extensions"].get(ext_id)


def existe(ext_id: str) -> bool:
    return ext_id in _load()["extensions"]


def criar(ext_id: str, dados: dict) -> bool:
    """
    Cria uma nova extensão. Rejeita se o id já existir (Req 1.5).
    `dados` deve conter ao menos: nome, preco_mensal. Demais campos têm padrão.
    Retorna True se criada, False se o id já existia.
    """
    data = _load()
    if ext_id in data["extensions"]:
        return False
    data["extensions"][ext_id] = {
        "id": ext_id,
        "nome": dados.get("nome", ext_id),
        "descricao": dados.get("descricao", ""),
        "preco_mensal": float(dados.get("preco_mensal", 0.0)),
        "duracao_dias": int(dados.get("duracao_dias", 30)),
        "modulos": list(dados.get("modulos", [ext_id])),
        "ativa": bool(dados.get("ativa", True)),
        "emoji": dados.get("emoji", "🧩"),
    }
    _save(data)
    return True


def atualizar(ext_id: str, dados: dict) -> bool:
    """Atualiza campos de uma extensão existente. Retorna False se não existir."""
    data = _load()
    ext = data["extensions"].get(ext_id)
    if not ext:
        return False
    for campo in ("nome", "descricao", "emoji"):
        if campo in dados:
            ext[campo] = dados[campo]
    if "preco_mensal" in dados:
        ext["preco_mensal"] = float(dados["preco_mensal"])
    if "duracao_dias" in dados:
        ext["duracao_dias"] = int(dados["duracao_dias"])
    if "modulos" in dados:
        ext["modulos"] = list(dados["modulos"])
    if "ativa" in dados:
        ext["ativa"] = bool(dados["ativa"])
    data["extensions"][ext_id] = ext
    _save(data)
    return True


def definir_ativa(ext_id: str, ativa: bool) -> bool:
    """Ativa/desativa uma extensão para venda global (Req 7.3.1/7.3.2)."""
    return atualizar(ext_id, {"ativa": bool(ativa)})


def definir_preco(ext_id: str, preco: float) -> bool:
    """Define o preço mensal de uma extensão (Req 1.7)."""
    return atualizar(ext_id, {"preco_mensal": float(preco)})


def esta_ativa_no_catalogo(ext_id: str) -> bool:
    """True se a extensão existe e está ativa (habilitada globalmente)."""
    ext = obter(ext_id)
    return bool(ext and ext.get("ativa", True))


# ─── Mapeamento módulo ↔ extensão ─────────────────────────────────────────────
def modulos_de(ext_id: str) -> list[str]:
    """Módulos internos que uma extensão habilita."""
    ext = obter(ext_id)
    return list(ext.get("modulos", [])) if ext else []


def extensao_de_modulo(modulo: str) -> Optional[str]:
    """
    Retorna o id da extensão que habilita um módulo interno, ou None se o módulo
    não pertencer a nenhuma extensão (ex.: módulo de núcleo).
    """
    for ext in _load()["extensions"].values():
        if modulo in ext.get("modulos", []):
            return ext.get("id")
    return None
