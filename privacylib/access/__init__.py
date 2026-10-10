"""Controle de acesso por extensão (domínio) — Fase B: implementação canônica.

A lógica de decisão de acesso foi movida de ``functions/extensions/access.py``
para este pacote (``privacylib/access/__init__.py``). O antigo
``functions/extensions/access.py`` passou a ser um shim que reexporta por
identidade os símbolos públicos daqui, de modo que:

    functions.extensions.access.pode_usar is privacylib.access.pode_usar

Fluxo de decisão (Req 5) — preservado EXATAMENTE:
    1. É o dono do bot?            → permite tudo
    2. A guild é o servidor raiz?  → permite tudo
    3. O módulo é de núcleo?       → permite (painel + ticket básico)
    4. Existe extensão ativa que habilita o módulo? → permite
    5. Caso contrário             → bloqueia (informando a extensão necessária)

Comportamento de entrada nula preservado: ``guild_id`` / ``user_id`` iguais a
``None`` resultam em ``False`` sem exceção, nos mesmos pontos da lógica original.

Cycle-safety (Req 15.3): a camada ``access`` depende das camadas inferiores
``extensions`` (``catalog``/``subscriptions``) e ``db``. Para evitar ciclos,
este módulo referencia as fontes CANÔNICAS ``functions.extensions.catalog``,
``functions.extensions.subscriptions`` e ``functions.database`` (que é o shim
canônico para ``privacylib.db.store``). Nenhum desses módulos importa de volta
``privacylib.access``, e a fachada raiz ``privacylib`` NÃO é importada em tempo
de carga (a fachada resolve ``access`` de forma preguiçosa via ``__getattr__``).
Portanto o import de ``privacylib.access`` é livre de ciclos.

Como este é um pacote, os módulos irmãos ``privacylib.access.perms``,
``privacylib.access.server`` e ``privacylib.access.plan`` permanecem importáveis.

_Requirements: 14.1, 14.3, 9.1, 9.5, 9.6, 9.7, 15.3_
"""
from typing import Optional
from functions.database import database as db
from functions.extensions import catalog, subscriptions

# Módulos sempre liberados, sem exigir assinatura (Req 5.4).
# "painel" = /painel ; "ticket_basico" = abrir/fechar/atender ticket.
CORE_MODULES = {"painel", "ticket_basico"}


def _config() -> dict:
    return db.obter("config.json") or {}


def is_owner(user_id) -> bool:
    """True se o usuário é o dono do bot (config.json bot.owner)."""
    owner_id = _config().get("bot", {}).get("owner", "")
    return str(user_id) == str(owner_id)


def is_root_guild(guild_id) -> bool:
    """True se a guild é o servidor raiz/owner (config.json bot.server)."""
    server_id = _config().get("bot", {}).get("server", "")
    return str(guild_id) == str(server_id)


def is_core(modulo: str) -> bool:
    """True se o módulo faz parte do núcleo gratuito."""
    return modulo in CORE_MODULES


def extensao_necessaria(modulo: str) -> Optional[str]:
    """Retorna o id da extensão que habilita o módulo, ou None se for núcleo/desconhecido."""
    if is_core(modulo):
        return None
    return catalog.extensao_de_modulo(modulo)


def pode_usar(guild_id, user_id, modulo: str) -> bool:
    """
    Decisão central de acesso a uma funcionalidade (módulo interno).
    """
    # 1. Dono do bot tem acesso irrestrito (Req 5.3)
    if is_owner(user_id):
        return True

    # 2. Servidor raiz libera todos os sistemas (Req 5.7)
    if guild_id is not None and is_root_guild(guild_id):
        return True

    # 3. Núcleo é sempre liberado (Req 5.4)
    if is_core(modulo):
        return True

    # 4. Precisa de extensão ativa
    ext_id = catalog.extensao_de_modulo(modulo)
    if not ext_id:
        # Módulo não mapeado a nenhuma extensão e não é núcleo:
        # por segurança, bloquear (evita liberar algo não previsto).
        return False

    # A extensão precisa estar ativa no catálogo (não desativada globalmente — Req 7.3.1)
    if not catalog.esta_ativa_no_catalogo(ext_id):
        return False

    # E o servidor precisa ter a assinatura ativa e não expirada (Req 5.5)
    if guild_id is None:
        return False
    return subscriptions.ativa(str(guild_id), ext_id)


def loja_aceita_cartao(guild_id) -> bool:
    """
    True se a loja do servidor pode aceitar cartão de crédito/débito, ou seja, se a
    extensão `loja_cartao` está ativa (ou é servidor raiz). Usado pelo checkout da
    loja para exibir/ocultar as opções de cartão (Req 12.7/12.8).
    """
    if guild_id is not None and is_root_guild(guild_id):
        return True
    if not catalog.esta_ativa_no_catalogo("loja_cartao"):
        return False
    if guild_id is None:
        return False
    return subscriptions.ativa(str(guild_id), "loja_cartao")


def guard_message(modulo: str) -> str:
    """
    Mensagem padrão de bloqueio, informando qual extensão assinar (Req 5.2).
    """
    ext_id = catalog.extensao_de_modulo(modulo)
    ext = catalog.obter(ext_id) if ext_id else None
    if ext:
        emoji = ext.get("emoji", "🧩")
        nome = ext.get("nome", ext_id)
        preco = ext.get("preco_mensal", 0.0)
        return (
            f"🔒 Esta funcionalidade faz parte da extensão {emoji} **{nome}**, "
            f"que este servidor ainda não assinou.\n"
            f"> Valor: **R$ {preco:.2f}/mês**\n"
            f"Abra o **Painel → Extensões** para assinar e liberar o acesso."
        )
    return (
        "🔒 Esta funcionalidade requer uma extensão que este servidor ainda não assinou.\n"
        "Abra o **Painel → Extensões** para ver as opções disponíveis."
    )


def requer_extensao(modulo: str):
    """
    Decorator para comandos slash: bloqueia se o servidor não tiver acesso ao módulo.
    Uso:
        @requer_extensao("moderacao")
        async def comando(self, inter): ...
    Responde ephemeral com guard_message se bloqueado.
    """
    def decorator(func):
        import functools

        @functools.wraps(func)
        async def wrapper(self, inter, *args, **kwargs):
            guild_id = inter.guild.id if inter.guild else None
            if not pode_usar(guild_id, inter.author.id, modulo):
                try:
                    await inter.response.send_message(guard_message(modulo), ephemeral=True)
                except Exception:
                    try:
                        await inter.edit_original_message(content=guard_message(modulo))
                    except Exception:
                        pass
                return
            return await func(self, inter, *args, **kwargs)

        return wrapper

    return decorator


__all__ = [
    "pode_usar",
    "is_owner",
    "is_root_guild",
    "is_core",
    "loja_aceita_cartao",
    "guard_message",
    "requer_extensao",
    # Helpers públicos preservados do módulo original
    "CORE_MODULES",
    "extensao_necessaria",
]
