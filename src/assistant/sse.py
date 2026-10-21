"""Parser incremental de Server-Sent Events.

Puro: recebe bytes, devolve eventos. Não sabe nada de rede nem de Qt,
por isso é testável sem servidor nenhum.

Por que trabalhar em bytes e não em str: a rede entrega pedaços de
tamanho arbitrário, e um caractere UTF-8 de vários bytes ("á" = 2 bytes)
pode chegar partido entre dois pedaços. Decodificar cada pedaço isolado
quebraria o caractere. Aqui só decodificamos linhas completas.

Referência do formato: https://html.spec.whatwg.org/multipage/server-sent-events.html
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SSEEvent:
    type: str
    data: str


class SSEParser:
    def __init__(self) -> None:
        self._buffer = b""
        self._event_type = ""
        self._data_lines: list[str] = []
        # A última linha terminou num \r no fim do pedaço. Se o próximo
        # pedaço começar com \n, é o resto do mesmo \r\n e deve ser pulado.
        self._skip_lf = False

    def feed(self, chunk: bytes) -> list[SSEEvent]:
        """Consome um pedaço da resposta e devolve os eventos que fecharam."""
        if self._skip_lf and chunk:
            if chunk.startswith(b"\n"):
                chunk = chunk[1:]
            self._skip_lf = False

        self._buffer += chunk
        eventos: list[SSEEvent] = []

        while True:
            fim = self._next_line_end()
            if fim is None:
                break
            linha_bytes, self._buffer = self._split_line(fim)
            evento = self._process_line(linha_bytes.decode("utf-8", errors="replace"))
            if evento is not None:
                eventos.append(evento)

        return eventos

    # --- internos ---------------------------------------------------------

    def _next_line_end(self) -> int | None:
        """Posição do primeiro terminador de linha (\\n, \\r ou \\r\\n)."""
        for i, byte in enumerate(self._buffer):
            if byte in (0x0A, 0x0D):  # \n ou \r
                return i
        return None

    def _split_line(self, fim: int) -> tuple[bytes, bytes]:
        linha = self._buffer[:fim]
        if self._buffer[fim : fim + 2] == b"\r\n":
            return linha, self._buffer[fim + 2 :]
        if self._buffer[fim : fim + 1] == b"\r" and fim == len(self._buffer) - 1:
            # \r no fim do pedaço: a linha já acabou, mas talvez o \n do
            # \r\n ainda esteja a caminho.
            self._skip_lf = True
        return linha, self._buffer[fim + 1 :]

    def _process_line(self, linha: str) -> SSEEvent | None:
        if linha == "":
            return self._dispatch()

        if linha.startswith(":"):  # comentário / keep-alive
            return None

        campo, sep, valor = linha.partition(":")
        if sep and valor.startswith(" "):
            valor = valor[1:]

        if campo == "event":
            self._event_type = valor
        elif campo == "data":
            self._data_lines.append(valor)
        # "id" e "retry" não são usados pelo Stego; ignorados de propósito.
        return None

    def _dispatch(self) -> SSEEvent | None:
        if not self._data_lines:
            self._event_type = ""
            return None

        evento = SSEEvent(
            type=self._event_type or "message",
            data="\n".join(self._data_lines),
        )
        self._event_type = ""
        self._data_lines = []
        return evento
