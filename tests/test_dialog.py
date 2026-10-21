import pytest
from PySide6.QtCore import QEventLoop, QObject, Qt, QTimer, Signal
from PySide6.QtTest import QTest

from src.assistant.dialog import AskWindow, Fase
from src.assistant.stego_client import StegoClient

HITS = [
    {
        "citation": "Escalonador do Linux",
        "source_path": "/home/iago/notas/linux.md",
        "content": "O CFS usa uma árvore rubro-negra.",
        "sensitivity": "normal",
    },
    {
        "citation": "Diário",
        "source_path": "/home/iago/privado/diario.md",
        "content": "texto restrito",
        "sensitivity": "restricted",
    },
]


class FakeClient(QObject):
    """Mesmos sinais do StegoClient; registra as chamadas em vez de usar rede."""

    hits_received = Signal(list)
    token_received = Signal(str)
    finished = Signal(dict)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self.perguntas: list[tuple[str, bool]] = []
        self.cancelamentos = 0

    def ask(self, question, include_restricted=False):
        self.perguntas.append((question, include_restricted))

    def cancel(self):
        self.cancelamentos += 1
        self.cancelled.emit()


@pytest.fixture
def janela(qapp):
    client = FakeClient()
    w = AskWindow(client=client)
    fases = []
    w.fase_mudou.connect(fases.append)
    w.fases = fases
    yield w
    w.close()
    w.deleteLater()


def perguntar(w: AskWindow, texto: str) -> None:
    w.campo.setText(texto)
    QTest.keyClick(w.campo, Qt.Key.Key_Return)


def responder(w: AskWindow, tokens=("O CFS ", "usa árvore ", "[1]."), refused=False):
    w.client.hits_received.emit(HITS)
    for t in tokens:
        w.client.token_received.emit(t)
    w.client.finished.emit(
        {"timings": {"embed": 100, "geracao": 1400}, "tokens_per_second": 12.5, "refused": refused}
    )


# --- enviar ---------------------------------------------------------------------


def test_enter_envia_a_pergunta(janela):
    perguntar(janela, "  como funciona o escalonador?  ")
    assert janela.client.perguntas == [("como funciona o escalonador?", False)]
    assert janela.fase == Fase.BUSCANDO
    assert janela.botao.text() == "Cancelar"
    assert janela.campo.isReadOnly()


def test_pergunta_vazia_nao_envia(janela):
    perguntar(janela, "   ")
    assert janela.client.perguntas == []
    assert janela.fases == []


def test_restrito_marcado_vai_na_pergunta(janela):
    janela.restrito.setChecked(True)
    perguntar(janela, "diário")
    assert janela.client.perguntas == [("diário", True)]


def test_restrito_comeca_desmarcado(janela):
    assert not janela.restrito.isChecked()


# --- receber --------------------------------------------------------------------


def test_resposta_completa(janela):
    perguntar(janela, "escalonador")
    responder(janela)

    assert janela.texto_resposta() == "O CFS usa árvore [1]."
    assert janela.fases == [Fase.BUSCANDO, Fase.RESPONDENDO, Fase.PRONTO]
    assert janela.botao.text() == "Perguntar"
    assert not janela.campo.isReadOnly()
    assert "1.5 s" in janela.status.text()
    assert "12.5 tok/s" in janela.status.text()


def test_fontes_numeradas_como_no_prompt_do_stego(janela):
    perguntar(janela, "escalonador")
    janela.client.hits_received.emit(HITS)

    itens = [janela.fontes.item(i) for i in range(janela.fontes.count())]
    assert [i.text() for i in itens] == [
        "[1] Escalonador do Linux",
        "[2] Diário  · restrito",
    ]
    assert itens[0].data(Qt.ItemDataRole.UserRole) == "/home/iago/notas/linux.md"
    assert "árvore rubro-negra" in itens[0].toolTip()


def test_token_vai_para_o_fim_mesmo_com_cursor_no_meio(janela):
    perguntar(janela, "x")
    janela.client.token_received.emit("começo ")
    cursor = janela.resposta.textCursor()
    cursor.setPosition(2)  # usuário clicou no meio do texto
    janela.resposta.setTextCursor(cursor)
    janela.client.token_received.emit("fim")
    assert janela.texto_resposta() == "começo fim"


def test_recusa(janela):
    perguntar(janela, "receita de lasanha")
    responder(janela, tokens=("Nao encontrei isso no seu acervo.",), refused=True)

    assert janela.fase == Fase.RECUSADO
    assert "Não está no acervo" in janela.status.text()
    assert janela.resposta.font().italic()


def test_nova_pergunta_limpa_a_anterior(janela):
    perguntar(janela, "primeira")
    responder(janela, refused=True)
    perguntar(janela, "segunda")

    assert janela.texto_resposta() == ""
    assert janela.fontes.count() == 0
    assert not janela.resposta.font().italic()


# --- falhas e cancelamento ------------------------------------------------------


def test_erro_sem_texto(janela):
    perguntar(janela, "x")
    janela.client.failed.emit("o Stego não está rodando em http://127.0.0.1:8080")

    assert janela.fase == Fase.ERRO
    assert janela.status.text().startswith("Erro: o Stego não está rodando")
    assert janela.botao.text() == "Perguntar"


def test_erro_no_meio_mantem_o_texto_parcial(janela):
    perguntar(janela, "x")
    janela.client.hits_received.emit(HITS)
    janela.client.token_received.emit("O CFS ")
    janela.client.failed.emit("geracao falhou: model crashed")

    assert janela.texto_resposta() == "O CFS "
    assert janela.status.text() == "Resposta interrompida: geracao falhou: model crashed"


def test_botao_cancela_durante_a_pergunta(janela):
    perguntar(janela, "x")
    janela.botao.click()

    assert janela.client.cancelamentos == 1
    assert janela.fase == Fase.OCIOSO
    assert janela.botao.text() == "Perguntar"
    assert len(janela.client.perguntas) == 1  # clicar não reenviou


def test_esc_cancela_se_ocupado_e_esconde_se_livre(janela):
    # A tecla vai para o campo (onde o foco fica de verdade) e precisa
    # subir até a janela: o QLineEdit não pode engolir o Esc.
    janela.show()
    perguntar(janela, "x")
    QTest.keyClick(janela.campo, Qt.Key.Key_Escape)
    assert janela.client.cancelamentos == 1
    assert janela.isVisible()

    QTest.keyClick(janela.campo, Qt.Key.Key_Escape)
    assert not janela.isVisible()


def test_fechar_a_janela_nao_cancela(janela):
    janela.show()
    perguntar(janela, "x")
    janela.close()
    assert janela.client.cancelamentos == 0
    assert janela.em_andamento

    janela.client.token_received.emit("chegou com a janela fechada")
    janela.abrir()
    assert janela.texto_resposta() == "chegou com a janela fechada"


# --- de ponta a ponta com o cliente real -------------------------------------------


def test_com_stego_client_real(qapp, fake_stego):
    w = AskWindow(client=StegoClient(base_url=fake_stego.base_url))
    fases = []
    w.fase_mudou.connect(fases.append)

    perguntar(w, "como funciona o escalonador do linux")
    loop = QEventLoop()
    w.fase_mudou.connect(lambda f: loop.quit() if f not in (Fase.BUSCANDO, Fase.RESPONDENDO) else None)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    assert fases == [Fase.BUSCANDO, Fase.RESPONDENDO, Fase.PRONTO]
    assert w.texto_resposta() == "O escalonador usa CFS [1]."
    assert w.fontes.count() == 2
    w.deleteLater()
