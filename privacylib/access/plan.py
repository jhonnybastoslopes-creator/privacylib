"""Planos do bot (domínio) — LEGADO — Fase B: implementação canônica.

A implementação real do sistema de planos **legado** foi movida de
``functions/plan.py`` para este módulo. O comportamento é preservado EXATAMENTE:
plano global lido de ``configs/config_plan.json`` e planos por servidor em
``server_plans`` (com expiração automática). Nenhuma regra foi alterada.

O antigo ``functions/plan.py`` passou a ser um shim que reexporta todos os
símbolos públicos daqui por identidade, de modo que:

    functions.plan.get_plan is privacylib.access.plan.get_plan

Marcação de LEGADO: estas funções pertencem ao sistema de planos herdado do bot.
São mantidas por compatibilidade retroativa e não devem ser consideradas a
interface preferencial de controle de acesso — novos consumidores devem preferir
``privacylib.access`` (marketplace de extensões), conforme o Requirement 9.4.

Cycle-safety (Req 15.3): as dependências de infraestrutura (``functions.database``)
e de domínio (``functions.extensions.access``) usam import tardio dentro das
funções que as consomem, exatamente como no módulo original — nenhum import da
fachada ``privacylib`` ocorre em tempo de carga.

_Requirements: 14.1, 14.3, 9.4, 15.3_
"""

import json
import os

CONFIG_PATH = "configs/config_plan.json"


def get_plan() -> str:
    """
    Obtém o plano atual configurado.

    Returns:
        str: O plano atual ("pro", "basic" ou "cloud")
    """
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("plan", "pro").lower()
    except Exception as e:
        print(f"Erro ao ler configs/config_plan.json: {e}")

    return "pro"  # Default para pro se houver erro


def is_pro() -> bool:
    """Verifica se o plano é Pro (todas funcionalidades)"""
    return get_plan() == "pro"


def is_basic() -> bool:
    """Verifica se o plano é Basic (sem backup e cloud)"""
    return get_plan() == "basic"


def is_cloud() -> bool:
    """Verifica se o plano é Cloud (apenas painel, anunciar e backup)"""
    return get_plan() == "cloud"


def is_free() -> bool:
    """Verifica se o plano é Free (apenas Hydra Wallet como método de pagamento)"""
    return get_plan() == "free"


def should_allow_payment_provider(provider_key: str) -> bool:
    """
    Verifica se um provedor de pagamento pode ser configurado no plano atual.

    Args:
        provider_key: Chave do provedor (ex: "sync_wallet", "mercado_pago", etc)

    Returns:
        bool: True se o provedor é permitido no plano atual
    """
    plan = get_plan()

    if plan == "free":
        # No plano free, apenas Hydra Wallet é permitido
        return provider_key == "sync_wallet"

    # Outros planos permitem todos os provedores
    return True


def should_load_backup() -> bool:
    """Verifica se o módulo de backup deve ser carregado"""
    plan = get_plan()
    return plan in ["pro", "cloud"]


def should_load_cloud() -> bool:
    """Verifica se o módulo cloud deve ser carregado"""
    plan = get_plan()
    return plan in ["pro", "cloud"]


def should_load_module(module_name: str) -> bool:
    """
    Verifica se um módulo específico deve ser carregado baseado no plano.

    Args:
        module_name: Nome do módulo (ex: "automations", "tickets", "settings", "customization", etc)

    Returns:
        bool: True se o módulo deve ser carregado
    """
    plan = get_plan()

    if plan == "pro":
        return True

    if plan == "cloud":
        # No plano cloud, apenas backup, cloud, settings e customization são permitidos
        return module_name in ["backup", "cloud", "settings", "customization"]

    if plan == "basic":
        # No plano basic, todos exceto backup e cloud
        return module_name not in ["backup", "cloud"]

    if plan == "free":
        # No plano free, todos exceto cloud, protection e backup
        return module_name not in ["cloud", "protection", "backup"]

    return True


def should_load_command(command_name: str) -> bool:
    """
    Verifica se um comando específico deve ser carregado baseado no plano.

    Args:
        command_name: Nome do comando (ex: "painel", "backup", "anunciar")

    Returns:
        bool: True se o comando deve ser carregado
    """
    plan = get_plan()

    if plan == "pro":
        return True

    if plan == "cloud":
        # No plano cloud, apenas painel, anunciar e backup
        return command_name in ["painel", "anunciar", "backup"]

    if plan == "basic":
        # No plano basic, todos exceto backup
        return command_name != "backup"

    if plan == "free":
        # No plano free, remover backup e comandos relacionados a cloud/protection se houver
        return command_name not in ["backup", "cloud", "protection"]

    return True


def should_enable_cloud_button() -> bool:
    """Verifica se o botão Hydra Cloud deve estar habilitado no painel"""
    plan = get_plan()
    return plan in ["pro", "cloud"]


def should_enable_panel_button(button_name: str) -> bool:
    """
    Verifica se um botão específico do painel deve estar habilitado.

    Args:
        button_name: Nome do botão do painel (ex: "ticket", "cloud", "personalizacao", etc)

    Returns:
        bool: True se o botão deve estar habilitado
    """
    # Mapeamento: nome do botão -> nome do módulo
    button_to_module = {
        "loja": "loja",
        "ticket": "tickets",
        "cloud": "cloud",
        "personalizacao": "customization",
        "automacoes": "automations",
        "protection": "protection",
        "sorteios": "giveaways",
        "configuracoes": "settings",
        "rendimentos": "rendimentos"
    }

    plan = get_plan()

    if plan == "pro":
        return True

    if plan == "cloud":
        module_name = button_to_module.get(button_name, button_name)
        return module_name in ["cloud", "settings", "customization"]

    if plan == "basic":
        module_name = button_to_module.get(button_name, button_name)
        return module_name != "cloud"

    if plan == "free":
        module_name = button_to_module.get(button_name, button_name)
        return module_name not in ["cloud", "protection", "backup"]

    return True


def should_enable_panel_button_for_server(button_name: str, guild_id: str, user_id: str = None) -> bool:
    """
    Verifica se um botão do painel deve estar habilitado para um servidor específico.

    Delega ao Marketplace de Extensões (functions.extensions.access): o botão fica
    habilitado quando o servidor tem a extensão correspondente ativa, ou quando é o
    dono do bot / servidor raiz. Botões de núcleo ficam sempre habilitados.
    """
    # Mapa: nome do botão do painel → módulo interno de extensão
    botao_para_modulo_ext = {
        "loja": "loja",
        "automacoes": "automacoes",
        "protection": "protecao",
        "sorteios": "sorteios",
        "rendimentos": "rendimentos",
    }
    # Botões de núcleo / configuração / owner-only: sempre habilitados aqui.
    # (personalizacao e configuracoes têm suas próprias regras no painel.)
    nucleo = {"ticket", "configuracoes", "personalizacao", "cloud"}

    try:
        from functions.extensions import access

        # Dono e servidor raiz sempre habilitados
        if user_id and access.is_owner(user_id):
            return True
        if guild_id is not None and access.is_root_guild(guild_id):
            return True

        if button_name in nucleo:
            return True

        modulo = botao_para_modulo_ext.get(button_name)
        if not modulo:
            # Botão desconhecido → habilitar por segurança (não travar UI)
            return True
        return access.pode_usar(guild_id, user_id, modulo)
    except Exception:
        # Fail-open: em caso de erro, não desabilitar o botão
        return True


def should_enable_settings_button(button_name: str) -> bool:
    """
    Verifica se um botão específico de configurações deve estar habilitado.

    Args:
        button_name: Nome do botão (ex: "cargos", "canais", "pagamentos", etc)

    Returns:
        bool: True se o botão deve estar habilitado
    """
    plan = get_plan()

    if plan == "pro":
        return True

    if plan == "cloud":
        # No plano cloud, apenas Cargos e Canais
        return button_name in ["cargos", "canais"]

    if plan == "basic":
        return True

    return True


# ─── Sistema de Planos por Servidor ────────────────────────────────────────────
# Planos: gratis, classico, plus
# Permite vender mensalidade do uso do bot por servidor

PLAN_FEATURES = {
    "gratis": {
        "label": "🆓 Grátis",
        "modules": ["settings", "customization"],
        "commands": ["painel", "mod", "anunciar"],
        "features": ["moderacao_basica", "boas_vindas"],
        "max_tickets": 0,
        "max_products": 0,
        "max_giveaways": 0,
        "canais": [
            "canal_de_boas_vindas",
            "canal_de_logs_do_sistema",
            "canal_de_logs_de_entradas",
            "canal_de_logs_de_saidas",
            "canal_de_logs_de_mensagens",
            "canal_de_logs_de_trafego_em_call",
            "canal_de_logs_de_comandos",
        ],
        "cargos": [
            "cargo_auto_role",
            "cargo_verificado",
        ],
    },
    "classico": {
        "label": "⭐ Clássico",
        "modules": ["settings", "customization", "automations", "tickets"],
        "commands": ["painel", "mod", "anunciar", "tickets"],
        "features": [
            "moderacao_basica", "boas_vindas", "automacoes",
            "tickets", "sugestoes", "formulario", "antilink", "warns",
        ],
        "max_tickets": 5,
        "max_products": 0,
        "max_giveaways": 3,
        "canais": [
            "canal_de_boas_vindas",
            "canal_de_logs_do_sistema",
            "canal_de_logs_de_entradas",
            "canal_de_logs_de_saidas",
            "canal_de_logs_de_mensagens",
            "canal_de_logs_de_trafego_em_call",
            "canal_de_logs_de_comandos",
            "canal_de_logs_de_tickets",
            "canal_de_logs_de_anti_falso",
            "canal_de_logs_de_banimentos",
            "canal_de_logs_de_expulsoes",
            "canal_de_logs_de_castigos",
            "canal_de_feedback",
        ],
        "cargos": [
            "cargo_auto_role",
            "cargo_verificado",
            "cargo_admin",
            "cargo_suporte",
        ],
    },
    "plus": {
        "label": "💎 Plus",
        "modules": [
            "settings", "customization", "automations", "tickets",
            "loja", "giveaways", "protection", "rendimentos", "backup",
        ],
        "commands": [
            "painel", "mod", "anunciar", "tickets", "giveaways",
            "backup", "contextmenus", "function_payment",
        ],
        "features": [
            "moderacao_basica", "boas_vindas", "automacoes",
            "tickets", "sugestoes", "formulario", "antilink", "warns",
            "loja", "giveaways", "protection", "rendimentos", "backup",
        ],
        "max_tickets": -1,
        "max_products": -1,
        "max_giveaways": -1,
        "canais": "__all__",
        "cargos": "__all__",
    },
}


def get_allowed_canais(guild_id: str, user_id: str = None) -> list:
    """Retorna lista de canais permitidos para o plano do servidor."""
    from functions.database import database as db
    config = db.obter("config.json")
    owner_id = config.get("bot", {}).get("owner", "")
    if user_id and str(user_id) == str(owner_id):
        return "__all__"

    plan = get_server_plan(guild_id)
    plan_data = PLAN_FEATURES.get(plan, PLAN_FEATURES["gratis"])
    return plan_data.get("canais", [])


def get_allowed_cargos(guild_id: str, user_id: str = None) -> list:
    """Retorna lista de cargos permitidos para o plano do servidor."""
    from functions.database import database as db
    config = db.obter("config.json")
    owner_id = config.get("bot", {}).get("owner", "")
    if user_id and str(user_id) == str(owner_id):
        return "__all__"

    plan = get_server_plan(guild_id)
    plan_data = PLAN_FEATURES.get(plan, PLAN_FEATURES["gratis"])
    return plan_data.get("cargos", [])


def get_server_plan(guild_id: str) -> str:
    """Obtém o plano de um servidor específico."""
    from functions.database import database as db
    data = db.get_document("server_plans")
    if not data or not isinstance(data, dict):
        return "gratis"
    plan_info = data.get("plans", {}).get(str(guild_id), {})
    return plan_info.get("plan", "gratis")


def server_has_feature(guild_id: str, feature: str) -> bool:
    """Verifica se um servidor tem acesso a uma feature pelo plano."""
    plan = get_server_plan(guild_id)
    plan_data = PLAN_FEATURES.get(plan, PLAN_FEATURES["gratis"])
    return feature in plan_data.get("features", [])


def server_can_load_module(guild_id: str, module_name: str) -> bool:
    """Verifica se um servidor pode usar um módulo."""
    plan = get_server_plan(guild_id)
    plan_data = PLAN_FEATURES.get(plan, PLAN_FEATURES["gratis"])
    return module_name in plan_data.get("modules", [])


def get_plan_label(plan: str) -> str:
    """Retorna o label formatado de um plano."""
    return PLAN_FEATURES.get(plan, {}).get("label", "🆓 Grátis")


# ─── Sistema de Expiração de Planos ───────────────────────────────────────────
import time


def get_server_plan_info(guild_id: str) -> dict:
    """
    Retorna informações completas do plano de um servidor.
    Inclui verificação de expiração.

    Returns:
        dict com: plan, expires_at, expired, label, days_left
    """
    from functions.database import database as db
    data = db.get_document("server_plans")
    if not data or not isinstance(data, dict):
        return {
            "plan": "gratis",
            "expires_at": None,
            "expired": False,
            "label": "🆓 Grátis",
            "days_left": -1,
        }

    plan_info = data.get("plans", {}).get(str(guild_id), {})
    plan = plan_info.get("plan", "gratis")
    expires_at = plan_info.get("expires_at")  # timestamp Unix

    # Plano grátis nunca expira
    if plan == "gratis":
        return {
            "plan": "gratis",
            "expires_at": None,
            "expired": False,
            "label": "🆓 Grátis",
            "days_left": -1,
        }

    # Verifica expiração
    now = int(time.time())
    expired = False
    days_left = -1

    if expires_at:
        if now >= expires_at:
            # Plano expirou → rebaixar para grátis automaticamente
            expired = True
            plans = data.get("plans", {})
            plans[str(guild_id)] = {
                "plan": "gratis",
                "expired_from": plan,
                "expired_at": now,
                "updated_at": now,
            }
            data["plans"] = plans
            db.save_document("server_plans", data)
            return {
                "plan": "gratis",
                "expires_at": expires_at,
                "expired": True,
                "expired_from": plan,
                "label": "🆓 Grátis (Expirado)",
                "days_left": 0,
            }
        else:
            days_left = (expires_at - now) // 86400

    return {
        "plan": plan,
        "expires_at": expires_at,
        "expired": False,
        "label": get_plan_label(plan),
        "days_left": days_left,
    }


def set_server_plan(guild_id: str, plan: str, days: int = 30, set_by: str = None):
    """
    Define o plano de um servidor com duração.

    Args:
        guild_id: ID do servidor
        plan: "gratis", "classico" ou "plus"
        days: Dias de duração (0 = sem expiração)
        set_by: ID de quem definiu
    """
    from functions.database import database as db
    data = db.get_document("server_plans")
    if not data or not isinstance(data, dict):
        data = {"plans": {}}

    now = int(time.time())
    plans = data.get("plans", {})

    plan_entry = {
        "plan": plan,
        "updated_at": now,
        "updated_by": set_by,
    }

    if plan == "gratis" or days == 0:
        plan_entry["expires_at"] = None
    else:
        plan_entry["expires_at"] = now + (days * 86400)

    plans[str(guild_id)] = plan_entry
    data["plans"] = plans
    db.save_document("server_plans", data)


def check_plan_access(guild_id: str, feature: str) -> dict:
    """
    Verifica se o servidor tem acesso a uma feature.
    Retorna dict com resultado e informação para upsell.

    Returns:
        {
            "allowed": bool,
            "current_plan": str,
            "required_plan": str or None,
            "message": str,
        }
    """
    plan_info = get_server_plan_info(guild_id)
    current_plan = plan_info["plan"]
    plan_data = PLAN_FEATURES.get(current_plan, PLAN_FEATURES["gratis"])

    if feature in plan_data.get("features", []):
        return {
            "allowed": True,
            "current_plan": current_plan,
            "required_plan": None,
            "message": "",
        }

    # Encontrar qual plano mínimo precisa
    required = None
    for plan_name in ["classico", "plus"]:
        plan_feats = PLAN_FEATURES[plan_name].get("features", [])
        if feature in plan_feats:
            required = plan_name
            break

    required_label = get_plan_label(required) if required else "💎 Plus"
    current_label = get_plan_label(current_plan)

    return {
        "allowed": False,
        "current_plan": current_plan,
        "required_plan": required,
        "message": (
            f"Esta funcionalidade requer o plano **{required_label}**.\n"
            f"Seu plano atual: **{current_label}**\n\n"
            f"Entre em contato com o dono do bot para ativar."
        ),
    }


__all__ = [
    # Dados legados
    "CONFIG_PATH",
    "PLAN_FEATURES",
    # Plano global (configs/config_plan.json)
    "get_plan",
    "is_pro",
    "is_basic",
    "is_cloud",
    "is_free",
    "should_allow_payment_provider",
    "should_load_backup",
    "should_load_cloud",
    "should_load_module",
    "should_load_command",
    "should_enable_cloud_button",
    "should_enable_panel_button",
    "should_enable_panel_button_for_server",
    "should_enable_settings_button",
    # Planos por servidor (server_plans)
    "get_allowed_canais",
    "get_allowed_cargos",
    "get_server_plan",
    "server_has_feature",
    "server_can_load_module",
    "get_plan_label",
    "get_server_plan_info",
    "set_server_plan",
    "check_plan_access",
]
