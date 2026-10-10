"""Emojis (infra de apresentação): fachada runtime — Fase B (implementação real).

A implementação **real** do runtime de emojis agora mora aqui:

- a classe ``emoji``, cujos atributos de classe são carregados dinamicamente de
  ``database/emojis/emojis.json`` na importação;
- ``reload_emoji_class`` — recarrega os atributos da classe ``emoji`` a partir
  do JSON (atualiza o MESMO objeto de classe em memória);
- ``init_on_startup(bot_token, app_id)`` — inicializa o sistema de emojis na
  subida do bot (reconciliação de IDs + upload dos faltantes).

Como existe um **único objeto de classe** ``emoji`` definido neste módulo e o
antigo ``functions/emoji.py`` apenas o reexporta por identidade, a instância
única compartilhada em memória é preservada (Requisito 12.2):

    functions.emoji.emoji is privacylib.emoji.emoji            # True
    functions.emoji.reload_emoji_class is privacylib.emoji.reload_emoji_class
    functions.emoji.init_on_startup    is privacylib.emoji.init_on_startup

O submódulo de gestão/upload/sync permanece em ``privacylib.emoji.manager``.

_Requirements: 14.1, 14.3, 12.2, 7.1, 7.2, 7.4, 7.5, 7.8_
"""

from privacylib.db.store import database as db


class emoji:
    db = db.obter("database/emojis/emojis.json")
    for key, value in db.items():
        locals()[key] = value


def reload_emoji_class():
    """Recarrega a classe emoji com os dados atualizados"""
    emoji.db = db.obter("database/emojis/emojis.json")
    for key, value in emoji.db.items():
        setattr(emoji, key, value)
    print(f"[Emojis] Classe emoji recarregada com {len(emoji.db)} emojis")


def init_on_startup(bot_token: str, app_id: str) -> None:
    """
    Inicializa o sistema de emojis na inicialização do bot.

    Estratégia (mantém sempre os MESMOS emojis, mas com os IDs corretos):
      • Reconciliação de IDs SEMPRE roda: lê os emojis já existentes na
        aplicação do bot no Discord e atualiza os IDs no emojis.json.
        Isso corrige emojis que apareciam como texto cru (ex: ":loading:")
        quando o ID salvo no JSON estava desatualizado.
      • Faz upload apenas dos emojis que estiverem faltando no Discord.
      • Se a aplicação nunca teve emojis (primeira vez), faz a sincronização
        completa (sync_all) que cria todos.
    """
    print("[Emojis] Iniciando sistema de emojis...")

    from privacylib.emoji.manager import emojis as Emojis

    try:
        emoji_manager = Emojis(bot_token, app_id)
    except Exception as e:
        print(f"[Emojis] Falha ao inicializar gerenciador de emojis: {e}")
        return

    total_json = len(emoji_manager.emojis_db)
    print(f"[Emojis] {total_json} emojis no JSON local")

    # Ativar intents privilegiadas (necessário para operações de aplicação)
    try:
        from privacylib.bot.lifecycle import enable_intents
        enable_intents(bot_token, app_id)
    except Exception as e:
        print(f"[Emojis] Aviso ao ativar intents: {e}")

    try:
        # Reconciliação leve: atualiza IDs pelos emojis já existentes no Discord
        # e faz upload somente dos que faltam. Roda em toda inicialização.
        updated, uploaded, missing = emoji_manager.reconcile_ids()

        # Se muitos emojis ainda faltam (ex: aplicação totalmente vazia),
        # fazer a sincronização completa como fallback.
        if missing > 0 and (uploaded + updated) == 0:
            print("[Emojis] Nenhum emoji encontrado na aplicação — sincronização completa...")
            emoji_manager.sync_all()

        # Marcar token atual como o último usado
        emoji_manager._set_configured_True()

        # Recarregar a classe emoji com os IDs atualizados
        reload_emoji_class()

        if updated or uploaded:
            print(f"[Emojis] ✅ Emojis atualizados (IDs: {updated}, novos: {uploaded})")
        else:
            print("[Emojis] ✅ Emojis já estavam sincronizados")
    except Exception as e:
        import traceback
        print(f"[Emojis] Erro na reconciliação de emojis: {e}")
        print(traceback.format_exc())


__all__ = ["emoji", "reload_emoji_class", "init_on_startup"]
