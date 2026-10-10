"""
privacylib/extensions/qr.py — Geração do QR Code PIX com a logo do bot.

Gera a imagem do QR code localmente a partir do código PIX copia-e-cola e
sobrepõe a foto de perfil do bot no centro, como marca registrada (Req 14).

- Usa correção de erro ALTA (H, ~30%) para permanecer legível com a logo no meio.
- A composição de imagem roda em asyncio.to_thread (não bloqueia o event loop).
- Se o avatar não puder ser obtido, gera o QR sem a logo (fallback).
- Nada é salvo em disco/banco: retorna os bytes do PNG para anexar no Discord.

_Requirements: 14.1, 14.3
"""
import asyncio
from io import BytesIO
from typing import Optional

import aiohttp


async def _baixar_avatar_bytes(bot) -> Optional[bytes]:
    """Baixa a foto de perfil do bot como bytes PNG. None se indisponível."""
    try:
        user = getattr(bot, "user", None)
        if not user:
            return None
        asset = user.display_avatar
        # Preferir formato estático PNG, tamanho médio
        try:
            asset = asset.with_format("png").with_size(256)
        except Exception:
            pass
        return await asset.read()
    except Exception:
        return None


def _compor_qr_com_logo(pix_code: str, logo_bytes: Optional[bytes]) -> bytes:
    """
    (Síncrono — deve rodar em thread.) Gera o QR e opcionalmente centraliza a logo.
    Retorna PNG em bytes.
    """
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H
    from PIL import Image

    # version mínimo garante módulos suficientes para a logo não invadir os
    # localizadores; box_size alto deixa a imagem nítida.
    qr = qrcode.QRCode(
        version=6,                           # fixa um QR maior (mais redundância)
        error_correction=ERROR_CORRECT_H,    # tolera ~30% de oclusão (logo central)
        box_size=10,
        border=4,
    )
    qr.add_data(pix_code)
    qr.make(fit=True)                        # cresce a versão se o dado for grande

    img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
    qr_w, qr_h = img.size

    if logo_bytes:
        try:
            logo = Image.open(BytesIO(logo_bytes)).convert("RGBA")
            # Logo conservadora: ~15% da largura do QR. Com fundo branco fica
            # ~18%, bem abaixo do limite de ~30% do nível H → mantém legível.
            alvo = int(qr_w * 0.15)
            logo = logo.resize((alvo, alvo), Image.LANCZOS)

            # Fundo branco atrás da logo para garantir contraste/leitura
            pad = max(2, int(alvo * 0.12))
            fundo_tam = alvo + pad * 2
            fundo = Image.new("RGBA", (fundo_tam, fundo_tam), (255, 255, 255, 255))
            fundo.paste(logo, (pad, pad), logo)

            pos = ((qr_w - fundo_tam) // 2, (qr_h - fundo_tam) // 2)
            img.alpha_composite(fundo, pos)
        except Exception:
            # Se falhar ao compor a logo, mantém o QR puro (ainda válido)
            pass

    out = BytesIO()
    img.convert("RGB").save(out, format="PNG")
    out.seek(0)
    return out.getvalue()


async def gerar_qr_com_logo(pix_copia_cola: str, bot) -> bytes:
    """
    Gera o PNG do QR PIX com a logo do bot no centro.
    Retorna os bytes do PNG. Nunca lança: em caso de erro na logo, gera sem ela.
    """
    logo_bytes = await _baixar_avatar_bytes(bot)
    # Processamento de imagem fora do event loop (Req 14.6)
    return await asyncio.to_thread(_compor_qr_com_logo, pix_copia_cola, logo_bytes)


async def gerar_qr_simples(pix_copia_cola: str) -> bytes:
    """Gera o QR sem logo (fallback ou uso genérico)."""
    return await asyncio.to_thread(_compor_qr_com_logo, pix_copia_cola, None)
