"""Canal de comandos do Gremlin já aberto, por socket Unix.

Para que serve: um atalho global do KDE (ex.: Meta+G) roda o script
scripts/gremlin-perguntar, que pede a este servidor para abrir a janela
de perguntas. Atalho global dentro do próprio app não funciona bem no
Wayland; o KDE cuida do atalho e nós só recebemos o recado.

Protocolo, uma linha em UTF-8 em cada sentido:
    cliente -> "perguntar\\n"
    servidor -> "ok\\n"  ou  "erro: <motivo>\\n"

O cliente (scripts/gremlin-perguntar) usa só a biblioteca padrão, sem
importar este módulo: importar o pacote src carrega o PySide6 (~200 ms)
e o atalho precisa responder na hora. Por isso socket_path() existe
duplicada lá; um teste garante que as duas dão o mesmo caminho.
"""

from __future__ import annotations

import os
import socket

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

COMANDOS = {"perguntar"}
_MAX_LINHA = 256


def socket_path() -> str:
    """Caminho do socket. $XDG_RUNTIME_DIR só o próprio usuário acessa."""
    if caminho := os.environ.get("GREMLIN_IPC_PATH"):
        return caminho
    if runtime := os.environ.get("XDG_RUNTIME_DIR"):
        return os.path.join(runtime, "linux-desktop-gremlin.sock")
    return f"/tmp/linux-desktop-gremlin-{os.getuid()}.sock"


def _tem_alguem_escutando(caminho: str) -> bool:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(caminho)
            return True
        except OSError:
            return False


class CommandServer(QObject):
    perguntar_pedido = Signal()

    def __init__(self, caminho: str | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.caminho = caminho or socket_path()
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._on_new_connection)
        self._buffers: dict[QLocalSocket, bytes] = {}

    def start(self) -> bool:
        """Começa a escutar. False se não deu (ex.: outro Gremlin já escuta)."""
        # Com UserAccessOption o Qt cria o socket à parte e o MOVE para o
        # caminho final, sobrescrevendo o que estiver lá. Isso já limpa a
        # sobra de um Gremlin que crashou, mas também passaria por cima de
        # um Gremlin VIVO (ex.: dois personagens abertos) sem reclamar.
        # Por isso a checagem abaixo é a única coisa que impede o roubo.
        if os.path.exists(self.caminho) and _tem_alguem_escutando(self.caminho):
            print(f"[Gremlin] atalho já atendido por outro Gremlin em {self.caminho}")
            return False

        if not self._server.listen(self.caminho):
            print(f"[Gremlin] não consegui abrir o socket {self.caminho}: "
                  f"{self._server.errorString()}")
            return False
        return True

    def close(self) -> None:
        self._server.close()  # também apaga o arquivo do socket

    @property
    def escutando(self) -> bool:
        return self._server.isListening()

    # --- internos ---------------------------------------------------------------

    def _on_new_connection(self) -> None:
        while (conexao := self._server.nextPendingConnection()) is not None:
            self._buffers[conexao] = b""
            conexao.readyRead.connect(lambda c=conexao: self._on_ready_read(c))
            # Só destrói a conexão quando ela termina de fato: destruir logo
            # após responder poderia descartar o "ok" antes de ser enviado.
            conexao.disconnected.connect(lambda c=conexao: self._forget(c))

    def _on_ready_read(self, conexao: QLocalSocket) -> None:
        if conexao not in self._buffers:  # já respondida
            return
        buffer = self._buffers[conexao] + bytes(conexao.readAll().data())
        if b"\n" not in buffer:
            if len(buffer) > _MAX_LINHA:  # ninguém legítimo manda isso
                self._responder(conexao, "erro: linha longa demais")
            else:
                self._buffers[conexao] = buffer
            return

        linha = buffer.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip()
        if linha not in COMANDOS:
            self._responder(conexao, f"erro: comando desconhecido {linha!r}")
            return

        self._responder(conexao, "ok")
        if linha == "perguntar":
            self.perguntar_pedido.emit()

    def _responder(self, conexao: QLocalSocket, texto: str) -> None:
        self._buffers.pop(conexao, None)  # marca como respondida
        conexao.write(f"{texto}\n".encode())
        conexao.flush()
        # Espera o que falta ser escrito e então emite disconnected,
        # que chama _forget.
        conexao.disconnectFromServer()

    def _forget(self, conexao: QLocalSocket) -> None:
        self._buffers.pop(conexao, None)
        conexao.deleteLater()
