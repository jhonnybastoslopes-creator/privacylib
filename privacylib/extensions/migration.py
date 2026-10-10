"""
privacylib/extensions/migration.py — Migração dos Planos antigos para Extensões.

Converte o modelo antigo (server_plans: gratis/classico/plus) para assinaturas de
extensões, preservando a data de expiração vigente (Req 9). Idempotente: marca cada
servidor migrado com a flag `_migrado_ext` para não duplicar.

Não remove dados de configuração dos módulos (Req 9.2). Grátis fica só no núcleo.

_Requirements: 14.1, 14.3
"""
import time
from privacylib.db.store import database as db
from privacylib.extensions import subscriptions, catalog

# Mapa: plano antigo → extensões equivalentes.
# (Tickets básico é núcleo; moderação/tradução/IA são extensões novas e NÃO faziam
#  parte dos planos antigos, então não são atribuídas automaticamente.)
_PLANO_EXTENSOES = {
    "classico": ["automacoes", "formulario"],
    "plus": [
        "automacoes", "formulario", "loja", "sorteios",
        "protecao", "rendimentos", "faccao",
    ],
}


def migrar_planos_para_extensoes(force: bool = False) -> dict:
    """
    Executa a migração. Retorna um resumo:
        {"migrados": N, "ignorados": N, "gratis": N}
    Seguro para reexecutar (idempotente via flag `_migrado_ext`).
    """
    # Garante o catálogo antes de migrar
    try:
        catalog.seed_inicial()
    except Exception:
        pass

    data = db.get_document("server_plans")
    if not isinstance(data, dict) or "plans" not in data:
        return {"migrados": 0, "ignorados": 0, "gratis": 0}

    plans = data.get("plans", {})
    now = int(time.time())
    migrados = ignorados = gratis = 0

    for gid, info in plans.items():
        if not isinstance(info, dict):
            continue

        # Idempotência: já migrado?
        if info.get("_migrado_ext") and not force:
            ignorados += 1
            continue

        plano = info.get("plan", "gratis")
        expires_at = info.get("expires_at")

        if plano == "gratis" or plano not in _PLANO_EXTENSOES:
            # Grátis (ou plano desconhecido) → sem extensões pagas, só núcleo
            info["_migrado_ext"] = True
            gratis += 1
            continue

        # Calcular dias restantes a partir da expiração vigente (preservar — Req 9.1)
        if expires_at and int(expires_at) > now:
            dias = max(1, (int(expires_at) - now) // 86400)
        else:
            # Plano sem expiração definida → padrão de 30 dias
            dias = 30

        for ext_id in _PLANO_EXTENSOES[plano]:
            # Só migra extensões que existem no catálogo
            if catalog.existe(ext_id):
                subscriptions.ativar(
                    str(gid), ext_id, dias,
                    via="migracao_plano", payment_id=f"mig_{gid}_{ext_id}",
                )

        info["_migrado_ext"] = True
        info["_migrado_em"] = now
        migrados += 1

    data["plans"] = plans
    db.save_document("server_plans", data)

    print(f"[EXT_MIGRATION] Migração concluída: {migrados} migrados, "
          f"{gratis} grátis, {ignorados} já migrados.")
    return {"migrados": migrados, "ignorados": ignorados, "gratis": gratis}
