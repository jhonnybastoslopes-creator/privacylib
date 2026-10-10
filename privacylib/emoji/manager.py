"""Gestão de emojis (infra de apresentação) — Fase B: implementação real.

A classe de gestão ``emojis`` (upload/sync/reconciliação com a aplicação do
Discord) agora mora aqui. O antigo ``functions/emojis/__init__.py`` passou a ser
um *shim* de compatibilidade que reexporta ``emojis`` daqui por identidade:

    functions.emojis.emojis is privacylib.emoji.manager.emojis   # True

Os submódulos auxiliares (folhas, sem risco de ciclo) permanecem em
``functions/emojis/`` e são importados daqui:

- ``functions.emojis.database`` → ``load_emojis`` / ``save_emojis``
- ``functions.emojis.verify``   → ``verify_emojis_batch``
- ``functions.emojis.upload``   → ``upload_emoji_async``
- ``functions.emojis.delete``   → ``delete_emoji_async``

A classe ``emojis`` expõe, entre outros, os métodos de gestão/upload/sync:

- ``sync_all`` / ``sync_all_async`` — sincroniza todos os emojis do ``emojis.json``.
- ``reconcile_ids`` / ``reconcile_ids_async`` — atualiza os IDs dos emojis que já
  existem na aplicação Discord e envia apenas os que faltam; retorna a tupla de
  contagens ``(atualizados, enviados, faltando)``.
- ``validate_or_create_async`` — valida/cria um emoji individual.
- ``_set_configured_True`` — marca o token atual como configurado.

_Requirements: 14.1, 14.3, 12.2, 7.6_
"""

import os
import re
import sys
import asyncio
import aiohttp
import json

from functions.emojis.database import load_emojis, save_emojis
from functions.emojis.verify import verify_emojis_batch
from functions.emojis.upload import upload_emoji_async
from functions.emojis.delete import delete_emoji_async


class emojis:
    DB_PATH = "database/emojis/emojis.json"
    ASSETS_PATH = "database/emojis/assets"

    def __init__(self, bot_token: str, app_id: str):
        self.bot_token = bot_token
        self.app_id = app_id
        self.emojis_db = load_emojis()
        self._ensure_emojis_structure()
        # Recarregar após garantir estrutura
        if not self.emojis_db or len(self.emojis_db) == 0:
            self.emojis_db = load_emojis()

    def get(self, name: str) -> str | None:
        return self.emojis_db.get(name)

    def list(self) -> dict:
        return self.emojis_db

    def save(self):
        save_emojis(self.emojis_db)

    def _ensure_emojis_structure(self):
        """Garante que emojis.json tenha a estrutura correta escaneando assets"""
        if not self.emojis_db or len(self.emojis_db) == 0:
            print("[Emojis] emojis.json vazio, escaneando pasta de assets...")

            if not os.path.exists(self.ASSETS_PATH):
                print(f"[Emojis] Pasta de assets não encontrada: {self.ASSETS_PATH}")
                return

            # Escanear todos os arquivos na pasta de assets
            emoji_files = {}
            try:
                for filename in os.listdir(self.ASSETS_PATH):
                    if filename.endswith(('.png', '.gif')):
                        # Remover extensão para obter o nome do emoji
                        emoji_name = os.path.splitext(filename)[0]
                        emoji_files[emoji_name] = ""

                if emoji_files:
                    self.emojis_db = emoji_files
                    self.save()
                    print(f"[Emojis] Estrutura criada com {len(self.emojis_db)} emojis encontrados em assets")
                else:
                    print("[Emojis] Nenhum arquivo de emoji encontrado em assets")
            except Exception as e:
                print(f"[Emojis] Erro ao escanear assets: {e}")

    def validate_name(self, name: str) -> bool:
        return 2 <= len(name) <= 32

    async def _list_guild_emojis_async(self, session: aiohttp.ClientSession):
        url = f"https://discord.com/api/v10/applications/{self.app_id}/emojis"
        headers = {
            "Authorization": f"Bot {self.bot_token}",
            "User-Agent": "DiscordBot (https://privacymods.bot, 1.0)",
        }
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("items", [])
        return []

    def emoji_name_exists(self, name: str, guild_emojis: list) -> bool:
        return any(e["name"] == name for e in guild_emojis)

    def get_emoji_id(self, name: str, guild_emojis: list) -> str | None:
        for emoji in guild_emojis:
            if emoji["name"] == name:
                return emoji["id"]
        return None

    async def validate_or_create_async(
        self, session: aiohttp.ClientSession, name: str, guild_emojis: list
    ) -> tuple[str | None, bool]:
        tag = self.emojis_db.get(name, "")
        create = False

        if not tag:
            create = True
        else:
            match = re.search(r"<a?:\w+:(\d+)>", tag)
            emoji_id = match.group(1) if match else None
            if emoji_id:
                # Verificação rápida inline
                verify_results = await verify_emojis_batch(
                    self.app_id, self.bot_token, [emoji_id]
                )
                if not verify_results.get(emoji_id, False):
                    await delete_emoji_async(session, self.app_id, self.bot_token, emoji_id)
                    create = True
                    self.emojis_db[name] = ""
            else:
                create = True

        if create:
            if not self.validate_name(name):
                return None, False

            if self.emoji_name_exists(name, guild_emojis):
                emoji_id = self.get_emoji_id(name, guild_emojis)
                if emoji_id:
                    await delete_emoji_async(
                        session, self.app_id, self.bot_token, emoji_id
                    )

            gif_path = os.path.join(self.ASSETS_PATH, f"{name}.gif")
            png_path = os.path.join(self.ASSETS_PATH, f"{name}.png")
            path = gif_path if os.path.isfile(gif_path) else png_path

            if not os.path.isfile(path):
                return None, False

            try:
                new_id = await upload_emoji_async(
                    session, name, path, self.app_id, self.bot_token
                )
                new_tag = (
                    f"<a:{name}:{new_id}>"
                    if path.endswith(".gif")
                    else f"<:{name}:{new_id}>"
                )
                self.emojis_db[name] = new_tag
                return new_tag, True
            except Exception as e:
                print(f"[Error] Failed to create emoji {name}: {e}")
                return None, False
        return tag, False

    def _set_configured_True(self):
        try:
            path = "database/emojis/emojis_data.json"
            data = {
                "configured": "True",
                "lastToken": self.bot_token
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print("[Emojis] emojis_data.json atualizado com sucesso")
        except Exception as e:
            print(f"[Emojis] Falha ao atualizar emojis_data.json: {e}")

    async def sync_all_async(self, progress_callback=None):
        total = len(self.emojis_db)
        success = 0
        added = 0

        print(f"[Emojis] Iniciando sincronização de {total} emojis...")

        connector = aiohttp.TCPConnector(limit=50)
        async with aiohttp.ClientSession(connector=connector) as session:
            guild_emojis = await self._list_guild_emojis_async(session)
            print(f"[Emojis] {len(guild_emojis)} emojis encontrados no Discord")

            # Processar em lotes de 10 emojis por vez
            names = list(self.emojis_db.keys())
            batch_size = 10

            for i in range(0, len(names), batch_size):
                batch = names[i : i + batch_size]
                tasks = []
                for name in batch:
                    task = asyncio.create_task(self.validate_or_create_async(session, name, guild_emojis))
                    tasks.append(task)
                    await asyncio.sleep(0.2)
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for name, result in zip(batch, results):
                    if isinstance(result, Exception):
                        print(f"[Emojis] Erro ao processar {name}: {result}")
                        continue

                    tag, was_added = result
                    if tag:
                        success += 1
                    if was_added:
                        added += 1

                    if progress_callback:
                        progress_callback(success, total)

                # Atualizar lista de emojis após cada lote
                if added > 0:
                    guild_emojis = await self._list_guild_emojis_async(session)

        # Salvar todas as mudanças de uma vez
        self.save()

        print(f"[Emojis] Sincronização concluída: {success}/{total} emojis processados, {added} novos adicionados")

        if success == total:
            self._set_configured_True()
            print("[Emojis] Todos os emojis foram sincronizados com sucesso!")

            if added > 0:
                print(f"[Emojis] {added} novos emojis foram adicionados. Reiniciando bot...")
                return os.execv(sys.executable, ["python"] + sys.argv)
            else:
                print("[Emojis] Nenhum novo emoji foi adicionado.")

        return success, total

    def sync_all(self, progress_callback=None):
        """Versão síncrona para compatibilidade"""
        return asyncio.run(self.sync_all_async(progress_callback))

    # ─────────────────────────────────────────────────────────────────────────
    # Sincronização leve de IDs — NÃO faz upload, apenas atualiza os IDs do
    # emojis.json com os IDs reais dos emojis que já existem na aplicação no
    # Discord. Faz upload SOMENTE dos emojis que estiverem faltando.
    # Roda rápido em toda inicialização, mantendo os mesmos emojis sempre
    # com os IDs corretos (evita emojis aparecendo como texto cru).
    # ─────────────────────────────────────────────────────────────────────────
    async def reconcile_ids_async(self, progress_callback=None):
        """
        Lê os emojis existentes no Discord e:
          1. Atualiza no emojis.json o ID de cada emoji que já existe (por nome).
          2. Faz upload apenas dos emojis que não existem no Discord.
        Retorna (atualizados, enviados, faltando).
        """
        updated = 0
        uploaded = 0
        still_missing = 0

        connector = aiohttp.TCPConnector(limit=50)
        async with aiohttp.ClientSession(connector=connector) as session:
            guild_emojis = await self._list_guild_emojis_async(session)
            discord_by_name = {e["name"]: e for e in guild_emojis}
            print(f"[Emojis] Reconciliação: {len(discord_by_name)} emojis na aplicação Discord, {len(self.emojis_db)} no JSON")

            names = list(self.emojis_db.keys())
            to_upload = []

            for name in names:
                disc = discord_by_name.get(name)
                if disc:
                    # Emoji existe no Discord — atualizar/confirmar o ID no JSON
                    animated = disc.get("animated", False)
                    prefix = "a" if animated else ""
                    new_tag = f"<{prefix}:{name}:{disc['id']}>"
                    if self.emojis_db.get(name) != new_tag:
                        self.emojis_db[name] = new_tag
                        updated += 1
                else:
                    # Não existe no Discord — precisa fazer upload
                    to_upload.append(name)

            # Upload apenas dos que faltam (em lotes pequenos)
            if to_upload:
                print(f"[Emojis] {len(to_upload)} emojis faltando no Discord — enviando...")
                batch_size = 10
                for i in range(0, len(to_upload), batch_size):
                    batch = to_upload[i:i + batch_size]
                    tasks = []
                    for name in batch:
                        tasks.append(asyncio.create_task(
                            self.validate_or_create_async(session, name, guild_emojis)
                        ))
                        await asyncio.sleep(0.2)
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for name, result in zip(batch, results):
                        if isinstance(result, Exception):
                            print(f"[Emojis] Erro ao enviar {name}: {result}")
                            still_missing += 1
                            continue
                        tag, was_added = result
                        if tag:
                            uploaded += 1
                        else:
                            still_missing += 1
                    # Atualizar lista após cada lote
                    guild_emojis = await self._list_guild_emojis_async(session)

        # Persistir mudanças de ID no JSON
        self.save()
        print(f"[Emojis] Reconciliação concluída: {updated} IDs atualizados, {uploaded} enviados, {still_missing} ainda faltando")
        return updated, uploaded, still_missing

    def reconcile_ids(self, progress_callback=None):
        """Versão síncrona de reconcile_ids_async."""
        return asyncio.run(self.reconcile_ids_async(progress_callback))


__all__ = ["emojis"]
