"""
privacylib/guild/context.py — Contexto do servidor atual (isolamento multi-servidor).

Fase B da migração: a implementação **real** do contexto por-servidor agora mora
aqui. O módulo antigo ``functions/guild_context.py`` passou a ser um *shim* de
compatibilidade que reexporta ``set_current_guild`` e ``current_guild_id`` daqui
por identidade.

Usa ``contextvars`` (nativo do Python, async-safe) para guardar o guild_id da
interação que está sendo processada AGORA. Assim, os helpers de dados por-servidor
(guild_store, KeyFactory, etc.) resolvem automaticamente o servidor correto, sem
precisar propagar o guild_id manualmente em centenas de chamadas.

Fluxo:
- Um listener global (events/guild_context_binder.py) captura o guild_id de cada
  interação/mensagem e chama set_current_guild(guild_id) ANTES dos handlers rodarem.
- Os helpers chamam current_guild_id() para saber de qual servidor ler/gravar.
- Se não houver contexto (ex.: tarefa de background sem guild), usa o servidor raiz
  (config.json bot.server) como fallback seguro.

contextvars isola automaticamente por tarefa asyncio: interações simultâneas de
servidores diferentes NÃO se misturam.

Requirements: 14.1, 14.3, 16.3
"""
import contextvars

# ContextVar por tarefa asyncio. Default None → usa fallback raiz.
_current_guild: contextvars.ContextVar = contextvars.ContextVar("current_guild_id", default=None)


def set_current_guild(guild_id) -> None:
    """Define o guild_id do contexto atual (chamado no início de cada interação)."""
    _current_guild.set(str(guild_id) if guild_id is not None else None)


def _raiz_guild_id():
    # Import tardio da classe ``database`` para evitar ciclo de import na
    # inicialização: a fachada ``privacylib`` carrega a camada guild e a camada
    # guild não pode importar a infra de dados no topo do módulo. Apontamos para
    # a localização canônica ``privacylib.db.store``. Ver Requisito 15.3.
    from privacylib.db.store import database as db
    cfg = db.obter("config.json") or {}
    return cfg.get("bot", {}).get("server")


def current_guild_id():
    """
    Retorna o guild_id do contexto atual. Se não houver (ex.: background),
    cai no servidor raiz como fallback seguro.
    """
    gid = _current_guild.get()
    if gid is not None:
        return gid
    return _raiz_guild_id()


__all__ = ["set_current_guild", "current_guild_id"]
