"""privacylib — biblioteca core unificada do PrivacyBOT.

Fachada raiz estável. Expõe, como atributos do módulo, exatamente os nove
símbolos públicos de maior acoplamento do bot, organizados em três camadas:

- Infraestrutura: ``db``, ``guild``, ``errors``
- Apresentação:   ``ui``, ``emoji``, ``utils``
- Domínio:        ``access``, ``perms``, ``extensions``

Regras garantidas por esta fachada (Requirement 1):

1. Os nove símbolos existem como atributos do módulo e são não nulos.
2. ``__all__`` contém exatamente esses nove símbolos.
3. Importar qualquer um dos nove não gera ``ImportError``.
4. Acessar qualquer nome fora dos nove levanta ``AttributeError`` (ver
   ``__getattr__`` ao final deste módulo).

Ordem de import (Requirement 15.2): os imports em tempo de módulo seguem o
sentido infraestrutura → apresentação → domínio. Como a fachada é a camada mais
externa (o topo que o bot consome), ela pode importar de todas as camadas
inferiores sem criar ciclos: nenhum submódulo de ``privacylib`` importa a
fachada raiz em tempo de módulo.

_Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 15.2, 15.3_
"""

# ---------------------------------------------------------------------------
# Contrato público da fachada
# ---------------------------------------------------------------------------
#
# Resolução LAZY dos nove símbolos (PEP 562).
#
# A partir da Fase B, ``functions/database.py`` virou um shim que carrega
# ``privacylib.db.store`` e, por isso, qualquer import de um submódulo de
# ``privacylib`` executa este ``__init__``. Se a fachada importasse
# ansiosamente (eager) todas as camadas (db → guild → ui → emoji → utils →
# access → extensions) em tempo de módulo, o grafo inteiro do bot seria puxado
# no meio da inicialização de ``functions.database``, recriando o ciclo de
# import que a migração busca evitar (Requisito 15.3: imports tardios para
# quebrar ciclos infra↔apresentação↔domínio).
#
# Para preservar o contrato público (os nove atributos existem, são não nulos,
# ``__all__`` contém exatamente eles e nomes desconhecidos levantam
# ``AttributeError``) sem forçar o carregamento ansioso do grafo, cada símbolo é
# resolvido na primeira vez que é acessado, via ``__getattr__`` do módulo.
#
# _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 15.2, 15.3_

__all__ = [
    # Infra
    "db",
    "guild",
    "errors",
    # Apresentação
    "ui",
    "emoji",
    "utils",
    # Domínio
    "access",
    "perms",
    "extensions",
]


def _resolve(name: str):
    """Carrega e retorna o símbolo público ``name`` da fachada (sob demanda).

    A ordem de resolução respeita as camadas (infra → apresentação → domínio),
    mas o carregamento só acontece quando o símbolo é efetivamente acessado,
    evitando o ciclo de import em tempo de módulo.

    Importante: usamos ``importlib.import_module`` para carregar os subpacotes
    (``privacylib.db``, ``privacylib.guild``, ...) em vez de ``from privacylib
    import X``. O segundo faria uma *busca de atributo* no pacote ``privacylib``,
    que recairia neste mesmo ``__getattr__`` e geraria recursão infinita.
    """
    import importlib

    # Infra
    if name == "db":
        return importlib.import_module("privacylib.db").db
    if name == "guild":
        return importlib.import_module("privacylib.guild")
    if name == "errors":
        return importlib.import_module("privacylib.errors")
    # Apresentação
    if name == "ui":
        return importlib.import_module("privacylib.ui")
    if name == "emoji":
        try:
            return importlib.import_module("privacylib.emoji").emoji
        except (ImportError, AttributeError):
            return importlib.import_module("functions.emoji").emoji
    if name == "utils":
        try:
            return importlib.import_module("privacylib.utils").utils
        except (ImportError, AttributeError):
            return importlib.import_module("functions.utils").utils
    # Domínio
    if name == "access":
        return importlib.import_module("privacylib.access")
    if name == "perms":
        return importlib.import_module("privacylib.access.perms").perms
    if name == "extensions":
        return importlib.import_module("privacylib.extensions")
    return None


def __getattr__(name: str):
    """Resolve os nove símbolos sob demanda; rejeita qualquer outro nome.

    Chamado pelo Python apenas quando ``name`` não é um atributo já definido
    no módulo (PEP 562). Na primeira vez que um dos nove símbolos é acessado,
    ele é carregado, cacheado como atributo real do módulo (para acessos
    subsequentes O(1)) e retornado. Qualquer outro nome resulta em
    ``AttributeError`` (Requirement 1.4).
    """
    if name in __all__:
        obj = _resolve(name)
        # Cacheia como atributo real do módulo: próximos acessos não passam mais
        # por __getattr__ e a identidade do objeto é preservada.
        globals()[name] = obj
        return obj
    raise AttributeError(
        f"module 'privacylib' has no attribute {name!r}; "
        f"a fachada expõe apenas {__all__}"
    )


def __dir__():
    """Inclui os nove símbolos públicos no ``dir(privacylib)``."""
    return sorted(set(list(globals().keys()) + __all__))
