"""Cliente do endpoint GET /api/ask do Stego, em sinais Qt.

Contrato do Stego (src/stego/server.py), conferido rodando o servidor:

    event: hits   data: [ {chunk_id, content, citation, source_path, ...}, ... ]
    event: token  data: "pedaço de texto"            (string JSON)
    event: done   data: {timings, tokens_per_second, refused}
    event: error  data: "mensagem"                   (string JSON)

Detalhes que este cliente precisa tratar e que não são óbvios:

* `error` pode chegar DEPOIS de tokens (Ollama caiu no meio da geração)
  ou ANTES de `hits` (Ollama fora do ar já no embedding da pergunta).
* Depois de `error` não vem `done`: o servidor só fecha a conexão.
* A recusa ("Nao encontrei isso no seu acervo.") chega como `token`
  comum; quem diz que foi recusa é `done.refused`.
* Pergunta vazia devolve HTTP 400 em texto puro, não SSE.

Por que QNetworkAccessManager e não httpx numa thread: o QNAM já é
assíncrono e entrega os dados no event loop do Qt. Nada de QThread,
lock ou fila entre threads, e a animação do Gremlin nunca trava.
Também não adiciona dependência: QtNetwork já vem no PySide6.

Todo pedido termina em exatamente UM destes sinais:
finished, failed ou cancelled.
"""

from __future__ import annotations

import json
import os
from functools import partial
from urllib.parse import quote, urlencode

from PySide6.QtCore import QMetaObject, QObject, Qt, QUrl, Signal
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkProxy,
    QNetworkReply,
    QNetworkRequest,
)

from .sse import SSEEvent, SSEParser


def _default_base_url() -> str:
    if url := os.environ.get("GREMLIN_STEGO_URL"):
        return url
    # Mesma variável que o Stego usa para escolher a porta.
    return f"http://127.0.0.1:{os.environ.get('STEGO_PORT', '8080')}"


DEFAULT_BASE_URL = _default_base_url()

# Sem bytes por esse tempo = Stego travou. Generoso de propósito: com o
# modelo frio, carregar o llama3.1:8b antes do primeiro token demora.
DEFAULT_TRANSFER_TIMEOUT_MS = 180_000


class StegoClient(QObject):
    hits_received = Signal(list)  # trechos recuperados (fontes)
    token_received = Signal(str)  # pedaço da resposta
    finished = Signal(dict)  # payload do evento done
    failed = Signal(str)  # mensagem legível para o usuário
    cancelled = Signal()

    def __init__(
        self,
        base_url: str | None = None,
        transfer_timeout_ms: int = DEFAULT_TRANSFER_TIMEOUT_MS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.transfer_timeout_ms = transfer_timeout_ms

        self._manager = QNetworkAccessManager(self)
        # O Stego só escuta em 127.0.0.1. Se o sistema tiver http_proxy
        # configurado, o Qt mandaria a pergunta para o proxy.
        self._manager.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))

        self._reply: QNetworkReply | None = None
        self._parser = SSEParser()
        self._error_body = b""

    # --- API pública --------------------------------------------------------

    @property
    def is_busy(self) -> bool:
        return self._reply is not None

    def ask(self, question: str, include_restricted: bool = False) -> None:
        """Dispara a pergunta. Uma pergunta em andamento é cancelada antes."""
        question = question.strip()
        if not question:
            raise ValueError("pergunta vazia")

        if self._reply is not None:
            self.cancel()

        self._parser = SSEParser()
        self._error_body = b""

        request = QNetworkRequest(self._ask_url(question, include_restricted))
        request.setRawHeader(b"Accept", b"text/event-stream")
        request.setTransferTimeout(self.transfer_timeout_ms)

        reply = self._manager.get(request)
        self._reply = reply
        reply.readyRead.connect(partial(self._on_ready_read, reply))
        reply.finished.connect(partial(self._on_finished, reply))

    def cancel(self) -> None:
        """Interrompe a pergunta atual. Sem efeito se não houver nenhuma."""
        if self._reply is None:
            return
        self._close_request()
        self.cancelled.emit()

    # --- internos -------------------------------------------------------------

    def _ask_url(self, question: str, include_restricted: bool) -> QUrl:
        # quote (e não quote_plus): o servidor usa parse_qs, que lê "+"
        # como espaço. Com quote, "C++" vira "C%2B%2B" e chega intacto.
        query = urlencode(
            {"q": question, "restricted": "1" if include_restricted else "0"},
            quote_via=quote,
        )
        return QUrl(f"{self.base_url}/api/ask?{query}", QUrl.ParsingMode.StrictMode)

    def _status_code(self, reply: QNetworkReply) -> int | None:
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        return int(status) if status is not None else None

    def _on_ready_read(self, reply: QNetworkReply) -> None:
        if reply is not self._reply:
            return

        dados = bytes(reply.readAll().data())
        if self._status_code(reply) != 200:
            self._error_body += dados
            return

        for evento in self._parser.feed(dados):
            self._handle_event(evento)
            if reply is not self._reply:  # evento terminal fechou o pedido
                return

    def _handle_event(self, evento: SSEEvent) -> None:
        try:
            dados = json.loads(evento.data)
        except json.JSONDecodeError:
            self._fail(f"o Stego mandou um evento '{evento.type}' ilegível")
            return

        match evento.type:
            case "hits":
                self.hits_received.emit(list(dados))
            case "token":
                self.token_received.emit(str(dados))
            case "done":
                self._close_request()
                self.finished.emit(dict(dados))
            case "error":
                self._fail(str(dados))
            case _:
                pass  # evento novo de uma versão futura do Stego: ignora

    def _on_finished(self, reply: QNetworkReply) -> None:
        if reply is not self._reply:
            return  # já encerrado por done, error ou cancel

        # Resto que ainda não passou pelo readyRead.
        self._on_ready_read(reply)
        if reply is not self._reply:
            return

        self._fail(self._describe_failure(reply))

    def _describe_failure(self, reply: QNetworkReply) -> str:
        status = self._status_code(reply)
        if status is not None and status != 200:
            corpo = self._error_body.decode("utf-8", errors="replace").strip()
            return f"o Stego recusou a pergunta (HTTP {status}): {corpo or 'sem detalhes'}"

        erro = reply.error()
        E = QNetworkReply.NetworkError
        if erro in (E.ConnectionRefusedError, E.HostNotFoundError):
            # "stego" só existe dentro do ambiente do projeto Stego, não
            # no PATH: por isso o comando sugerido é o do uv.
            return (
                f"o Stego não está rodando em {self.base_url} "
                "(na pasta do Stego, rode: uv run stego serve)"
            )
        if erro in (E.TimeoutError, E.OperationCanceledError):
            segundos = self.transfer_timeout_ms // 1000
            return f"o Stego ficou {segundos}s sem responder"
        if erro != E.NoError:
            return f"falha de rede falando com o Stego: {reply.errorString()}"
        return "a conexão com o Stego fechou antes do fim da resposta"

    def _fail(self, mensagem: str) -> None:
        self._close_request()
        self.failed.emit(mensagem)

    def _close_request(self) -> None:
        """Solta o reply ANTES de emitir o sinal terminal.

        Assim um slot que chame ask() de novo (ex.: "tentar outra vez")
        encontra o cliente livre, e qualquer sinal atrasado do reply
        antigo é ignorado por não ser mais o reply atual.

        abort() e deleteLater() vão pela fila de eventos do PRÓPRIO reply
        (QueuedConnection), nunca por um callback Python solto: se o
        reply morrer antes (ex.: o StegoClient foi destruído junto com o
        QNetworkAccessManager), o Qt descarta a chamada em vez de tocar
        num objeto já liberado (segfault). Também evita abortar o reply de
        dentro do próprio readyRead dele.
        """
        reply, self._reply = self._reply, None
        if reply is None:
            return
        reply.readyRead.disconnect()
        reply.finished.disconnect()
        QMetaObject.invokeMethod(reply, "abort", Qt.ConnectionType.QueuedConnection)
        reply.deleteLater()
