import socket
from urllib.parse import parse_qs, urlparse

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from src.assistant.stego_client import StegoClient

TERMINAIS = {"finished", "failed", "cancelled"}


class Gravador:
    """Registra todos os sinais do cliente, na ordem em que chegam."""

    def __init__(self, client: StegoClient):
        self.sinais: list[tuple[str, object]] = []
        client.hits_received.connect(lambda v: self.sinais.append(("hits", v)))
        client.token_received.connect(lambda v: self.sinais.append(("token", v)))
        client.finished.connect(lambda v: self.sinais.append(("finished", v)))
        client.failed.connect(lambda v: self.sinais.append(("failed", v)))
        client.cancelled.connect(lambda: self.sinais.append(("cancelled", None)))

    def nomes(self) -> list[str]:
        return [nome for nome, _ in self.sinais]

    def texto(self) -> str:
        return "".join(v for nome, v in self.sinais if nome == "token")

    def terminais(self) -> list[tuple[str, object]]:
        return [s for s in self.sinais if s[0] in TERMINAIS]

    def esperar(self, quantos: int = 1, timeout_ms: int = 5000) -> None:
        """Roda o event loop até `quantos` sinais terminais (ou estoura)."""
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        checa = QTimer()
        checa.timeout.connect(
            lambda: loop.quit() if len(self.terminais()) >= quantos else None
        )
        timer.start(timeout_ms)
        checa.start(5)
        loop.exec()
        checa.stop()
        assert len(self.terminais()) >= quantos, f"sem sinal terminal: {self.sinais}"

    def girar(self, ms: int) -> None:
        """Roda o event loop por um tempo fixo (para provar que nada mais chega)."""
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()


@pytest.fixture
def client(qapp, fake_stego):
    return StegoClient(base_url=fake_stego.base_url)


# --- os quatro cenários gravados do Stego real --------------------------------


def test_resposta_completa(client, fake_stego):
    g = Gravador(client)
    client.ask("como funciona o escalonador do linux")
    g.esperar()
    g.girar(100)

    assert g.nomes() == ["hits", "token", "token", "token", "finished"]
    assert g.sinais[0][1][0]["citation"]
    assert g.texto() == "O escalonador usa CFS [1]."
    assert g.sinais[-1][1]["refused"] is False
    assert g.sinais[-1][1]["tokens_per_second"] == 20.0
    assert not client.is_busy


def test_indice_vazio_recusa_vem_como_token_e_done_refused(client, fake_stego):
    fake_stego.scenario = "fixture:ask_indice_vazio.sse"
    g = Gravador(client)
    client.ask("qualquer coisa")
    g.esperar()

    assert g.nomes() == ["hits", "token", "finished"]
    assert g.sinais[0][1] == []
    assert g.texto() == "Nao encontrei isso no seu acervo."
    assert g.sinais[-1][1]["refused"] is True


def test_erro_no_meio_da_geracao_preserva_tokens_e_falha(client, fake_stego):
    fake_stego.scenario = "fixture:ask_erro_no_meio.sse"
    g = Gravador(client)
    client.ask("escalonador")
    g.esperar()
    g.girar(100)

    assert g.nomes() == ["hits", "token", "failed"]
    assert g.texto() == "O escalonador "
    assert g.sinais[-1][1] == "geracao falhou: model crashed"


def test_ollama_fora_falha_antes_dos_hits(client, fake_stego):
    fake_stego.scenario = "fixture:ask_ollama_fora.sse"
    g = Gravador(client)
    client.ask("escalonador")
    g.esperar()

    assert g.nomes() == ["failed"]
    assert "embed falhou" in g.sinais[0][1]


# --- falhas fora do protocolo SSE ---------------------------------------------


def test_http_400_vira_failed_com_o_corpo(client, fake_stego):
    fake_stego.scenario = "http400"
    g = Gravador(client)
    client.ask("x")
    g.esperar()

    assert g.nomes() == ["failed"]
    assert "HTTP 400" in g.sinais[0][1]
    assert "pergunta vazia" in g.sinais[0][1]


def test_stego_desligado(qapp):
    with socket.socket() as s:  # porta livre e sem ninguém escutando
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]

    client = StegoClient(base_url=f"http://127.0.0.1:{porta}")
    g = Gravador(client)
    client.ask("x")
    g.esperar()

    assert g.nomes() == ["failed"]
    assert "não está rodando" in g.sinais[0][1]


def test_conexao_fecha_sem_done(client, fake_stego):
    fake_stego.scenario = "close_without_done"
    g = Gravador(client)
    client.ask("x")
    g.esperar()

    assert g.nomes() == ["hits", "token", "failed"]
    assert "fechou antes do fim" in g.sinais[-1][1]


def test_timeout_sem_bytes(qapp, fake_stego):
    fake_stego.scenario = "hang"
    client = StegoClient(base_url=fake_stego.base_url, transfer_timeout_ms=300)
    g = Gravador(client)
    client.ask("x")
    g.esperar()

    assert g.nomes() == ["hits", "failed"]
    assert "sem responder" in g.sinais[-1][1]


# --- cancelamento e reentrância -----------------------------------------------


def test_cancelar_no_meio(client, fake_stego):
    fake_stego.scenario = "hang"
    g = Gravador(client)
    client.ask("x")
    QTimer.singleShot(150, client.cancel)
    g.esperar()
    g.girar(200)

    assert g.nomes() == ["hits", "cancelled"]  # e nenhum failed depois
    assert not client.is_busy


def test_cancelar_sem_pergunta_nao_faz_nada(client):
    g = Gravador(client)
    client.cancel()
    assert g.sinais == []


def test_nova_pergunta_cancela_a_anterior(client, fake_stego):
    fake_stego.scenario = "hang"
    g = Gravador(client)
    client.ask("primeira")
    g.girar(150)
    fake_stego.scenario = "fixture:ask_ok.sse"
    client.ask("segunda")
    g.esperar(2)

    assert [n for n, _ in g.terminais()] == ["cancelled", "finished"]


def test_slot_pode_perguntar_de_novo_ao_terminar(client, fake_stego):
    """O cliente já está livre quando emite o sinal terminal."""
    g = Gravador(client)
    respondidas = []

    def ao_terminar(_):
        respondidas.append(1)
        if len(respondidas) == 1:
            client.ask("de novo")

    client.finished.connect(ao_terminar)
    client.ask("primeira")
    g.esperar(2)

    assert [n for n, _ in g.terminais()] == ["finished", "finished"]
    assert len(fake_stego.requests) == 2


# --- montagem da URL ----------------------------------------------------------


def test_pergunta_chega_intacta_no_servidor(client, fake_stego):
    """parse_qs do Stego lê '+' como espaço; o cliente precisa codificar."""
    pergunta = "C++ & SQL? 100% é #1 / a+b=c"
    g = Gravador(client)
    client.ask(pergunta, include_restricted=True)
    g.esperar()

    url = urlparse(fake_stego.requests[0])
    params = parse_qs(url.query)
    assert url.path == "/api/ask"
    assert params["q"] == [pergunta]
    assert params["restricted"] == ["1"]


def test_restrito_desligado_por_padrao(client, fake_stego):
    g = Gravador(client)
    client.ask("x")
    g.esperar()
    assert parse_qs(urlparse(fake_stego.requests[0]).query)["restricted"] == ["0"]


def test_pergunta_vazia_nem_sai_do_cliente(client, fake_stego):
    with pytest.raises(ValueError):
        client.ask("   ")
    assert fake_stego.requests == []


def test_ignora_proxy_do_sistema(qapp, fake_stego, monkeypatch):
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    client = StegoClient(base_url=fake_stego.base_url)
    g = Gravador(client)
    client.ask("x")
    g.esperar()
    assert g.nomes()[-1] == "finished"


def test_url_padrao_segue_stego_port(monkeypatch):
    import importlib

    import src.assistant.stego_client as mod

    monkeypatch.delenv("GREMLIN_STEGO_URL", raising=False)
    monkeypatch.setenv("STEGO_PORT", "9123")
    assert importlib.reload(mod).DEFAULT_BASE_URL == "http://127.0.0.1:9123"

    monkeypatch.setenv("GREMLIN_STEGO_URL", "http://127.0.0.1:7000")
    assert importlib.reload(mod).DEFAULT_BASE_URL == "http://127.0.0.1:7000"

    monkeypatch.delenv("GREMLIN_STEGO_URL")
    monkeypatch.delenv("STEGO_PORT")
    importlib.reload(mod)
