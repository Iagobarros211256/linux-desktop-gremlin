"""Ponte entre o Gremlin e o Stego (RAG local).

Este pacote não contém lógica de busca (isso é do Stego) nem de animação
(isso é do gremlin.py). Ele só traduz o protocolo HTTP/SSE do Stego em
sinais Qt que a interface pode consumir.
"""

from .sse import SSEEvent, SSEParser
from .stego_client import DEFAULT_BASE_URL, StegoClient

__all__ = ["DEFAULT_BASE_URL", "SSEEvent", "SSEParser", "StegoClient"]
