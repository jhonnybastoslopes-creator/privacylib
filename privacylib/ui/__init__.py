"""Fachada da camada de apresentação (`privacylib.ui`).

Expõe os pontos de entrada estáveis da UI, mantendo o pacote importável e os
submódulos (`containers`, `messages`, `text`) acessíveis diretamente.

Símbolos públicos:

- ``container``        — função de conveniência (``ui.container(conteudo=..., cor_hex=...)``)
- ``ContainerUtils``   — utilitário único de montagem de containers V2
- ``messages``         — submódulo (``ui.messages``) com ``message``/``embed_message``
- ``text``             — submódulo (``ui.text``) com os helpers de texto seguro
- ``message``          — classe de mensagens (``ui.message.wait/error/success/...``)
- ``embed_message``    — classe de mensagens em embed (``+ plain``)

Garantias de identidade (reexport por identidade — Fase A):

    privacylib.ui.container        is privacylib.ui.containers.container
    privacylib.ui.ContainerUtils   is privacylib.ui.containers.ContainerUtils
    privacylib.ui.message          is privacylib.ui.messages.message
    privacylib.ui.embed_message    is privacylib.ui.messages.embed_message
    privacylib.ui.messages         is <módulo privacylib.ui.messages>
    privacylib.ui.text             is <módulo privacylib.ui.text>

_Requirements: 5.2, 6.1_
"""

# Submódulos expostos como atributos do pacote (``ui.messages`` / ``ui.text``).
from privacylib.ui import messages, text  # noqa: F401

# Containers: função de conveniência + utilitário canônico.
from privacylib.ui.containers import ContainerUtils, container  # noqa: F401

# Classes de mensagem reexportadas no topo (``ui.message`` / ``ui.embed_message``).
from privacylib.ui.messages import embed_message, message  # noqa: F401

__all__ = [
    "container",
    "ContainerUtils",
    "messages",
    "text",
    "message",
    "embed_message",
]
