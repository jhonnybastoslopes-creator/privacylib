"""Marketplace de extensões (domínio).

Fase B da migração (inversão): a lógica real dos 8 submódulos de marketplace
agora vive AQUI, em ``privacylib/extensions/*``. Os antigos módulos
``functions/extensions/*`` passaram a ser shims que reexportam por identidade os
símbolos deste pacote.

Submódulos expostos (Requirement 14):

- ``catalog``        → ``privacylib.extensions.catalog``
- ``subscriptions``  → ``privacylib.extensions.subscriptions``
- ``pricing``        → ``privacylib.extensions.pricing``
- ``payments``       → ``privacylib.extensions.payments``
- ``qr``             → ``privacylib.extensions.qr``
- ``logs``           → ``privacylib.extensions.logs``
- ``migration``      → ``privacylib.extensions.migration``
- ``data_migration`` → ``privacylib.extensions.data_migration``

Garantias:

1. Cada submódulo é acessível como atributo de ``privacylib.extensions`` e
   importável via ``from privacylib.extensions import <submódulo>``.
3. Como os shims em ``functions.extensions.*`` reexportam deste pacote por
   identidade, vale ``functions.extensions.catalog.<nome> is
   privacylib.extensions.catalog.<nome>``.
4. Se **qualquer** um dos 8 submódulos falhar ao importar, o import de
   ``privacylib.extensions`` falha com ``ImportError`` que **identifica o
   submódulo afetado**, sem expor um conjunto parcial de submódulos.

Nota: ``access`` NÃO pertence a este pacote — ele vive em ``privacylib.access``.

_Requirements: 14.1, 14.3
"""

# Nomes dos 8 submódulos de marketplace, na ordem do design/requisito.
_SUBMODULES = (
    "catalog",
    "subscriptions",
    "pricing",
    "payments",
    "qr",
    "logs",
    "migration",
    "data_migration",
)


def _load_submodules():
    """Importa os 8 submódulos deste subpacote (``privacylib.extensions.*``).

    Faz a resolução em um namespace temporário e só o publica no módulo quando
    **todos** os 8 submódulos tiverem sido importados com sucesso. Assim, uma
    falha em qualquer submódulo nunca deixa um conjunto parcial exposto em
    ``privacylib.extensions`` (comportamento tudo-ou-nada).

    Em caso de falha, re-levanta ``ImportError`` identificando o submódulo
    afetado, encadeando a causa original para diagnóstico.
    """
    import importlib

    resolved = {}
    for name in _SUBMODULES:
        try:
            module = importlib.import_module(f"privacylib.extensions.{name}")
        except ImportError as exc:
            raise ImportError(
                f"privacylib.extensions: falha ao importar o submódulo "
                f"{name!r} de 'privacylib.extensions.{name}'; nenhum submódulo "
                f"foi exposto (sem conjunto parcial). Causa: {exc}"
            ) from exc
        resolved[name] = module

    # Todos os 8 resolveram — publica de uma só vez (tudo-ou-nada).
    globals().update(resolved)


_load_submodules()

# ``__all__`` contém exatamente os 8 submódulos expostos.
__all__ = list(_SUBMODULES)
