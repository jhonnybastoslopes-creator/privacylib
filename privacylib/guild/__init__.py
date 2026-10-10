"""
privacylib/guild/ — Isolamento multi-servidor (infra): contexto, store e KeyFactory.

Fachada de conveniência do pacote ``guild``. Reexporta por identidade os símbolos
dos submódulos ``context``, ``store`` e ``keys``, de modo que os consumidores possam
importar diretamente do pacote sem conhecer a organização interna:

    from privacylib.guild import key                       # KeyFactory pronta (contexto atual)
    from privacylib.guild.keys import KeyFactory, key_for  # fábrica e helper explícito
    from privacylib.guild import get, save, set_current_guild, current_guild_id

O design mostra o uso de fachada ``guild.get("loja_products")`` como chamada de
topo do pacote, por isso os helpers de ``store`` (``make_key``, ``get``, ``save``,
``delete``, ``aget``, ``asave``) e de ``context`` (``set_current_guild``,
``current_guild_id``) também são reexportados aqui.

Os submódulos ``privacylib.guild.context``, ``privacylib.guild.store`` e
``privacylib.guild.keys`` continuam importáveis normalmente.

Nota de nomes: ``make_key`` vem de ``store``; ``key``/``key_for``/``KeyFactory`` vêm
de ``keys``. São nomes distintos — não há colisão.

Requirements: 3.6
"""
from privacylib.guild.context import set_current_guild, current_guild_id
from privacylib.guild.store import make_key, get, save, delete, aget, asave
from privacylib.guild.keys import (
    KeyFactory,
    key,
    key_for,
    GLOBAL_DOCUMENTS,
    is_global_document,
    assert_per_server,
    guarded_key_for,
)

__all__ = [
    # context
    "set_current_guild",
    "current_guild_id",
    # store
    "make_key",
    "get",
    "save",
    "delete",
    "aget",
    "asave",
    # keys
    "KeyFactory",
    "key",
    "key_for",
    # guarda global vs. por-servidor (Req. 16.1–16.3)
    "GLOBAL_DOCUMENTS",
    "is_global_document",
    "assert_per_server",
    "guarded_key_for",
]
