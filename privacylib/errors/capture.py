"""Captura global de erros (infra) — implementação canônica (Fase B).

Rede de captura de erros em TODAS as camadas. Objetivo: garantir que
praticamente nenhum erro do bot passe despercebido, enviando tudo ao sistema de
logs (canal configurado, por-servidor com fallback global) além do
stdout/journald.

A implementação real foi movida para cá na Fase B. O módulo antigo
``functions/global_error_capture.py`` passou a ser um shim que reexporta
``install`` por identidade.

Camadas cobertas:
  1. sys.excepthook            → exceções não tratadas na thread principal
  2. threading.excepthook      → exceções em qualquer thread (ex.: run_in_executor)
  3. sys.unraisablehook        → exceções que o Python não consegue propagar
  4. asyncio exception handler → erros em tasks async órfãs / callbacks
  5. logging (root handler)    → todo logging.error/exception/critical de QUALQUER
                                 módulo, inclusive disnake e libs de terceiros

Proteções:
  - Anti-loop: enquanto um erro está sendo reportado, novas capturas são ignoradas.
  - Throttle: erros idênticos repetidos em janela curta são agregados (evita flood).
  - Nunca levanta exceção (falha de forma silenciosa no pior caso, só com print).

Segurança de ciclos (Req 15.3): o acesso ao handler de erros é feito por import
tardio dentro de ``_enviar``/``install`` (nunca em tempo de módulo), preservando
o comportamento anti-ciclo da implementação original.

_Requirements: 4.2, 4.3, 14.1, 14.3, 15.3_
"""
import sys
import time
import logging
import threading
import traceback

# Estado interno (evita import circular; o envio real é feito via error_handler).
_installed = False
_reporting = False  # anti-loop
_last_sent: dict[str, float] = {}  # hash do erro → timestamp do último envio
_THROTTLE_SECONDS = 30  # não repetir o mesmo erro no canal com mais frequência


def _throttled(chave: str) -> bool:
    """True se este erro foi enviado há pouco (deve ser suprimido no canal)."""
    agora = time.time()
    ultimo = _last_sent.get(chave, 0)
    if agora - ultimo < _THROTTLE_SECONDS:
        return True
    _last_sent[chave] = agora
    # Limpa entradas antigas para não crescer indefinidamente
    if len(_last_sent) > 500:
        for k in [k for k, t in _last_sent.items() if agora - t > 300]:
            _last_sent.pop(k, None)
    return False


def _enviar(titulo: str, error_text: str, error_name: str, guild_id=None):
    """Enfileira o envio ao canal de logs sem bloquear e sem quebrar."""
    global _reporting
    if _reporting:
        return  # anti-loop: um erro durante o reporte não vira outro reporte
    chave = f"{error_name}:{hash(error_text[:400])}"
    if _throttled(chave):
        return

    _reporting = True
    try:
        from privacylib.errors import handler as eh
        handler = getattr(eh, "_GLOBAL_HANDLER", None)
        if handler is None or getattr(handler, "bot", None) is None:
            return
        bot = handler.bot
        loop = getattr(bot, "loop", None)
        if loop is None or not loop.is_running():
            return

        async def _coro():
            try:
                await handler.send_error_to_channel(titulo, error_text, error_name, guild_id=guild_id)
            except Exception:
                pass

        try:
            # Agenda no loop do bot de forma thread-safe (funciona de qualquer thread)
            import asyncio
            asyncio.run_coroutine_threadsafe(_coro(), loop)
        except Exception:
            pass
    except Exception:
        pass
    finally:
        _reporting = False


# ── 1. Exceções não tratadas (thread principal) ──────────────────────────────
def _excepthook(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    texto = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(f"[GLOBAL_ERROR] {exc_type.__name__}\n{texto}")
    _enviar("Exceção não capturada", texto, exc_type.__name__)


# ── 2. Exceções em threads ────────────────────────────────────────────────────
def _thread_excepthook(args):
    exc_type = args.exc_type
    if issubclass(exc_type, KeyboardInterrupt):
        return
    texto = ''.join(traceback.format_exception(exc_type, args.exc_value, args.exc_traceback))
    nome_thread = getattr(args.thread, "name", "?")
    print(f"[GLOBAL_ERROR] (thread {nome_thread}) {exc_type.__name__}\n{texto}")
    _enviar(f"Exceção em thread: {nome_thread}", texto, exc_type.__name__)


# ── 3. Exceções não propagáveis ───────────────────────────────────────────────
def _unraisablehook(unraisable):
    try:
        exc_type = unraisable.exc_type
        texto = ''.join(traceback.format_exception(
            exc_type, unraisable.exc_value, unraisable.exc_traceback))
        print(f"[GLOBAL_ERROR] (unraisable) {exc_type.__name__}\n{texto}")
        _enviar("Exceção não propagável", texto, exc_type.__name__)
    except Exception:
        pass


# ── 4. Erros do asyncio ───────────────────────────────────────────────────────
def _asyncio_handler(loop, context):
    exc = context.get("exception")
    if exc is not None:
        if isinstance(exc, KeyboardInterrupt):
            return
        texto = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        nome = type(exc).__name__
    else:
        texto = f"Message: {context.get('message')}\nContext: {context}"
        nome = "AsyncioError"
    print(f"[GLOBAL_ERROR] (asyncio) {nome}\n{texto}")
    _enviar("Erro no asyncio", texto, nome)


# ── 5. Handler de logging raiz ────────────────────────────────────────────────
class _LogCaptureHandler(logging.Handler):
    """Captura logging.error/exception/critical de qualquer módulo."""

    def emit(self, record: logging.LogRecord):
        try:
            if record.levelno < logging.ERROR:
                return
            # Evita recapturar o próprio print/log de erro deste sistema
            if record.name.startswith("PrivacyBOT.global_capture"):
                return
            if record.exc_info:
                texto = ''.join(traceback.format_exception(*record.exc_info))
                nome = record.exc_info[0].__name__ if record.exc_info[0] else "LogError"
            else:
                texto = record.getMessage()
                nome = "LogError"
            _enviar(f"Log de erro: {record.name}", texto, nome)
        except Exception:
            pass


def install(loop=None):
    """Instala todos os hooks de captura. Idempotente."""
    global _installed
    if _installed:
        return
    _installed = True

    try:
        sys.excepthook = _excepthook
    except Exception:
        pass
    try:
        threading.excepthook = _thread_excepthook
    except Exception:
        pass
    try:
        sys.unraisablehook = _unraisablehook
    except Exception:
        pass
    try:
        import asyncio
        if loop is None:
            loop = asyncio.get_event_loop()
        loop.set_exception_handler(_asyncio_handler)
    except Exception:
        pass
    try:
        root = logging.getLogger()
        # Evita instalar duplicado
        if not any(isinstance(h, _LogCaptureHandler) for h in root.handlers):
            h = _LogCaptureHandler()
            h.setLevel(logging.ERROR)
            root.addHandler(h)
    except Exception:
        pass

    print("[GlobalErrorCapture] ✅ Rede de captura de erros instalada (todas as camadas)")


__all__ = ["install"]
