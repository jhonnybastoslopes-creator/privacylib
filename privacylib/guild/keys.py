"""
privacylib/guild/keys.py — Geração centralizada de chaves por-servidor.

Este módulo introduz a ``KeyFactory``, que aposenta gradualmente os ~132 helpers
locais duplicados (``_lk``, ``_tk_key``, ``_srv_key``, ``_pk``, ``_fk``) espalhados
pelo código. Todos eles produzem exatamente a mesma Chave_Por_Servidor:

    f"{base}_{guild_id}"

Dois caminhos de uso:

- ``key`` (instância pronta de :class:`KeyFactory`): resolve o ``guild_id`` a partir
  do Contexto_De_Guild atual (``current_guild_id()``). Ideal para handlers de
  interação, onde o contexto já foi definido pelo binder global.
- ``key_for(base, guild_id)``: recebe o ``guild_id`` explicitamente. Ideal para
  listeners de ``on_message``/tarefas de background onde não há contexto implícito.

O import de ``current_guild_id`` é feito de forma TARDIA (dentro do método), para
respeitar as camadas e evitar ciclos de import em tempo de carga do módulo.

Requirements: 3.3, 3.4, 3.6, 3.7, 3.8, 15.3, 16.1, 16.2, 16.3
"""

__all__ = [
    "KeyFactory",
    "key",
    "key_for",
    # Guarda global vs. por-servidor (Req. 16.1–16.3)
    "GLOBAL_DOCUMENTS",
    "is_global_document",
    "assert_per_server",
    "guarded_key_for",
]


# ─── Guarda de preservação: Documento_Global vs. Chave_Por_Servidor ───────────
#
# Fonte única de verdade do conjunto de Documentos_Globais — documentos que DEVEM
# ser acessados por chave simples, SEM sufixo de guild e SEM prefixo (Req. 16.2).
#
# Reconciliação das duas listas existentes no projeto:
#   1) design.md › "Documentos globais (NÃO por-servidor)":
#        custom_colors, custom_mode, canais, cargos, server_plans, ext_catalog,
#        ext_subscriptions, ext_payment_config, error_logs_config
#   2) docstring de functions/guild_store.py:
#        custom_colors, custom_mode, canais, cargos, bot_permissions, server_plans,
#        owner_payment_config, ext_*
#
# Adotamos o SUPERSET claramente correto (união das duas listas). Além disso,
# qualquer base com o prefixo "ext_" é tratada como global, conforme a convenção
# do marketplace de extensões (ext_catalog, ext_subscriptions, ext_payment_config,
# e demais ext_*). Ver is_global_document().
GLOBAL_DOCUMENTS = frozenset({
    "custom_colors",
    "custom_mode",
    "canais",
    "cargos",
    "bot_permissions",       # da docstring de functions/guild_store.py
    "server_plans",
    "owner_payment_config",  # da docstring de functions/guild_store.py
    "ext_catalog",
    "ext_subscriptions",
    "ext_payment_config",
    "error_logs_config",     # per-servidor usa error_logs_config_{guild}
})

#: Prefixos cujas bases são sempre tratadas como globais (marketplace de extensões).
_GLOBAL_PREFIXES = ("ext_",)


def is_global_document(base: str) -> bool:
    """Indica se ``base`` é um Documento_Global (chave simples, sem sufixo de guild).

    Um documento é global quando pertence ao conjunto canônico
    :data:`GLOBAL_DOCUMENTS` ou quando seu nome começa com um prefixo global
    (``ext_``). Documentos globais NÃO devem receber o sufixo ``_{guild_id}``
    (Req. 16.2).

    Args:
        base: nome lógico do documento (ex.: ``"custom_colors"``,
            ``"loja_products"``).

    Returns:
        ``True`` se o documento deve permanecer global; ``False`` caso contrário.
        Entrada nula/vazia retorna ``False`` (não é um documento global conhecido),
        sem lançar exceção.
    """
    if not base:
        return False
    if base in GLOBAL_DOCUMENTS:
        return True
    return any(base.startswith(prefix) for prefix in _GLOBAL_PREFIXES)


def assert_per_server(base: str) -> None:
    """Guarda advisória: garante que ``base`` NÃO é um Documento_Global.

    Deve ser chamada antes de compor uma Chave_Por_Servidor para capturar o uso
    indevido de aplicar o sufixo ``_{guild_id}`` a um documento que deve permanecer
    global (Req. 16.2). É opcional/defensiva — não altera nenhum fluxo de leitura
    ou escrita existente, apenas sinaliza o erro quando explicitamente usada.

    Raises:
        ValueError: se ``base`` for um Documento_Global conhecido.
    """
    if is_global_document(base):
        raise ValueError(
            f"assert_per_server: '{base}' é um Documento_Global e deve ser acessado "
            f"por chave simples, sem sufixo de guild nem prefixo (Req. 16.2). "
            f"Não componha '{base}_{{guild_id}}'."
        )


def guarded_key_for(base: str, guild_id) -> str:
    """Como :func:`key_for`, mas recusa compor chave para um Documento_Global.

    Variante defensiva de :func:`key_for`: além de validar ``guild_id``, aplica
    :func:`assert_per_server` para impedir que um Documento_Global ganhe o sufixo
    ``_{guild_id}`` por engano (Req. 16.2). É opcional — os fluxos existentes
    continuam usando :func:`key_for`/``key`` inalterados.

    Raises:
        ValueError: se ``base`` for global, ou se ``guild_id`` for nulo/vazio.
    """
    assert_per_server(base)
    return key_for(base, guild_id)


class KeyFactory:
    """Gera chaves por-servidor a partir do Contexto_De_Guild atual.

    Substitui os helpers locais ``_lk``/``_tk_key``/``_srv_key``/``_pk``/``_fk``,
    produzindo chaves idênticas, caractere por caractere: ``f"{base}_{guild_id}"``.

    Args:
        prefixo: prefixo opcional reservado para composições futuras. Mantido por
            compatibilidade com a forma descrita no design; não altera o formato
            da chave gerada quando vazio.
    """

    def __init__(self, prefixo: str = ""):
        self._prefixo = prefixo

    def __call__(self, base: str) -> str:
        # Import tardio para respeitar as camadas (domínio → infra) e evitar ciclos.
        from privacylib.guild.context import current_guild_id

        gid = current_guild_id()
        if gid is None or str(gid) == "":
            # Rejeita sem produzir chave, preservando o estado inalterado.
            raise RuntimeError(
                "KeyFactory: nenhum contexto de guild ativo "
                "(current_guild_id() retornou nulo). Defina o contexto com "
                "set_current_guild(guild_id) ou use key_for(base, guild_id)."
            )
        return f"{base}_{gid}"


# Helper pronto, compatível com os nomes atuais: key("loja_products") -> "loja_products_{guild}".
key = KeyFactory()


def key_for(base: str, guild_id) -> str:
    """Chave por-servidor com ``guild_id`` explícito.

    Para listeners de ``on_message`` e tarefas de background onde não há
    Contexto_De_Guild implícito.

    Raises:
        ValueError: se ``guild_id`` for nulo ou vazio — a operação é rejeitada sem
            produzir chave, preservando o estado inalterado.
    """
    if guild_id is None or str(guild_id) == "":
        raise ValueError(
            "key_for: guild_id inválido (nulo ou vazio); nenhuma chave foi produzida."
        )
    return f"{base}_{guild_id}"
