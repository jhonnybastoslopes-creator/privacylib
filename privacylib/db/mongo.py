"""Conexão com o MongoDB (camada de dados / infra).

Fase B da migração: a lógica **real** de conexão com o MongoDB agora mora aqui,
em ``privacylib/db/mongo.py``. O módulo antigo ``connections/mongo_db.py`` passou
a ser um *shim* de compatibilidade que reexporta estes mesmos objetos por
identidade.

Comportamento preservado EXATAMENTE em relação ao módulo original:

    - Lê ``config.json`` (chave ``botID``) via ``json.load`` direto do arquivo.
    - Lê ``configs/config_mongo.json`` (chaves ``mongoURL`` e ``databaseName``,
      com padrão ``"sync_bots"``) via ``json.load`` direto do arquivo.
    - Cria o cliente com ``pymongo.MongoClient(mongo_url)`` (conexão preguiçosa
      do próprio pymongo — nada é conectado em tempo de import).
    - Define ``database = client[database_name]`` e ``collection = database[bot_id]``.

Observação sobre ciclos: a leitura de configuração é feita por ``json.load``
direto dos arquivos (exatamente como o módulo original fazia), sem passar por
``functions.database``/``privacylib.db.store``. Como ``privacylib.db.store``
importa ``collection`` daqui, usar ``json`` direto evita qualquer ciclo de
import entre ``store`` e ``mongo``.

Garante que:

    privacylib.db.mongo.client     is connections.mongo_db.client
    privacylib.db.mongo.database   is connections.mongo_db.database
    privacylib.db.mongo.collection is connections.mongo_db.collection

_Requirements: 2.1, 14.1, 14.3, 16.1_
"""

import json

import pymongo

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

with open("configs/config_mongo.json", "r", encoding="utf-8") as f:
    mongo_config = json.load(f)

mongo_url = mongo_config.get("mongoURL")
bot_id = config.get("botID")
database_name = mongo_config.get("databaseName", "sync_bots")

client = pymongo.MongoClient(mongo_url)
database = client[database_name]
collection = database[bot_id]

__all__ = ["client", "database", "collection"]
