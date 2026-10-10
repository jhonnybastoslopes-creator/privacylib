"""Camada de dados (infra): conexão Mongo e classe ``database`` com cache.

Fase A da migração. Esta fachada expõe o alias ``db`` (classe ``database``) que
a fachada raiz ``privacylib`` reexporta, conforme a seção de componentes do
design.

A fonte dedicada ``privacylib/db/store.py`` (tarefa 2.2) reexporta por
identidade a classe ``database`` de ``functions/database.py`` e define o alias
``db = database``. Esta fachada apenas repassa esses símbolos, de modo que o
import exato do design (``from privacylib.db import db``) resolva pela origem
pretendida.

Garante (Fase A):

    privacylib.db.db       is functions.database.database
    privacylib.db.database is functions.database.database
    privacylib.db.db       is privacylib.db.store.database

_Requirements: 2.2, 2.5_
"""

from privacylib.db.store import database, db  # noqa: F401

__all__ = ["db", "database"]
