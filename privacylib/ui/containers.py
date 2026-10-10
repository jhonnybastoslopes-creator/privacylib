"""Fonte única de verdade para montagem de containers de UI (disnake).

Este módulo centraliza o `ContainerUtils` que hoje existe duplicado em 4 cópias
idênticas (tickets, loja, giveaways, cloud). A versão canônica aqui é a de
`modules/tickets/config/container_utils.py`, por conter o fallback
anti-container-vazio mais refinado (separadores condicionais ao conteúdo real).

A dedução das 4 cópias para reexportarem deste módulo é feita na Fase C
(tarefa 19.1); aqui apenas estabelecemos a implementação canônica.
"""

import disnake

__all__ = ["ContainerUtils", "container"]


class ContainerUtils:
    """Utilitário único de montagem de containers V2 do disnake."""

    @staticmethod
    def parse_hex_to_colour(value: str | None) -> disnake.Colour | None:
        """Converte uma string hexadecimal de 6 dígitos em `disnake.Colour`.

        Aceita os prefixos opcionais `#` e `0x`. Para qualquer entrada que não
        corresponda a um hex de 6 dígitos válido (ou nula/vazia), retorna
        deterministicamente `None`, sem lançar exceção — o chamador
        (`montar_container`) trata `None` como "sem cor de destaque", mantendo
        um comportamento padrão determinístico.
        """
        if not value:
            return None
        try:
            s = str(value).strip().lower()
            if s.startswith("0x"):
                s = s[2:]
            if s.startswith("#"):
                s = s[1:]
            if len(s) != 6:
                return None
            return disnake.Colour(int(s, 16))
        except Exception:
            return None

    @staticmethod
    def montar_container(
        conteudo: str | None,
        imagem_url: str | None = None,
        cor_hex: str | None = None,
        extra_children: list | None = None,
        thumbnail_url: str | None = None,
    ) -> disnake.ui.Container:
        """Monta um `disnake.ui.Container` a partir dos argumentos fornecidos.

        Garante (fallback anti-container-vazio) que o container nunca seja
        renderizado visualmente vazio: se nenhum `TextDisplay`/`Section` for
        gerado a partir dos argumentos, insere exatamente um `TextDisplay`
        placeholder no topo.
        """
        children = []

        # Lidar com a Seção (Conteúdo e Thumbnail)
        thumbnail_accessory = None
        if thumbnail_url and (thumbnail_url.startswith("http://") or thumbnail_url.startswith("https://")):
            thumbnail_accessory = disnake.ui.Thumbnail(media=thumbnail_url)

        if conteudo:
            if thumbnail_accessory:
                children.append(disnake.ui.Section(
                    disnake.ui.TextDisplay(conteudo),
                    accessory=thumbnail_accessory
                ))
            else:
                children.append(disnake.ui.TextDisplay(conteudo))
        elif thumbnail_accessory:
            children.append(disnake.ui.Section(
                accessory=thumbnail_accessory
            ))

        # Lidar com a Imagem Principal
        if imagem_url and (imagem_url.startswith("http://") or imagem_url.startswith("https://")):
            try:
                # Só adicionar separator se houver conteúdo antes (não apenas thumbnail)
                if children and conteudo:
                    children.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small))

                children.append(
                    disnake.ui.MediaGallery(
                        disnake.MediaGalleryItem(media=imagem_url)
                    )
                )
            except Exception:
                pass

        if extra_children:
            # Só adicionar separator se houver conteúdo ou imagem antes
            if children and (conteudo or imagem_url):
                children.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small))
            children.extend(extra_children)

        # Fallback anti-container-vazio: se não houver nenhum texto/seção (só botões,
        # só imagem, ou nada), insere um TextDisplay padrão no topo para o painel
        # nunca renderizar visualmente vazio.
        tem_texto = any(
            isinstance(c, (disnake.ui.TextDisplay, disnake.ui.Section))
            for c in children
        )
        if not tem_texto:
            children.insert(0, disnake.ui.TextDisplay("\u200b"))

        cor_container = ContainerUtils.parse_hex_to_colour(cor_hex)
        return disnake.ui.Container(*children, accent_colour=cor_container) if cor_container else disnake.ui.Container(*children)


def container(conteudo: str | None = None, **kwargs) -> disnake.ui.Container:
    """Função de conveniência que delega a `ContainerUtils.montar_container`.

    Repassa `conteudo` e quaisquer argumentos nomeados sem alteração.
    """
    return ContainerUtils.montar_container(conteudo, **kwargs)
