"""Handler de erros (infra) — implementação canônica (Fase B).

Sistema de logging de erros para Discord. Captura exceções (via listeners do
bot e, opcionalmente, via rede de captura global em ``privacylib.errors.capture``)
e envia para um canal de logs por-servidor com fallback para o canal global.

A implementação real foi movida para cá na Fase B. O módulo antigo
``functions/error_handler.py`` passou a ser um shim que reexporta estes
símbolos por identidade.

Reexporta/expõe:
    - ``ErrorHandler``: classe que configura e roteia o tratamento de erros.
    - ``setup_error_handler``: configura o handler no bot.
    - ``report_background_error``: reporta erros de background ao canal de logs.
    - ``_GLOBAL_HANDLER``: instância global usada por tarefas de background e
      pela rede de captura global para reportar erros.

_Requirements: 4.1, 4.4, 4.5, 4.6, 14.1, 14.3, 15.3_
"""
import disnake
from disnake.ext import commands
import traceback
import datetime
import sys
from typing import Optional

from privacylib.db.store import database as db


class ErrorHandler:
    """Gerenciador de erros global do bot"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.error_channel_id: Optional[int] = None

    def load_error_channel(self):
        """Carrega o ID do canal de erros global do banco de dados (fallback)."""
        try:
            config = db.get_document("error_logs_config") or {}
            self.error_channel_id = config.get("channel_id")
        except Exception:
            self.error_channel_id = None

    def _resolve_channel_id(self, guild_id=None) -> Optional[int]:
        """Resolve o canal de logs a usar.

        Ordem: canal por-servidor (error_logs_config_{guild}) → canal global
        (error_logs_config). Assim cada servidor pode ter seu próprio canal e,
        se não tiver, cai no canal global do dono.
        """
        # 1. Canal específico do servidor
        if guild_id is not None:
            try:
                cfg = db.get_document(f"error_logs_config_{guild_id}") or {}
                cid = cfg.get("channel_id")
                if cid:
                    return int(cid)
            except Exception:
                pass
        # 2. Canal global (fallback)
        try:
            cfg = db.get_document("error_logs_config") or {}
            cid = cfg.get("channel_id")
            if cid:
                return int(cid)
        except Exception:
            pass
        return None

    def setup_global_handlers(self):
        """Configura handlers globais de exceções.

        A instalação real dos hooks (sys.excepthook, threads, asyncio, logging,
        unraisable) é feita pelo módulo privacylib.errors.capture, que tem
        anti-loop e throttle. Aqui apenas delegamos para evitar handlers duplicados.
        """
        try:
            from privacylib.errors.capture import install as install_capture
            install_capture(loop=getattr(self.bot, "loop", None))
        except Exception as e:
            print(f"[ERROR] Falha ao instalar captura global: {e}")

    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """Handler para exceções não capturadas"""
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        # Criar string do erro
        error_text = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))

        # Enviar para o canal de erros
        self.bot.loop.create_task(self.send_error_to_channel(
            "Exceção Global Não Capturada",
            error_text,
            exc_type.__name__
        ))

    def handle_asyncio_exception(self, loop, context):
        """Handler para exceções do asyncio"""
        exc = context.get('exception')
        if exc:
            error_text = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            error_name = type(exc).__name__
        else:
            error_text = f"Message: {context.get('message')}\n"
            error_name = "Asyncio Error"

        self.bot.loop.create_task(self.send_error_to_channel(
            "Exceção AsyncIO",
            error_text,
            error_name
        ))

    async def send_error_to_channel(self, title: str, error_text: str, error_name: str, guild_id=None):
        """Envia o erro para o canal configurado (por-servidor com fallback global)."""
        # SEMPRE logar no stdout/journal para diagnóstico (independente do canal Discord)
        print(f"[ERROR] {title}: {error_name}")
        print(error_text)

        channel_id = self._resolve_channel_id(guild_id)
        if not channel_id:
            return

        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                print(f"[ERROR] Canal de logs não encontrado: {channel_id}")
                return

            # Limitar tamanho do erro
            max_length = 1900
            if len(error_text) > max_length:
                error_text = error_text[:max_length] + "\n... (truncado)"

            # Criar embed do erro
            embed = disnake.Embed(
                title=f"❌ {title}",
                description=f"**Erro:** `{error_name}`",
                color=disnake.Color.red(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )

            embed.add_field(
                name="Traceback",
                value=f"```\n{error_text}\n```",
                inline=False
            )

            await channel.send(embed=embed)
        except Exception as e:
            print(f"[ERROR] Falha ao enviar erro para o canal: {e}")
            print(f"[ERROR] {title}: {error_name}")
            print(error_text)


# Instância global do handler, para tarefas de background reportarem erros.
_GLOBAL_HANDLER: Optional["ErrorHandler"] = None


async def report_background_error(titulo: str, error: Exception, guild_id=None):
    """Reporta um erro de tarefa de background ao sistema de logs.

    Use dentro de `except` em `@tasks.loop` para que o erro chegue ao canal de
    logs (por-servidor com fallback global), além do stdout/journald.
    """
    if _GLOBAL_HANDLER is None:
        # Sem handler ainda: ao menos loga no stdout.
        print(f"[BG_ERROR] {titulo}: {type(error).__name__}: {error}")
        return
    error_text = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    try:
        await _GLOBAL_HANDLER.send_error_to_channel(titulo, error_text, type(error).__name__, guild_id=guild_id)
    except Exception as e:
        print(f"[BG_ERROR] Falha ao reportar '{titulo}': {e}")


def setup_error_handler(bot: commands.Bot, setup_global: bool = False):
    """Configura o handler de erros global para o bot

    Args:
        bot: Instância do bot
        setup_global: Se True, configura handlers globais (pode causar problemas)
    """
    global _GLOBAL_HANDLER
    error_handler = ErrorHandler(bot)
    error_handler.load_error_channel()
    _GLOBAL_HANDLER = error_handler

    # Apenas configurar handlers globais se explicitamente solicitado
    # Configurar de forma segura após o bot estar pronto
    if setup_global:
        @bot.event
        async def on_ready():
            """Configura handlers globais após o bot estar pronto"""
            print("[ErrorHandler] Bot pronto, configurando handlers globais de erros...")
            try:
                error_handler.setup_global_handlers()
                print("[ErrorHandler] ✅ Handlers globais de erros configurados com sucesso")
            except Exception as e:
                print(f"[ErrorHandler] ❌ Falha ao configurar handlers globais: {e}")

            # Rede de captura em TODAS as camadas (threads, asyncio, logging, unraisable)
            try:
                from privacylib.errors.capture import install as install_capture
                install_capture(loop=bot.loop)
            except Exception as e:
                print(f"[ErrorHandler] ❌ Falha ao instalar captura global: {e}")

    # Adicionar listener para erros de comandos
    @bot.event
    async def on_command_error(ctx: commands.Context, error: Exception):
        """Handler para erros de comandos"""
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Você não tem permissão para usar este comando.")
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Argumento obrigatório ausente: `{error.param.name}`")
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ Argumento inválido: {error}")
            return

        # Outros erros
        error_text = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        await error_handler.send_error_to_channel(
            f"Erro no Comando: {ctx.command.name if ctx.command else 'Desconhecido'}",
            error_text,
            type(error).__name__
        )

        # Tentar enviar mensagem ao usuário
        try:
            await ctx.send("❌ Ocorreu um erro ao executar este comando. O erro foi reportado.")
        except:
            pass

    # Adicionar listener para erros de interações
    @bot.event
    async def on_slash_command_error(inter: disnake.ApplicationCommandInteraction, error: Exception):
        """Handler para erros de comandos slash"""
        error_text = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        gid = inter.guild.id if inter.guild else None
        await error_handler.send_error_to_channel(
            f"Erro no Slash Command: {inter.application_command.name}",
            error_text,
            type(error).__name__,
            guild_id=gid,
        )

        # Tentar enviar mensagem ao usuário
        try:
            await inter.response.send_message(
                "❌ Ocorreu um erro ao executar este comando. O erro foi reportado.",
                ephemeral=True
            )
        except:
            try:
                await inter.edit_original_message(
                    content="❌ Ocorreu um erro ao executar este comando. O erro foi reportado."
                )
            except:
                pass

    # Rede de segurança: erros em QUALQUER listener de evento (botões, selects,
    # modais, on_message, etc.) caem aqui. É a principal lacuna do sistema antigo.
    @bot.event
    async def on_error(event_method: str, *args, **kwargs):
        """Handler global para erros em qualquer evento/listener."""
        error_text = traceback.format_exc()

        # Tenta descobrir o servidor a partir dos argumentos do evento (interação,
        # mensagem, etc.) para mandar ao canal do servidor certo.
        guild_id = None
        for a in args:
            try:
                g = getattr(a, "guild", None)
                if g is not None:
                    guild_id = g.id
                    break
                gid = getattr(a, "guild_id", None)
                if gid:
                    guild_id = gid
                    break
            except Exception:
                continue

        exc_name = "Erro"
        try:
            exc_name = sys.exc_info()[0].__name__
        except Exception:
            pass

        await error_handler.send_error_to_channel(
            f"Erro no evento: {event_method}",
            error_text,
            exc_name,
            guild_id=guild_id,
        )

    # Erros de interação não tratados (inclui componentes/botões/selects em alguns
    # fluxos). Complementa o on_error acima.
    @bot.event
    async def on_interaction_error(inter: disnake.Interaction, error: Exception):
        """Handler para erros gerais de interação (componentes)."""
        error_text = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        gid = None
        try:
            gid = inter.guild.id if inter.guild else None
        except Exception:
            pass

        # Identifica o componente/comando para o título
        ident = "interação"
        try:
            comp = getattr(inter, "component", None)
            if comp is not None:
                ident = getattr(comp, "custom_id", None) or "componente"
            elif getattr(inter, "application_command", None):
                ident = inter.application_command.name
        except Exception:
            pass

        await error_handler.send_error_to_channel(
            f"Erro em interação: {ident}",
            error_text,
            type(error).__name__,
            guild_id=gid,
        )

        # Avisa o usuário de forma não-intrusiva, se ainda for possível responder.
        try:
            if not inter.response.is_done():
                await inter.response.send_message(
                    "❌ Ocorreu um erro. O problema foi reportado à equipe.",
                    ephemeral=True,
                )
        except Exception:
            pass

    return error_handler


__all__ = ["ErrorHandler", "setup_error_handler", "report_background_error"]
