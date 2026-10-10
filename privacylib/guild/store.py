"""
privacylib/guild/store.py — Camada de Acesso a Dados por Servidor.

Fase B da migração: a implementação **real** do acesso a dados por-servidor agora
mora aqui. O módulo antigo ``functions/guild_store.py`` passou a ser um *shim* de
compatibilidade que reexporta ``make_key``, ``get``, ``save``, ``delete``, ``aget``
e ``asave`` daqui por identidade.

Wrapper fino sobre a classe ``database`` que compõe a chave do documento com o
`guild_id`, isolando os dados de cada servidor. Reaproveita o cache do database.

Uso:
    from privacylib.guild.store import get, save
    produtos = get("loja_products", guild_id, default={})
    save("loja_products", guild_id, produtos)

Regra da chave: f"{base}_{guild_id}" (ex.: "loja_products_1170540994748498042").

NÃO use este módulo para documentos verdadeiramente globais (custom_colors,
custom_mode, canais, cargos, bot_permissions, server_plans, owner_payment_config,
ext_*). Esses continuam via a camada de dados global diretamente.

Requirements: 14.1, 14.3, 16.3
"""


def _db():
    # Resolução tardia da classe ``database`` para evitar ciclo de import na
    # inicialização: a fachada ``privacylib`` carrega a camada guild e a camada
    # guild não pode importar a infra de dados no topo do módulo. Apontamos para
    # a localização canônica ``privacylib.db.store``. Ver Requisito 15.3.
    from privacylib.db.store import database
    return database


def make_key(base: str, guild_id) -> str:
    """Compõe a chave por-servidor de forma determinística."""
    return f"{base}_{guild_id}"


# ─── Síncrono ────────────────────────────────────────────────────────────────
def get(base: str, guild_id, default=None):
    """Lê o documento por-servidor. Retorna `default` (ou {}) se não existir."""
    data = _db().get_document(make_key(base, guild_id))
    if data:
        return data
    return {} if default is None else default


def save(base: str, guild_id, data) -> None:
    """Grava o documento por-servidor."""
    _db().save_document(make_key(base, guild_id), data)


def delete(base: str, guild_id) -> None:
    """Remove o documento por-servidor."""
    _db().delete_document(make_key(base, guild_id))


# ─── Assíncrono (não bloqueia o event loop) ──────────────────────────────────
async def aget(base: str, guild_id, default=None):
    data = await _db().async_get_document(make_key(base, guild_id))
    if data:
        return data
    return {} if default is None else default


async def asave(base: str, guild_id, data) -> None:
    await _db().async_save_document(make_key(base, guild_id), data)


__all__ = ["make_key", "get", "save", "delete", "aget", "asave"]
