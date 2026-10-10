"""Bootstrap e ciclo de vida do bot — implementação canônica da `privacylib`.

Fase B (inversão): a lógica real das funções de ciclo de vida que viviam em
``core/`` foi consolidada neste módulo. Os antigos módulos ``core/*.py`` passaram
a ser shims que reexportam as funções daqui.

Natureza/assinaturas preservadas EXATAMENTE:
    - create_bot()              sync  -> tuple[commands.Bot, str, str]   (core/create_bot.py)
    - change_bio()              sync  -> None                            (core/change_bio.py)
    - change_status(bot)        async -> None                            (core/change_status.py)
    - enable_intents(token, app_id=None) sync -> bool                    (core/enable_intents.py)
    - log_restart(bot)          async -> None                            (core/log_restart.py)
    - apply_server_protection(bot) sync -> None                          (core/server_protection.py)

Além das 6 funções-fachada, preserva os auxiliares públicos que os módulos de
``core/`` expunham (consumidos por outros pontos ou por testes):
    - obter_info, salvar_info      (de core/create_bot.py)
    - get_status_obj, get_status   (de core/change_status.py)
    - get_application_id           (de core/enable_intents.py)
    - get_main_server_id           (de core/server_protection.py)

Imports internos apontam para os locais canônicos da ``privacylib`` quando o
original referenciava ``functions.*`` que hoje são shims.

_Requirements: 14.1, 14.3
"""
import json
import time

import disnake
import requests
from disnake.ext import commands

from privacylib.db.store import database as db
from privacylib.db.store import database
from privacylib.emoji import emoji
from tasks.bot.status_rotator import status_rotator_task


# ─────────────────────────────────────────────────────────────────────────────
# create_bot (core/create_bot.py)
# ─────────────────────────────────────────────────────────────────────────────
def obter_info():
        data = db.obter("config.json")

        # Se apiURL estiver vazio, não tentar fazer requisição
        if not data.get('apiURL'):
            print("[ObterInfo] apiURL não configurado, usando configuração local")
            return data.get('bot', {})

        headers = {"authorization": data['botToken'], "content-type": "application/json"}
        url = f"{data['apiURL']}/api/bot/{data['botID']}/info"

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()

        print(f"[ObterInfo] Erro na requisição. Status: {response.status_code}")
        exit(1)


def salvar_info(info: dict):
    config_db = db.obter("config.json")
    config_db["bot"] = {k: info[k] for k in ("token", "owner", "id", "perms", "server")}
    if "version" in info:
        config_db["version"] = info["version"]
    db.salvar("config.json", config_db)


def create_bot() -> tuple[commands.Bot, str, str]:
    config_db = db.obter("config.json")
    if config_db["saveConfig"] == True:
        info = obter_info()
        salvar_info(info)
    else:
        info = config_db["bot"]

    intents = disnake.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.guilds = True

    # test_guilds=None → comandos GLOBAIS (aparecem em todos os servidores).
    # (Antes era test_guilds=[servidor raiz], o que fazia os comandos só existirem
    #  no servidor principal — por isso /painel não aparecia em outros servidores.)
    # Nota: comandos globais podem levar até ~1h para propagar na primeira vez.
    bot = commands.Bot(
        command_prefix=commands.when_mentioned,
        intents=intents,
        help_command=None,
        reload=True,
        test_guilds=None,
    )
    return bot, info["token"], info["id"]


# ─────────────────────────────────────────────────────────────────────────────
# change_bio (core/change_bio.py)
# ─────────────────────────────────────────────────────────────────────────────
def change_bio():
    database_cfg = db.obter("config.json")
    token = database_cfg["bot"]["token"]
    id = database_cfg["bot"]["id"]

    description = (
        f"{emoji.priv_1}{emoji.priv_2}{emoji.priv_3}{emoji.priv_4}{emoji.priv_5}"
    )

    url = f"https://discord.com/api/v9/applications/{id}"
    headers = {
        "authorization": f"Bot {token}",
        "content-type": "application/json",
    }
    payload = {
        "description": description
    }

    requests.patch(url, headers=headers, json=payload)


# ─────────────────────────────────────────────────────────────────────────────
# change_status (core/change_status.py)
# ─────────────────────────────────────────────────────────────────────────────
def get_status_obj(status_type: str) -> disnake.Status:
    status_map = {
        "online": disnake.Status.online,
        "idle": disnake.Status.idle,
        "dnd": disnake.Status.dnd,
        "streaming": disnake.Status.streaming
    }
    return status_map.get(status_type, disnake.Status.online)


async def change_status(bot: commands.Bot):
    if not status_rotator_task.is_running():
        status_rotator_task.start(bot)


def get_status() -> disnake.Status:
    database_doc = db.get_document("custom_status")
    return get_status_obj(database_doc.get("type", "online"))


# ─────────────────────────────────────────────────────────────────────────────
# enable_intents (core/enable_intents.py)
# ─────────────────────────────────────────────────────────────────────────────
def get_application_id(token: str) -> str:
    """
    Obtém o ID da aplicação a partir do token do bot.
    """
    response = requests.get(
        "https://discord.com/api/v10/users/@me",
        headers={"Authorization": f"Bot {token}"}
    )
    if response.status_code == 200:
        return response.json().get("id")
    raise Exception(f"Erro ao obter ID da aplicação: {response.status_code}")


def enable_intents(token: str, app_id: str = None) -> bool:
    """
    Ativa as intents privilegiadas do bot.
    flags 11051008 = GATEWAY_PRESENCE | GATEWAY_GUILD_MEMBERS | GATEWAY_MESSAGE_CONTENT
    """
    if app_id is None:
        app_id = get_application_id(token)

    response = requests.patch(
        f"https://discord.com/api/v10/applications/{app_id}",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
        },
        json={
            "bot_public": True,
            "bot_require_code_grant": False,
            "flags": 11051008
        }
    )

    if response.status_code == 200:
        print("[Intents] Intents privilegiadas ativadas com sucesso!")
        return True
    else:
        print(f"[Intents] Erro ao ativar intents: {response.status_code} - {response.text}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# log_restart (core/log_restart.py)
# ─────────────────────────────────────────────────────────────────────────────
async def log_restart(bot: disnake.Client):
    try:
        info = database.obter("config.json")
        db_canais = database.get_document("canais")
        db_mode = database.get_document("custom_mode")
        db_color = database.get_document("custom_colors")

        canal_id_str = db_canais.get("canal_de_logs_do_sistema")
        if not canal_id_str:
            return

        canal_id = int(canal_id_str)
        canal_obj = bot.get_channel(canal_id)

        if not canal_obj:
            print(f"Canal de logs do sistema com ID {canal_id} não foi encontrado.")
            return

        mode = db_mode.get("mode", "components")
        primary_color_hex = db_color.get("primary")

        description_text_embed = (
            f"{emoji.reload} O **{bot.user.name}** foi reiniciado.\n"
            f"{emoji.robot} Versão atual: `{info['version']}`\n"
            f"{emoji.calendar} **Data:** <t:{int(time.time())}:f> (<t:{int(time.time())}:R>)"
        )
        description_text_container = (
            f"{emoji.reload} O **{bot.user.name}** foi reiniciado @everyone\n"
            f"{emoji.robot} Versão atual: `{info['version']}`\n"
            f"{emoji.calendar} **Data:** <t:{int(time.time())}:f> (<t:{int(time.time())}:R>)"
        )

        buttons = disnake.ui.ActionRow(
            disnake.ui.Button(
                label="OK",
                style=disnake.ButtonStyle.green,
                custom_id="restart_ok"
            )
        )

        if mode == "embed":
            content_text = f"@everyone"
            embed_kwargs = {}
            if primary_color_hex:
                embed_kwargs["color"] = int(primary_color_hex.replace("#", ""), 16)
            embed = disnake.Embed(
                title=f"Informações do Sistema > Reinicialização",
                description=description_text_embed,
                **embed_kwargs,
                # timestamp=disnake.utils.utcnow()
            )
            # embed.set_footer(text=bot.user.name, icon_url=bot.user.display_avatar.url if bot.user.display_avatar else None)
            await canal_obj.send(content=content_text, embed=embed, components=[buttons])

        else:
            container_kwargs = {}
            if primary_color_hex:
                container_kwargs["accent_colour"] = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))
            container = disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.priv_1}{emoji.priv_2}{emoji.priv_3}{emoji.priv_4}{emoji.priv_5}\n-# Informações do sistema > **Reinicialização**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(description_text_container),
                disnake.ui.Separator(),
                buttons,
                **container_kwargs
            )
            await canal_obj.send(components=[container], flags=disnake.MessageFlags(is_components_v2=True))

    except Exception as e:
        import traceback
        print(f"Ocorreu um erro em log_restart: {e}")
        traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# apply_server_protection (core/server_protection.py)
# ─────────────────────────────────────────────────────────────────────────────
def get_main_server_id() -> int:
    """Obtém o ID do servidor principal do config.json"""
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
            server_id = config.get("bot", {}).get("server")
            if server_id:
                return int(server_id)
    except Exception as e:
        print(f"Erro ao ler config.json: {e}")
    return None


def apply_server_protection(bot: commands.Bot):
    """
    No modo multi-servidor, não bloqueia comandos por servidor.
    O controle de acesso é feito pelo sistema de planos (plan_guard).
    """
    # Multi-server mode: sem bloqueio global
    pass


__all__ = [
    "create_bot",
    "change_bio",
    "change_status",
    "enable_intents",
    "log_restart",
    "apply_server_protection",
    # auxiliares públicos preservados
    "obter_info",
    "salvar_info",
    "get_status_obj",
    "get_status",
    "get_application_id",
    "get_main_server_id",
]
