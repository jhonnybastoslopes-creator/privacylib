"""
privacylib/extensions/logs.py — Log de Compras/Eventos de Extensões.

Envia embeds para o canal de logs configurado pelo dono (Req 13). Se o canal não
estiver configurado ou não puder receber a mensagem, apenas registra internamente
(via payments._record_history / print) e NÃO falha o fluxo de ativação/expiração.

_Requirements: 14.1, 14.3
"""
import time
from datetime import datetime

import disnake

from privacylib.extensions import catalog, payments


def _nomes_extensoes(ext_ids: list[str]) -> str:
    partes = []
    for eid in ext_ids:
        ext = catalog.obter(eid)
        if ext:
            partes.append(f"{ext.get('emoji', '🧩')} {ext.get('nome', eid)}")
        else:
            partes.append(eid)
    return ", ".join(partes) if partes else "—"


async def _enviar(bot, embed: disnake.Embed):
    """Envia o embed ao canal de log, se configurado e acessível. Nunca lança."""
    try:
        channel_id = payments.get_log_channel()
        if not channel_id or bot is None:
            return False
        channel = bot.get_channel(int(channel_id))
        if not channel:
            return False
        await channel.send(embed=embed)
        return True
    except Exception:
        return False


async def registrar_compra(bot, guild_id, user_id, ext_ids, valor, desconto_percent=0.0,
                           via="payment"):
    """Log de uma compra de extensão aprovada (Req 13.2)."""
    guild = bot.get_guild(int(guild_id)) if (bot and guild_id) else None
    nome_srv = guild.name if guild else f"Servidor {guild_id}"

    desc = (
        f"**Servidor:** {nome_srv} (`{guild_id}`)\n"
        f"**Comprador:** <@{user_id}>\n"
        f"**Extensões:** {_nomes_extensoes(ext_ids)}\n"
        f"**Valor pago:** R$ `{float(valor):.2f}`"
    )
    if desconto_percent:
        desc += f"\n**Desconto aplicado:** `{desconto_percent:.0f}%`"

    embed = disnake.Embed(
        title="🧾 Nova Compra de Extensão",
        description=desc,
        color=0x2ecc71,
        timestamp=datetime.now(),
    )
    embed.set_footer(text="Marketplace de Extensões")
    enviado = await _enviar(bot, embed)
    if not enviado:
        print(f"[EXT_LOG] Compra: guild={guild_id} user={user_id} exts={ext_ids} R${valor:.2f} (canal ausente)")


async def registrar_ativacao_manual(bot, guild_id, ext_id, dias):
    """Log de ativação manual pelo dono (Req 13.3)."""
    guild = bot.get_guild(int(guild_id)) if (bot and guild_id) else None
    nome_srv = guild.name if guild else f"Servidor {guild_id}"
    embed = disnake.Embed(
        title="🛠️ Ativação Manual de Extensão",
        description=(
            f"**Servidor:** {nome_srv} (`{guild_id}`)\n"
            f"**Extensão:** {_nomes_extensoes([ext_id])}\n"
            f"**Duração:** `{dias}` dias\n"
            f"**Origem:** ativação manual pelo dono"
        ),
        color=0x3498db,
        timestamp=datetime.now(),
    )
    embed.set_footer(text="Marketplace de Extensões")
    if not await _enviar(bot, embed):
        print(f"[EXT_LOG] Ativação manual: guild={guild_id} ext={ext_id} dias={dias} (canal ausente)")


async def registrar_expiracao(bot, guild_id, ext_id):
    """Log de expiração de uma extensão (Req 13.4)."""
    guild = bot.get_guild(int(guild_id)) if (bot and guild_id) else None
    nome_srv = guild.name if guild else f"Servidor {guild_id}"
    embed = disnake.Embed(
        title="⏰ Extensão Expirada",
        description=(
            f"**Servidor:** {nome_srv} (`{guild_id}`)\n"
            f"**Extensão:** {_nomes_extensoes([ext_id])}\n"
            f"O acesso foi bloqueado até uma nova assinatura."
        ),
        color=0xe74c3c,
        timestamp=datetime.now(),
    )
    embed.set_footer(text="Marketplace de Extensões")
    if not await _enviar(bot, embed):
        print(f"[EXT_LOG] Expiração: guild={guild_id} ext={ext_id} (canal ausente)")
