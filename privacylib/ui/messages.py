"""Mensagens e embeds (apresentação) — implementação canônica (Fase B).

A lógica real das classes ``message`` e ``embed_message`` foi **movida** de
``functions/message.py`` para este módulo. As assinaturas e o comportamento
são preservados EXATAMENTE como no original. O módulo antigo
(``functions/message.py``) passou a ser um shim que reexporta estes mesmos
objetos por identidade:

    functions.message.message       is privacylib.ui.messages.message
    functions.message.embed_message is privacylib.ui.messages.embed_message

A classe ``message`` expõe os métodos públicos ``wait``, ``missing_perms``,
``error`` e ``success``. A classe ``embed_message`` expõe os mesmos métodos
acrescidos de ``plain``.

Nota de segurança a ciclos: a dependência de emojis é consumida via
``functions.emoji`` (leaf em relação à camada de UI — resolve para o mesmo
objeto único de ``privacylib.emoji.emoji``), mantendo o comportamento original.

_Requirements: 14.1, 14.3_
"""

import disnake

from functions.emoji import emoji

__all__ = ["message", "embed_message"]


class message:
    @staticmethod
    async def wait(inter: disnake.MessageInteraction, send=False, ephemeral=True, followup=False) -> disnake.Message:
        components = disnake.ui.TextDisplay(f"{emoji.loading} Carregando informações...")

        if send:
            return await inter.response.send_message(
                components=components,
                flags=disnake.MessageFlags(is_components_v2=True),
                ephemeral=ephemeral
            )
        elif followup:
            return await inter.followup.send(
                components=components,
                flags=disnake.MessageFlags(is_components_v2=True),
                ephemeral=ephemeral
            )
        else:
            if not inter.response.is_done():
                try:
                    await inter.response.defer(with_message=False)
                except disnake.NotFound:
                    # Interação expirou, ignorar silenciosamente
                    return None

            try:
                return await inter.edit_original_message(
                    embed=None,
                    components=components
                )
            except disnake.NotFound:
                # Interação expirou, ignorar silenciosamente
                return None

    @staticmethod
    async def missing_perms(inter: disnake.MessageInteraction) -> disnake.Message:
        components = [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"{emoji.wrong} Você não tem permissão para usar este comando")
            )
        ]
        return await inter.response.send_message(
            components=components,
            ephemeral=True	,
            flags=disnake.MessageFlags(is_components_v2=True)
        )

    @staticmethod
    async def error(inter: disnake.MessageInteraction, message: str, send=False, followup=False, component=None) -> disnake.Message:
        components = [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"{emoji.wrong} {message}"),
            )
        ]
        if component:
            if isinstance(component, (list, tuple)):
                components.extend(component)
            else:
                components.append(component)

        if send:
            return await inter.response.send_message(
                components=components,
                ephemeral=True,
                flags=disnake.MessageFlags(is_components_v2=True)
            )
        elif followup:
            return await inter.followup.send(
                components=components,
                ephemeral=True,
                flags=disnake.MessageFlags(is_components_v2=True)
            )
        else:
            return await inter.edit_original_message(
                embed=None,
                components=components
            )

    @staticmethod
    async def success(inter: disnake.MessageInteraction, message: str, send=False, followup=False, component=None) -> disnake.Message:
        components = [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"{emoji.correct} {message}"),
            )
        ]
        if component:
            if isinstance(component, (list, tuple)):
                components.extend(component)
            else:
                components.append(component)

        if send:
            return await inter.response.send_message(
                components=components,
                ephemeral=True,
                flags=disnake.MessageFlags(is_components_v2=True)
            )
        elif followup:
            return await inter.followup.send(
                components=components,
                ephemeral=True,
                flags=disnake.MessageFlags(is_components_v2=True)
            )
        else:
            return await inter.edit_original_message(
                embed=None,
                components=components
            )


class embed_message:
    @staticmethod
    async def wait(inter: disnake.MessageInteraction, send=False, ephemeral=True, followup=False) -> disnake.Message:
        content = f"{emoji.loading} Carregando informações..."
        if send:
            return await inter.response.send_message(content=content, ephemeral=ephemeral)
        elif followup:
            return await inter.followup.send(content=content, ephemeral=ephemeral)
        else:
            if not inter.response.is_done():
                try:
                    await inter.response.defer(with_message=False)
                except disnake.NotFound:
                    # Interação expirou, ignorar silenciosamente
                    return None
            # Não usar 'content' ao editar mensagens, para compatibilidade com components v2
            try:
                embed = disnake.Embed(description=content)
                return await inter.edit_original_message(embed=embed, components=[])
            except disnake.NotFound:
                # Interação expirou, ignorar silenciosamente
                return None

    @staticmethod
    async def missing_perms(inter: disnake.MessageInteraction) -> disnake.Message:
        content = f"{emoji.wrong} Você não tem permissão para usar este comando"
        return await inter.response.send_message(content=content, ephemeral=True)

    @staticmethod
    async def error(inter: disnake.MessageInteraction, message: str, send=False, followup=False, component=None) -> disnake.Message:
        content = f"{emoji.wrong} {message}"

        if send:
            return await inter.response.send_message(content=content, ephemeral=True, components=component)
        elif followup:
            return await inter.followup.send(content=content, ephemeral=True, components=component)
        else:
            # Evitar 'content' em edição
            embed = disnake.Embed(description=content)
            return await inter.edit_original_message(embed=embed, components=component)

    @staticmethod
    async def success(inter: disnake.MessageInteraction, message: str, send=False, followup=False, component=None) -> disnake.Message:
        content = f"{emoji.correct} {message}"

        if send:
            return await inter.response.send_message(content=content, ephemeral=True, components=component)
        elif followup:
            return await inter.followup.send(content=content, ephemeral=True, components=component)
        else:
            # Evitar 'content' em edição
            embed = disnake.Embed(description=content)
            return await inter.edit_original_message(embed=embed, components=component)

    @staticmethod
    async def plain(inter: disnake.MessageInteraction, content: str, send=False, followup=False, component=None) -> disnake.Message:
        if send:
            return await inter.response.send_message(content=content, ephemeral=True, components=component)
        elif followup:
            return await inter.followup.send(content=content, ephemeral=True, components=component)
        else:
            # Evitar 'content' em edição
            embed = disnake.Embed(description=content)
            return await inter.edit_original_message(embed=embed, components=component)
