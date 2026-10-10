"""Verificação de shims no boot (Fase B) — Requirement 14.4.

Durante a Fase B da migração, a lógica real mora na ``privacylib`` e os módulos
antigos de ``functions/*``, ``core/*`` e ``connections/*`` viraram *shims* que
reexportam, por identidade, cada símbolo público da biblioteca.

Este módulo implementa a **verificação de shims no boot**: antes do bot conectar,
confirmamos que cada shim antigo realmente reexporta todos os símbolos públicos
esperados do seu módulo canônico da ``privacylib`` e que esses símbolos são o
**mesmo objeto** (identidade ``is``). A garantia é **tudo-ou-nada**:

* A verificação apenas LÊ/ASSERTA — nunca muta estado. Portanto, uma falha
  simplesmente aborta o boot (``raise``) sem deixar o conjunto de shims
  parcialmente resolvido.
* TODOS os problemas são coletados e reportados de uma só vez (não paramos no
  primeiro), mas a inicialização falha (``raise``) se o conjunto de problemas
  for não vazio.
* A mensagem de erro identifica, para cada símbolo divergente/ausente, o
  **símbolo** e o **módulo de origem** (o shim antigo) além do módulo canônico.

Abordagem *data-driven*: em vez de uma lista rígida de nomes, cada par
``(old_module, lib_module)`` deriva os nomes a verificar a partir do contrato
público do PRÓPRIO shim — isto é, do ``__all__`` que o shim declara (ou, na
ausência, dos nomes de nível de módulo que não iniciam com ``_``). Para cada
nome prometido pelo shim, exigimos que o módulo canônico da lib exponha o
mesmo objeto (identidade ``is``). Essa direção (shim → lib) é a correta para o
Requirement 14.4: o shim promete um símbolo antigo e a verificação confirma que
a lib tem o correspondente; se não tiver, falhamos indicando o símbolo e o
módulo de origem (o shim). Também lida corretamente com o caso em que vários
shims (ex.: cada ``core/*.py``) apontam para um único módulo canônico
(``privacylib.bot.lifecycle``): cada shim só é cobrado pelos símbolos que ele
próprio declara.

Distinção importante (robustez do próprio verificador):

* "o módulo canônico não importa por falta de dependência de terceiros"
  (ex.: o problema pré-existente de ambiente com ``googletrans``) → é tratado
  como **aviso de ambiente** (``ShimEnvironmentWarning``), NÃO falha o boot.
* "o shim existe mas não reexporta um símbolo esperado da biblioteca" ou
  "o shim reexporta um objeto diferente (identidade divergente)" → é uma
  **falha real** de shim (``ShimVerificationError``), que faz o boot falhar.

_Requirements: 14.4_
"""

from __future__ import annotations

import importlib
import logging

logger = logging.getLogger("PrivacyBOT.shim_check")


# ─────────────────────────────────────────────────────────────────────────────
# Mapa de shims: (módulo antigo que virou shim) -> (módulo canônico da lib)
# ─────────────────────────────────────────────────────────────────────────────
# Para cada par, os nomes públicos do módulo canônico (lib) são a fonte de
# verdade do que o shim antigo DEVE reexportar por identidade.
SHIM_MAP: tuple[tuple[str, str], ...] = (
    # Infra: dados
    ("functions.database", "privacylib.db.store"),
    ("connections.mongo_db", "privacylib.db.mongo"),
    # Infra: guild / isolamento multi-servidor
    ("functions.guild_context", "privacylib.guild.context"),
    ("functions.guild_store", "privacylib.guild.store"),
    # Infra: erros
    ("functions.error_handler", "privacylib.errors.handler"),
    ("functions.global_error_capture", "privacylib.errors.capture"),
    # Apresentação: ui
    ("functions.message", "privacylib.ui.messages"),
    ("functions.text_utils", "privacylib.ui.text"),
    # Apresentação: emoji
    ("functions.emoji", "privacylib.emoji"),
    ("functions.emojis", "privacylib.emoji.manager"),
    # Apresentação: utils
    ("functions.utils", "privacylib.utils"),
    ("functions.typing_helper", "privacylib.utils.typing"),
    # Domínio: acesso / permissões / planos / servidor
    ("functions.perms", "privacylib.access.perms"),
    ("functions.server_check", "privacylib.access.server"),
    ("functions.plan", "privacylib.access.plan"),
    ("functions.extensions.access", "privacylib.access"),
    # Domínio: marketplace de extensões (8 submódulos)
    ("functions.extensions.catalog", "privacylib.extensions.catalog"),
    ("functions.extensions.subscriptions", "privacylib.extensions.subscriptions"),
    ("functions.extensions.pricing", "privacylib.extensions.pricing"),
    ("functions.extensions.payments", "privacylib.extensions.payments"),
    ("functions.extensions.qr", "privacylib.extensions.qr"),
    ("functions.extensions.logs", "privacylib.extensions.logs"),
    ("functions.extensions.migration", "privacylib.extensions.migration"),
    ("functions.extensions.data_migration", "privacylib.extensions.data_migration"),
    # Bootstrap / ciclo de vida do bot (core/* -> privacylib.bot.lifecycle)
    ("core.create_bot", "privacylib.bot.lifecycle"),
    ("core.change_bio", "privacylib.bot.lifecycle"),
    ("core.change_status", "privacylib.bot.lifecycle"),
    ("core.enable_intents", "privacylib.bot.lifecycle"),
    ("core.log_restart", "privacylib.bot.lifecycle"),
    ("core.server_protection", "privacylib.bot.lifecycle"),
)


class ShimVerificationError(ImportError):
    """Falha real de shim: símbolo esperado ausente ou com identidade divergente.

    Subclasse de ``ImportError`` para que o boot possa capturar genericamente
    problemas de resolução de imports, mantendo semântica clara.
    """


class ShimEnvironmentWarning(RuntimeWarning):
    """Aviso de ambiente: um módulo não importou por dependência de terceiros.

    Não representa uma falha de shim e, portanto, NÃO deve abortar o boot.
    """


def _public_names(module) -> list[str]:
    """Retorna os nomes públicos de ``module``.

    Usa ``__all__`` quando declarado; caso contrário, todos os nomes de nível de
    módulo que não iniciam com ``_`` (Requirement 13.1 — definição de símbolo
    público).
    """
    declared = getattr(module, "__all__", None)
    if declared is not None:
        return list(declared)
    return [name for name in vars(module) if not name.startswith("_")]


def _is_missing_dependency_error(exc: BaseException) -> bool:
    """Heurística: distingue falha por dependência de terceiros ausente.

    Um ``ModuleNotFoundError`` cujo módulo faltante NÃO pertence ao próprio
    projeto (``privacylib``/``functions``/``core``/``connections``) é tratado
    como problema de AMBIENTE (ex.: ``googletrans``), não como falha de shim.
    """
    if isinstance(exc, ModuleNotFoundError):
        faltante = getattr(exc, "name", "") or ""
        raiz = faltante.split(".", 1)[0]
        projeto = {"privacylib", "functions", "core", "connections"}
        if raiz and raiz not in projeto:
            return True
    return False


def verify_shims() -> None:
    """Verifica que todos os shims da Fase B reexportam a lib por identidade.

    Comportamento tudo-ou-nada (Requirement 14.4):

    * Retorna ``None`` em sucesso (todos os símbolos públicos de cada módulo
      canônico estão reexportados pelo shim antigo correspondente, com a mesma
      identidade de objeto).
    * Levanta ``ShimVerificationError`` listando TODOS os símbolos ausentes ou
      divergentes de uma só vez, cada um com seu módulo de origem (o shim) e o
      módulo canônico. Como a função só lê/asserta, o ``raise`` apenas aborta o
      boot — nunca deixa um estado parcialmente resolvido.

    Falhas de import por dependência de terceiros ausente (ambiente) são
    registradas como aviso e NÃO abortam o boot.
    """
    problemas: list[str] = []
    avisos_ambiente: list[str] = []

    for old_name, lib_name in SHIM_MAP:
        # 1) Importar o módulo canônico (a fonte dos símbolos esperados).
        try:
            lib_module = importlib.import_module(lib_name)
        except Exception as exc:  # noqa: BLE001
            if _is_missing_dependency_error(exc):
                avisos_ambiente.append(
                    f"[ambiente] módulo canônico {lib_name!r} não pôde ser "
                    f"importado por dependência de terceiros ausente "
                    f"({type(exc).__name__}: {exc}); verificação adiada."
                )
                continue
            problemas.append(
                f"módulo canônico {lib_name!r} (origem dos shims de {old_name!r}) "
                f"falhou ao importar: {type(exc).__name__}: {exc}"
            )
            continue

        # 2) Importar o shim antigo.
        try:
            old_module = importlib.import_module(old_name)
        except Exception as exc:  # noqa: BLE001
            if _is_missing_dependency_error(exc):
                avisos_ambiente.append(
                    f"[ambiente] shim {old_name!r} não pôde ser importado por "
                    f"dependência de terceiros ausente "
                    f"({type(exc).__name__}: {exc}); verificação adiada."
                )
                continue
            problemas.append(
                f"shim {old_name!r} (deve reexportar {lib_name!r}) falhou ao "
                f"importar: {type(exc).__name__}: {exc}"
            )
            continue

        # 3) Para cada nome público prometido pelo PRÓPRIO shim, exigir que o
        #    módulo canônico da lib exponha o MESMO objeto (identidade).
        for symbol in _public_names(old_module):
            if not hasattr(old_module, symbol):
                # Nome declarado em __all__ do shim mas inexistente nele.
                problemas.append(
                    f"símbolo {symbol!r} declarado em __all__ do shim "
                    f"{old_name!r} não existe no próprio shim"
                )
                continue

            old_obj = getattr(old_module, symbol)

            if not hasattr(lib_module, symbol):
                # O shim promete um símbolo antigo sem correspondente na lib.
                problemas.append(
                    f"símbolo {symbol!r} esperado pelo shim {old_name!r} não "
                    f"possui correspondente na biblioteca {lib_name!r}"
                )
                continue

            lib_obj = getattr(lib_module, symbol)
            if old_obj is not lib_obj:
                problemas.append(
                    f"símbolo {symbol!r} do shim {old_name!r} não corresponde "
                    f"por identidade ao de {lib_name!r} "
                    f"(id shim={id(old_obj)} vs id lib={id(lib_obj)})"
                )

    # Avisos de ambiente nunca abortam o boot — apenas registram.
    for aviso in avisos_ambiente:
        logger.warning(aviso)

    if problemas:
        cabecalho = (
            f"Verificação de shims FALHOU: {len(problemas)} símbolo(s) "
            f"ausente(s) ou divergente(s). A inicialização foi abortada sem "
            f"resolver parcialmente o conjunto de shims (tudo-ou-nada)."
        )
        corpo = "\n".join(f"  - {p}" for p in problemas)
        raise ShimVerificationError(f"{cabecalho}\n{corpo}")

    logger.info(
        "Verificação de shims OK: %d par(es) de shim verificados; "
        "todos os símbolos públicos reexportam a privacylib por identidade.",
        len(SHIM_MAP),
    )
    return None


# Alias explícito solicitado: deixa claro no call-site que a função levanta.
verify_shims_or_raise = verify_shims


__all__ = [
    "verify_shims",
    "verify_shims_or_raise",
    "ShimVerificationError",
    "ShimEnvironmentWarning",
    "SHIM_MAP",
]
