"""Classe ``database`` (camada de dados / infra): CRUD de documentos + cache.

Fase B da migração: a implementação **real** da classe ``database`` agora mora
aqui, em ``privacylib/db/store.py``. O módulo antigo ``functions/database.py``
passou a ser um *shim* de compatibilidade que reexporta ``database`` daqui por
identidade.

Como a classe mantém o cache em um atributo de nível de classe
(``database._cache``, protegido por ``database._cache_lock``), haver uma única
definição de classe garante automaticamente um **único cache compartilhado** em
memória — o shim apenas reexporta a mesma referência de classe.

Garante (Fase B):

    functions.database.database is privacylib.db.store.database
    privacylib.db.store.db       is privacylib.db.store.database
    privacylib.db.db             is functions.database.database

A API pública preservada da classe ``database`` inclui:
    - síncronos: ``get_document``, ``get_documents``, ``save_document``,
      ``delete_document``, ``delete_documents``, ``obter``, ``salvar``
    - assíncronos: ``async_get_document``, ``async_save_document``
    - infra/cache: ``clear_cache``, ``get_cache_stats``,
      ``initialize_database_if_needed``, ``verify_and_create_missing_documents``

_Requirements: 14.1, 14.3, 14.4, 12.1, 16.1, 16.2, 16.3, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_
"""

import json
import os
import time
import threading
import copy
from typing import Optional, Any
from privacylib.db.mongo import collection as bot_collection

class database:
    # Cache em memória para documentos frequentemente acessados
    _cache: dict[str, tuple[Any, float]] = {}
    _cache_lock = threading.Lock()
    _default_ttl = 60  # 60 segundos por padrão
    
    # Documentos que devem ser cacheados por mais tempo (configurações raramente alteradas)
    _long_cache_docs = {
        # Núcleo / aparência
        "custom_mode",
        "custom_colors",
        "custom_info",
        "canais",
        "cargos",
        # Tickets
        "tickets_config",
        # Loja
        "loja_config",
        "loja_products",
        "loja_categories",
        "loja_coupons",
        # Automações / proteção / settings
        "automations_config",
        "protection_config",
        "settings_config",
        "giveaways_config",
        "youtube_config",
        "rendimentos_config",
        "server_plans",
        # Marketplace de Extensões
        "ext_catalog",
        "ext_subscriptions",
        "ext_pricing_config",
        "ext_payment_config",
        # Facção — consultados em todo clique de botão
        "faccao_config",
        "faccao_metas_config",
        "faccao_penalidades",
        "faccao_advertencias",
        "faccao_cofre",
        "faccao_registros",
        "faccao_farms",
        "faccao_ocorrencias",
        "faccao_metas_progresso",
        "faccao_banco",
        "faccao_cofre_mov",
        "faccao_metas_historico",
    }
    _long_cache_ttl = 600  # 10 minutos para documentos de configuração

    @staticmethod
    def _is_long_cache(config_type: str) -> bool:
        """
        True se o documento deve usar o cache de longa duração. Reconhece tanto as
        chaves globais quanto as por-servidor (ex.: 'faccao_config_123' → base
        'faccao_config' está em _long_cache_docs).
        """
        if config_type in database._long_cache_docs:
            return True
        # Chaves por-servidor: base + "_" + guild_id. Verifica se a base é de long cache.
        for base in database._long_cache_docs:
            if config_type.startswith(base + "_"):
                return True
        return False

    @staticmethod
    def obter(filename: str):
        try:
            with open(f"{filename}", "r", encoding="utf-8") as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

        # Segurança: injeta o token do ambiente (.env) ao ler config.json.
        # Assim o token não precisa ficar em texto puro no arquivo.
        # Aceita BOT_TOKEN, TOKEN ou DISCORD_TOKEN (nome padrão do .env).
        if isinstance(data, dict) and filename.replace("\\", "/").endswith("config.json"):
            env_token = (
                os.environ.get("BOT_TOKEN")
                or os.environ.get("TOKEN")
                or os.environ.get("DISCORD_TOKEN")
            )
            if env_token:
                data["botToken"] = env_token
                if isinstance(data.get("bot"), dict):
                    data["bot"]["token"] = env_token
        return data
    
    @staticmethod
    def salvar(filename: str, data: dict):
        with open(f"{filename}", "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)

    @staticmethod
    def get_document(config_type: str):
        """
        Obtém um documento de configuração específico do bot.
        Usa cache em memória para melhorar performance.
        config_type é usado como _id do documento.
        Retorna um dicionário vazio ou lista vazia se nenhum documento for encontrado.
        
        Se o documento contém apenas a chave 'items' (além de _id), retorna a lista diretamente.
        """
        current_time = time.time()
        
        # Verificar cache primeiro
        with database._cache_lock:
            if config_type in database._cache:
                cached_data, expiry_time = database._cache[config_type]
                if current_time < expiry_time:
                    # Cache válido, retornar cópia profunda para evitar mutação
                    return copy.deepcopy(cached_data)
        
        # Cache não encontrado ou expirado, buscar do MongoDB
        try:
            document = bot_collection.find_one({"_id": config_type})
            if document:
                # Remove o _id para manter compatibilidade
                doc_copy = document.copy()
                doc_copy.pop("_id", None)
                
                # Se o documento tem apenas 'items', retornar a lista diretamente
                if len(doc_copy) == 1 and "items" in doc_copy:
                    result = doc_copy["items"]
                else:
                    result = doc_copy
                
                # Armazenar no cache (fazer cópia profunda para evitar mutação)
                cached_result = copy.deepcopy(result)
                ttl = database._long_cache_ttl if database._is_long_cache(config_type) else database._default_ttl
                with database._cache_lock:
                    database._cache[config_type] = (cached_result, current_time + ttl)
                
                # Retornar cópia profunda para evitar mutação
                return copy.deepcopy(result)
            
            # Documento não encontrado, cachear resultado vazio por menos tempo
            empty_result = {}
            with database._cache_lock:
                database._cache[config_type] = (empty_result, current_time + 10)  # 10 segundos para "não encontrado"
            return empty_result
            
        except Exception as e:
            # Em caso de erro (MongoDB indisponível), tentar carregar do arquivo local se existir
            print(f"[AVISO] Erro ao buscar documento '{config_type}' do MongoDB: {e}")
            # Tentar carregar de arquivo local como fallback
            try:
                local_file = f"database/automations/{config_type}.json"
                if os.path.exists(local_file):
                    with open(local_file, "r", encoding="utf-8") as f:
                        return json.load(f)
            except:
                pass
            return {}

    @staticmethod
    def get_documents(query: dict = None):
        """
        Obtém múltiplos documentos de configuração do bot.
        Retorna uma lista de dicionários.
        """
        if query is None:
            query = {}
        documents = list(bot_collection.find(query))
        # Remove o _id de cada documento
        for doc in documents:
            doc.pop("_id", None)
        return documents

    @staticmethod
    def delete_document(config_type: str):
        """
        Deleta um documento de configuração específico do bot.
        """
        bot_collection.delete_one({"_id": config_type})
        # Invalidar cache
        with database._cache_lock:
            database._cache.pop(config_type, None)

    @staticmethod
    def delete_documents(query: dict):
        """
        Deleta múltiplos documentos de configuração do bot.
        """
        # Buscar IDs dos documentos que serão deletados para invalidar cache
        documents_to_delete = list(bot_collection.find(query, {"_id": 1}))
        deleted_ids = [doc["_id"] for doc in documents_to_delete]
        
        bot_collection.delete_many(query)
        
        # Invalidar cache dos documentos deletados
        with database._cache_lock:
            for doc_id in deleted_ids:
                database._cache.pop(doc_id, None)
        
    @staticmethod
    def save_document(config_type: str, query_or_data=None, data=None):
        """
        Salva um documento de configuração do bot (atualiza se existir, insere se não).
        config_type é usado como _id do documento.
        
        Aceita duas assinaturas para retrocompatibilidade:
        - save_document(config_type, data) - Nova assinatura
        - save_document(config_type, {}, data) - Assinatura antiga (query ignorado)
        
        Suporta tanto dicionários quanto listas.
        """
        # Se data é None, então query_or_data é o data (nova assinatura)
        if data is None:
            data = query_or_data
        # Caso contrário, query_or_data é o query (ignorado) e data é o terceiro argumento
        
        # Se data é uma lista, encapsular em um dicionário
        if isinstance(data, list):
            document = {
                "_id": config_type,
                "items": data
            }
            cache_data = data
        else:
            # Se é um dicionário, copiar e adicionar _id
            data_copy = data.copy()
            data_copy["_id"] = config_type
            document = data_copy
            # Para cache, remover _id novamente
            cache_data = {k: v for k, v in data_copy.items() if k != "_id"}
            # Se o documento tem apenas 'items', retornar a lista diretamente
            if len(cache_data) == 1 and "items" in cache_data:
                cache_data = cache_data["items"]
        
        # Atualizar cache IMEDIATAMENTE (leituras seguintes já veem o valor novo)
        current_time = time.time()
        ttl = database._long_cache_ttl if database._is_long_cache(config_type) else database._default_ttl
        cached_data = copy.deepcopy(cache_data)
        with database._cache_lock:
            database._cache[config_type] = (cached_data, current_time + ttl)

        # Persistir no MongoDB. Se houver um event loop rodando (contexto async do bot),
        # delega a escrita para uma thread em background para NÃO bloquear o event loop.
        def _persist():
            try:
                bot_collection.replace_one({"_id": config_type}, document, upsert=True)
            except Exception as e:
                print(f"[AVISO] Erro ao salvar documento '{config_type}' no MongoDB: {e}")
                try:
                    os.makedirs("database/automations", exist_ok=True)
                    local_file = f"database/automations/{config_type}.json"
                    with open(local_file, "w", encoding="utf-8") as f:
                        json.dump(cache_data, f, indent=4, ensure_ascii=False)
                except Exception as local_error:
                    print(f"[ERRO] Não foi possível salvar localmente: {local_error}")

        try:
            import asyncio as _asyncio
            loop = _asyncio.get_running_loop()
            # Há event loop ativo → roda a escrita em thread para não travar o bot
            loop.run_in_executor(None, _persist)
        except RuntimeError:
            # Sem event loop (ex: boot/scripts) → escreve de forma síncrona normal
            _persist()

    @staticmethod
    def initialize_database_if_needed():
        """
        Verifica se o bot já foi inicializado. Se não, popula a coleção do bot
        com o arquivo consolidado 'database_template.json'.
        Cada chave do JSON vira um documento com _id = nome da chave.
        """
        try:
            initialization_doc = bot_collection.find_one({"_id": "_meta_initialization"})
        except Exception as e:
            print(f"[AVISO] Não foi possível conectar ao MongoDB: {e}")
            print("[AVISO] O bot continuará sem conexão com banco de dados (modo limitado)")
            return

        if initialization_doc:
            # O bot já foi inicializado, não faz nada.
            return

        print("Primeira inicialização detectada. Populando a coleção do bot com valores padrão...")

        template_file = "database_template.json"
        
        try:
            with open(template_file, "r", encoding="utf-8") as f:
                all_configs = json.load(f)
            
            for config_type, default_data in all_configs.items():
                try:
                    if isinstance(default_data, list):
                        # Se for lista, salva como um documento com a lista dentro
                        database.save_document(config_type, {"items": default_data})
                        print(f" - Config '{config_type}' inicializada com {len(default_data)} itens.")
                    else:
                        # Se for dict, salva diretamente
                        database.save_document(config_type, default_data)
                        print(f" - Config '{config_type}' inicializada com sucesso.")
                
                except Exception as e:
                    print(f"Erro ao inicializar a config '{config_type}': {e}")
            
            # Marca que a inicialização foi concluída para não rodar novamente.
            bot_collection.insert_one({
                "_id": "_meta_initialization",
                "initialized_at": os.path.getmtime(template_file)
            })
            print("Inicialização da coleção do bot concluída.")
        
        except FileNotFoundError:
            print(f"ERRO: Arquivo '{template_file}' não encontrado!")
        except json.JSONDecodeError as e:
            print(f"ERRO: Arquivo '{template_file}' contém JSON inválido: {e}")

    @staticmethod
    def verify_and_create_missing_documents():
        """
        Verifica se todos os documentos do template existem na database.
        Se algum estiver faltando, cria com os valores padrão do template.
        Executa toda vez que o bot inicia.
        """
        template_file = "database_template.json"
        
        try:
            with open(template_file, "r", encoding="utf-8") as f:
                all_configs = json.load(f)
        except Exception as e:
            print(f"[MongoDB] ERRO ao ler template: {e}")
            return

        try:
            missing_count = 0
            for config_type, default_data in all_configs.items():
                # Verifica se o documento existe
                existing_doc = bot_collection.find_one({"_id": config_type})
                
                if not existing_doc:
                    # Documento não existe, criar com valores padrão
                    try:
                        if isinstance(default_data, list):
                            database.save_document(config_type, {"items": default_data})
                            print(f"[MongoDB] Documento faltante '{config_type}' criado com {len(default_data)} itens.")
                        else:
                            database.save_document(config_type, default_data)
                            print(f"[MongoDB] Documento faltante '{config_type}' criado com sucesso.")
                        missing_count += 1
                    except Exception as e:
                        print(f"[MongoDB] Erro ao criar documento '{config_type}': {e}")
            
            if missing_count > 0:
                print(f"[MongoDB] {missing_count} documento(s) faltante(s) foi(ram) criado(s).")
            else:
                print("[MongoDB] Todos os documentos do template estão presentes na database.")
        
        except FileNotFoundError:
            print(f"[MongoDB] ERRO: Arquivo '{template_file}' não encontrado!")
        except json.JSONDecodeError as e:
            print(f"[MongoDB] ERRO: Arquivo '{template_file}' contém JSON inválido: {e}")
        except Exception as e:
            print(f"[MongoDB] ERRO ao verificar documentos: {e}")
    
    @staticmethod
    def clear_cache(config_type: Optional[str] = None):
        """
        Limpa o cache de documentos.
        
        Args:
            config_type: Se fornecido, limpa apenas o cache deste documento.
                        Se None, limpa todo o cache.
        """
        with database._cache_lock:
            if config_type:
                database._cache.pop(config_type, None)
            else:
                database._cache.clear()
    
    @staticmethod
    def get_cache_stats() -> dict:
        """
        Retorna estatísticas do cache.
        """
        with database._cache_lock:
            current_time = time.time()
            valid_entries = sum(1 for _, (_, expiry) in database._cache.items() if current_time < expiry)
            expired_entries = len(database._cache) - valid_entries
            return {
                "total_entries": len(database._cache),
                "valid_entries": valid_entries,
                "expired_entries": expired_entries,
                "cached_documents": list(database._cache.keys())
            }

    # ── Versões assíncronas (não bloqueiam o event loop) ──────────────────────

    @staticmethod
    async def async_get_document(config_type: str):
        """
        Versão assíncrona de get_document.
        Verifica cache primeiro (síncrono, rápido).
        Se cache miss, roda a query MongoDB em asyncio.to_thread para não bloquear o event loop.
        """
        import asyncio

        current_time = time.time()

        # Verificar cache primeiro (operação rápida, sem I/O)
        with database._cache_lock:
            if config_type in database._cache:
                cached_data, expiry_time = database._cache[config_type]
                if current_time < expiry_time:
                    return copy.deepcopy(cached_data)

        # Cache miss — buscar do MongoDB em thread separada
        def _fetch():
            try:
                document = bot_collection.find_one({"_id": config_type})
                if document:
                    doc_copy = document.copy()
                    doc_copy.pop("_id", None)
                    if len(doc_copy) == 1 and "items" in doc_copy:
                        result = doc_copy["items"]
                    else:
                        result = doc_copy
                    cached_result = copy.deepcopy(result)
                    ttl = database._long_cache_ttl if database._is_long_cache(config_type) else database._default_ttl
                    ts = time.time()
                    with database._cache_lock:
                        database._cache[config_type] = (cached_result, ts + ttl)
                    return copy.deepcopy(result)
                # Não encontrado
                with database._cache_lock:
                    database._cache[config_type] = ({}, time.time() + 10)
                return {}
            except Exception as e:
                print(f"[AVISO] async_get_document '{config_type}': {e}")
                # Tentar fallback local
                try:
                    local_file = f"database/automations/{config_type}.json"
                    if os.path.exists(local_file):
                        with open(local_file, "r", encoding="utf-8") as f:
                            import json as _json
                            return _json.load(f)
                except Exception:
                    pass
                return {}

        return await asyncio.to_thread(_fetch)

    @staticmethod
    async def async_save_document(config_type: str, query_or_data=None, data=None):
        """
        Versão assíncrona de save_document.
        Atualiza o cache imediatamente e persiste no MongoDB em thread separada.
        """
        import asyncio

        if data is None:
            data = query_or_data

        if isinstance(data, list):
            document = {"_id": config_type, "items": data}
            cache_data = data
        else:
            data_copy = data.copy()
            data_copy["_id"] = config_type
            document = data_copy
            cache_data = {k: v for k, v in data_copy.items() if k != "_id"}
            if len(cache_data) == 1 and "items" in cache_data:
                cache_data = cache_data["items"]

        # Atualizar cache imediatamente (não espera o MongoDB)
        current_time = time.time()
        ttl = database._long_cache_ttl if database._is_long_cache(config_type) else database._default_ttl
        with database._cache_lock:
            database._cache[config_type] = (copy.deepcopy(cache_data), current_time + ttl)

        # Persistir no MongoDB em thread separada
        doc_to_save = copy.deepcopy(document)

        def _save():
            try:
                bot_collection.replace_one({"_id": config_type}, doc_to_save, upsert=True)
            except Exception as e:
                print(f"[AVISO] async_save_document '{config_type}': {e}")
                try:
                    os.makedirs("database/automations", exist_ok=True)
                    local_file = f"database/automations/{config_type}.json"
                    with open(local_file, "w", encoding="utf-8") as f:
                        import json as _json
                        _json.dump(cache_data, f, indent=4, ensure_ascii=False)
                except Exception:
                    pass

        await asyncio.to_thread(_save)


# Alias de conveniência: mesma referência de classe (identidade preservada).
db = database

__all__ = ["database", "db"]
