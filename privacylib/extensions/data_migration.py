"""
privacylib/extensions/data_migration.py — Migração de dados global → por-servidor.

Copia os documentos GLOBAIS existentes (feitos quando o bot era single-server) para
os documentos por-servidor do SERVIDOR RAIZ (`config.json` bot.server), usando o
guild_store. Preserva os documentos globais antigos (rollback seguro — Req 6.5) e é
idempotente (Req 6.3): só copia se o documento por-servidor do raiz ainda não existir.

Não altera documentos verdadeiramente globais (cores, modo, canais, cargos, planos,
marketplace, etc.).

_Requirements: 14.1, 14.3
"""
import time
from privacylib.db.store import database as db
from privacylib.guild import store as gs

_META = "_meta_migracao_multi_servidor"

# Bases de documentos GLOBAIS a migrar para o servidor raiz.
# (a chave por-servidor será f"{base}_{raiz}")
BASES_GLOBAIS = [
    # Loja
    "loja_products", "loja_data", "loja_buys", "loja_roles_temp",
    "loja_stock_notifications", "loja_saldo_config", "loja_saldo_users",
    "loja_customers", "loja_personalization", "loja_doubt_button",
    "loja_preferences", "loja_maintenance",
    # Facção
    "faccao_config", "faccao_registros", "faccao_metas_config",
    "faccao_metas_progresso", "faccao_metas_historico", "faccao_cofre",
    "faccao_cofre_mov", "faccao_penalidades", "faccao_advertencias",
    "faccao_farms", "faccao_ocorrencias", "faccao_banco",
    # Formulário
    "formulario_config", "formulario_respostas",
    # Fists
    "fists_config",
    # Proteção
    "protection_protecaogeral_webhooks", "protection_protecaogeral_expulsoes",
    "protection_protecaogeral_cargos", "protection_protecaogeral_comandosext",
    "protection_protecaogeral_banimentos", "protection_protecaogeral_canais",
    "protection_privatizacoes_urls", "protection_privatizacoes_persistencia",
    "protection_privatizacoes_perms", "protection_privatizacoes_mencoes",
    "protection_privatizacoes_cargos", "protection_privatizacoes_apps",
    # Automações (globais que usam chave fixa)
    "automations_topics", "automations_repost", "automations_msg_auto",
    "automations_nuke", "automations_invite_tracker", "automations_lock_unlock",
    "automations_feedbacks", "automations_feedbacks_log", "automations_cont_vendas",
    "automations_cont_members_call", "automations_cont_members",
    "automations_boas_vindas", "automations_clean", "automations_ai_moderator",
    "automations_ai_chat",
    # Tickets
    "tickets_config", "tickets_data", "tickets_calls",
]


def _raiz_guild_id() -> str | None:
    cfg = db.obter("config.json") or {}
    return cfg.get("bot", {}).get("server")


def ja_migrado() -> bool:
    meta = db.get_document(_META)
    return bool(isinstance(meta, dict) and meta.get("done"))


def migrar_dados_por_servidor(force: bool = False) -> dict:
    """
    Executa a migração dos dados globais para o servidor raiz.
    Idempotente: se já migrado (e não force), não faz nada.
    Retorna resumo {"copiados": N, "ignorados": N, "raiz": guild_id}.
    """
    if ja_migrado() and not force:
        return {"copiados": 0, "ignorados": 0, "raiz": _raiz_guild_id(), "status": "ja_migrado"}

    raiz = _raiz_guild_id()
    if not raiz:
        return {"copiados": 0, "ignorados": 0, "raiz": None, "status": "sem_raiz"}

    copiados = 0
    ignorados = 0
    fases = []

    for base in BASES_GLOBAIS:
        # Documento global antigo
        global_doc = db.get_document(base)
        # Documento por-servidor do raiz (destino)
        destino = gs.get(base, raiz, default=None)

        # Só copia se há dado global e o destino ainda está vazio (idempotência)
        tem_global = bool(global_doc) and global_doc != {}
        tem_destino = bool(destino) and destino != {}

        if tem_global and not tem_destino:
            gs.save(base, raiz, global_doc)
            copiados += 1
            fases.append(base)
        else:
            ignorados += 1

    # Migração especial: sorteios do arquivo JSON local → documento MongoDB por-servidor.
    # Tira o peso do disco da VM e isola por servidor (bot leve/autossustentável).
    try:
        import os
        import json as _json
        arq = "database/giveaways/giveaways_data.json"
        destino_gv = gs.get("giveaways_data", raiz, default=None)
        if os.path.exists(arq) and not (destino_gv and destino_gv != {}):
            with open(arq, "r", encoding="utf-8") as f:
                gv_data = _json.load(f)
            if gv_data:
                gs.save("giveaways_data", raiz, gv_data)
                copiados += 1
                fases.append("giveaways_data")
    except Exception as _gv_err:
        print(f"[MULTI_SRV] Aviso ao migrar giveaways do JSON: {_gv_err}")

    # Marca o estado (preserva os globais antigos — rollback seguro)
    db.save_document(_META, {
        "done": True,
        "at": int(time.time()),
        "raiz": str(raiz),
        "copiados": copiados,
        "bases": fases,
    })

    print(f"[MULTI_SRV] Migração de dados concluída: {copiados} copiados para o raiz {raiz}, "
          f"{ignorados} ignorados.")
    return {"copiados": copiados, "ignorados": ignorados, "raiz": raiz, "status": "ok"}
