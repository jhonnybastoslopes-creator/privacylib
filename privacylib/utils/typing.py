"""
privacylib.utils.typing — helpers de efeito de digitação (apresentação).

Fase B da migração: a implementação **real** dos helpers de "typing" agora mora
aqui, em ``privacylib/utils/typing.py``. O módulo antigo
``functions/typing_helper.py`` passou a ser um *shim* de compatibilidade que
reexporta estes nomes daqui por identidade, de modo que todo consumidor
existente (``from functions.typing_helper import ...``) continue funcionando sem
alteração:

    functions.typing_helper.send_with_typing     is privacylib.utils.typing.send_with_typing
    functions.typing_helper.reply_with_typing    is privacylib.utils.typing.reply_with_typing
    functions.typing_helper.calculate_typing_time is privacylib.utils.typing.calculate_typing_time

Funções públicas: ``send_with_typing``, ``reply_with_typing``,
``calculate_typing_time``.

_Requirements: 8.2, 14.1, 14.3_
"""
import asyncio
import random


def calculate_typing_time(text: str) -> float:
    """
    Calcula o tempo de typing baseado no tamanho da mensagem
    
    :param text: Texto da mensagem
    :return: Tempo em segundos
    """
    if not text:
        return 1.0
    
    # Base: 1 segundo + 0.05 segundos por caractere
    # Isso simula uma velocidade de digitação de ~20 caracteres por segundo
    base_time = 1.0
    char_time = len(text) * 0.05
    
    # Adicionar variação aleatória de ±20%
    variation = random.uniform(0.8, 1.2)
    
    total_time = (base_time + char_time) * variation
    
    # Limitar entre 1 e 5 segundos
    return max(1.0, min(5.0, total_time))


async def send_with_typing(channel, **kwargs):
    """
    Envia mensagem com efeito de typing para parecer mais humano
    
    :param channel: Canal ou usuário onde enviar a mensagem
    :param kwargs: Argumentos para enviar a mensagem (content, embed, components, etc.)
    :return: A mensagem enviada
    """
    content = kwargs.get('content', '')
    typing_time = calculate_typing_time(content)
    
    async with channel.typing():
        await asyncio.sleep(typing_time)
        return await channel.send(**kwargs)


async def reply_with_typing(message, **kwargs):
    """
    Responde a uma mensagem com efeito de typing
    
    :param message: Mensagem para responder
    :param kwargs: Argumentos para enviar a resposta
    :return: A mensagem enviada
    """
    content = kwargs.get('content', '')
    typing_time = calculate_typing_time(content)
    
    async with message.channel.typing():
        await asyncio.sleep(typing_time)
        return await message.reply(**kwargs)


__all__ = ["send_with_typing", "reply_with_typing", "calculate_typing_time"]
