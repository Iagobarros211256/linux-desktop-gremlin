import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Qt Quick sem GPU nos testes (o balão é QML).
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtWidgets import QApplication  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def ipc_path(monkeypatch):
    """Todo teste usa um socket próprio, nunca o do Gremlin de verdade.

    Pasta curta em /tmp de propósito: caminho de socket Unix tem limite
    de 108 bytes, e o tmp_path do pytest costuma passar disso.
    """
    import shutil
    import tempfile

    pasta = tempfile.mkdtemp(prefix="g", dir="/tmp")
    caminho = os.path.join(pasta, "s.sock")
    monkeypatch.setenv("GREMLIN_IPC_PATH", caminho)
    yield caminho
    shutil.rmtree(pasta, ignore_errors=True)


@pytest.fixture(scope="session")
def qapp():
    # QApplication (e não QCoreApplication) porque a janela usa widgets;
    # só pode existir uma por processo, então é a mesma para todos os testes.
    return QApplication.instance() or QApplication([])


class _FakeStegoHandler(BaseHTTPRequestHandler):
    """Reproduz cenários do /api/ask. O cenário fica em server.scenario."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.requests.append(self.path)
        cenario = self.server.scenario

        if cenario == "http400":
            corpo = b"pergunta vazia"
            self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.end_headers()

        try:
            if cenario.startswith("fixture:"):
                dados = (FIXTURES / cenario.removeprefix("fixture:")).read_bytes()
                # Pedaços pequenos e espaçados: força vários readyRead e
                # cortes no meio de eventos, como numa rede de verdade.
                for i in range(0, len(dados), 97):
                    self.wfile.write(dados[i : i + 97])
                    self.wfile.flush()
                    time.sleep(0.002)
            elif cenario == "close_without_done":
                self.wfile.write(b'event: hits\ndata: []\n\nevent: token\ndata: "meia "\n\n')
            elif cenario == "hang":
                self.wfile.write(b"event: hits\ndata: []\n\n")
                self.wfile.flush()
                time.sleep(3)
        except (BrokenPipeError, ConnectionResetError):
            pass


@pytest.fixture
def fake_stego():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeStegoHandler)
    server.daemon_threads = True
    server.scenario = "fixture:ask_ok.sse"
    server.requests = []
    server.base_url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
