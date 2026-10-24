"""Balão de perguntas: a lógica (AskController) e a janela QML (AskWindow)."""

import pytest
from PySide6.QtCore import QEventLoop, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from src.assistant.controller import AskController, Fase
from src.assistant.dialog import AskWindow
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

DONE = {"timings": {"embed": 100, "geracao": 1400}, "tokens_per_second": 12.5, "refused": False}


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


def girar(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture
def ctl(qapp):
    c = AskController(client=FakeClient())
    c.fases = []
    c.pedacos = []
    c.fase_mudou.connect(c.fases.append)
    c.pedacoChegou.connect(lambda t, k: c.pedacos.append(t if k == "palavra" else f"<{k}>"))
    return c


def responder(c, tokens=("O CFS ", "usa árvore ", "[1]."), done=DONE):
    c.client.hits_received.emit(HITS)
    for t in tokens:
        c.client.token_received.emit(t)
    c.client.finished.emit(done)


# === lógica (AskController) ===========================================================

# --- enviar ---------------------------------------------------------------------------


def test_acionar_envia_a_pergunta(ctl):
    ctl.acionar("  como funciona o escalonador?  ", False)
    assert ctl.client.perguntas == [("como funciona o escalonador?", False)]
    assert ctl.fase == Fase.BUSCANDO
    assert ctl.emAndamento and ctl.textoBotao == "Cancelar"
    assert ctl.status == "Buscando no acervo…"


def test_pergunta_vazia_nao_envia(ctl):
    ctl.acionar("   ", False)
    assert ctl.client.perguntas == []
    assert ctl.fases == []


def test_restrito_vai_na_pergunta(ctl):
    ctl.acionar("diário", True)
    assert ctl.client.perguntas == [("diário", True)]


def test_acionar_durante_a_pergunta_cancela(ctl):
    ctl.acionar("x", False)
    ctl.acionar("x", False)  # o mesmo botão vira "Cancelar"
    assert ctl.client.cancelamentos == 1
    assert len(ctl.client.perguntas) == 1
    assert ctl.fase == Fase.OCIOSO
    assert ctl.status == "Pergunta cancelada."


# --- receber --------------------------------------------------------------------------


def test_resposta_completa(ctl):
    terminou = []
    ctl.terminou.connect(lambda: terminou.append(1))
    ctl.acionar("escalonador", False)
    responder(ctl)

    assert ctl.texto_resposta() == "O CFS usa árvore [1]."
    assert ctl.fases == [Fase.BUSCANDO, Fase.RESPONDENDO, Fase.PRONTO]
    assert ctl.status == "Pronto em 1,5 s, 12,5 tokens/s"  # vírgula: é português
    assert ctl.textoBotao == "Perguntar" and ctl.temResposta
    assert terminou == [1]  # o balão dá o pulinho


def test_fontes_numeradas_como_no_prompt_do_stego(ctl):
    ctl.acionar("x", False)
    ctl.client.hits_received.emit(HITS)
    assert [(f["numero"], f["titulo"], f["restrito"]) for f in ctl.fontes] == [
        (1, "Escalonador do Linux", False),
        (2, "Diário", True),
    ]
    assert ctl.fontes[0]["caminho"] == "/home/iago/notas/linux.md"


def test_status_muda_quando_as_fontes_chegam(ctl):
    ctl.acionar("x", False)
    ctl.client.hits_received.emit(HITS)
    assert ctl.fase == Fase.BUSCANDO  # o Gremlin continua pensando
    assert ctl.status == "Lendo 2 fontes…"


def test_status_sem_fontes(ctl):
    ctl.acionar("x", False)
    ctl.client.hits_received.emit([])
    assert ctl.status == "Nenhuma fonte encontrada…"


def test_recusa(ctl):
    ctl.acionar("receita de lasanha", False)
    responder(ctl, tokens=("Nao encontrei isso no seu acervo.",), done=dict(DONE, refused=True))
    assert ctl.fase == Fase.RECUSADO
    assert ctl.recusada
    assert ctl.status == "Não está no acervo (1,5 s)"


def test_nova_pergunta_limpa_a_anterior(ctl):
    limpezas = []
    ctl.respostaLimpa.connect(lambda: limpezas.append(1))
    ctl.acionar("primeira", False)
    responder(ctl, done=dict(DONE, refused=True))
    ctl.acionar("segunda", False)

    assert limpezas == [1, 1]
    assert ctl.texto_resposta() == ""
    assert ctl.fontes == []
    assert not ctl.recusada


# --- tokens viram palavras -------------------------------------------------------------


def test_token_partido_no_meio_da_palavra_vira_uma_palavra(ctl):
    ctl.acionar("x", False)
    for t in ["O escal", "onador do ", "Linux"]:
        ctl.client.token_received.emit(t)
    assert ctl.pedacos == ["O", "escalonador", "do"]  # "Linux" ainda pode continuar
    ctl.client.finished.emit(DONE)
    assert ctl.pedacos == ["O", "escalonador", "do", "Linux"]


def test_quebras_de_linha_e_paragrafo(ctl):
    ctl.acionar("x", False)
    for t in ["\n\nIntro.\n", "\n- um\n* dois\n", "fim [1", "]."]:
        ctl.client.token_received.emit(t)
    ctl.client.finished.emit(DONE)
    assert ctl.pedacos == [
        "Intro.", "<linha>", "<paragrafo>",  # "\n" + "\n" em tokens separados
        "•", "um", "<linha>", "•", "dois", "<linha>",
        "fim", "[1].",
    ]


def test_quebras_repetidas_nao_empilham(ctl):
    ctl.acionar("x", False)
    ctl.client.token_received.emit("a\n\n\n\n\nb ")
    assert ctl.pedacos == ["a", "<paragrafo>", "b"]


def test_marcador_no_meio_da_frase_nao_vira_bolinha(ctl):
    ctl.acionar("x", False)
    ctl.client.token_received.emit("3 - 1 = 2 ")
    assert ctl.pedacos == ["3", "-", "1", "=", "2"]


# --- falhas e cancelamento ------------------------------------------------------------


def test_erro_sem_texto(ctl):
    ctl.acionar("x", False)
    ctl.client.failed.emit("o Stego não está rodando")
    assert ctl.fase == Fase.ERRO and ctl.statusErro
    assert ctl.status == "Erro: o Stego não está rodando"


def test_erro_no_meio_mostra_o_que_chegou(ctl):
    ctl.acionar("x", False)
    ctl.client.token_received.emit("O CFS us")
    ctl.client.failed.emit("geracao falhou")
    assert ctl.pedacos == ["O", "CFS", "us"]  # a palavra pela metade aparece
    assert ctl.status == "Resposta interrompida: geracao falhou"


def test_cancelar_sem_pergunta_nao_faz_nada(ctl):
    ctl.cancelar()
    assert ctl.client.cancelamentos == 0


# --- ações ------------------------------------------------------------------------------


def test_abrir_fonte(ctl, monkeypatch):
    from PySide6.QtGui import QDesktopServices

    abertos = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: abertos.append(url.toLocalFile()))
    ctl.acionar("x", False)
    ctl.client.hits_received.emit(HITS)
    ctl.abrirFonte(1)
    ctl.abrirFonte(9)  # fora da lista: ignora
    assert abertos == ["/home/iago/privado/diario.md"]


def test_copiar_resposta(ctl):
    ctl.acionar("x", False)
    responder(ctl)
    ctl.copiarResposta()
    assert QGuiApplication.clipboard().text() == "O CFS usa árvore [1]."


def test_cauda_so_avisa_quando_muda(ctl):
    avisos = []
    ctl.caudaMudou.connect(lambda: avisos.append(1))
    ctl.definir_cauda(100, True)
    ctl.definir_cauda(100, True)
    ctl.definir_cauda(100, False)
    assert avisos == [1, 1]


# === janela QML (AskWindow) ============================================================


@pytest.fixture
def janela(qapp):
    w = AskWindow(client=FakeClient())
    fases = []
    w.fase_mudou.connect(fases.append)
    w.fases = fases
    yield w
    w.close()
    w.deleteLater()


def digitar(w, texto):
    """QTest.keyClicks do PySide só aceita QWidget; o balão é uma QWindow."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    for letra in texto:
        for tipo in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QGuiApplication.sendEvent(w, QKeyEvent(tipo, 0, Qt.KeyboardModifier.NoModifier, letra))


def campo(w):
    return w.rootObject().findChild(QObject, "campo")


def test_qml_carrega_sem_erros(janela):
    assert janela.errors() == []
    largura, _ = janela.tamanho_balao()
    assert largura == 440


def test_abrir_mostra_e_foca_o_campo(janela):
    janela.abrir()
    girar(50)
    assert janela.isVisible()
    assert campo(janela).property("activeFocus")


def test_digitar_e_enter_pergunta(janela):
    janela.abrir()
    girar(50)
    digitar(janela, "o que é CFS?")
    QTest.keyClick(janela, Qt.Key.Key_Return)
    assert janela.client.perguntas == [("o que é CFS?", False)]
    assert janela.fases == [Fase.BUSCANDO]
    assert campo(janela).property("readOnly")  # não edita durante a pergunta


def test_esc_cancela_se_ocupado_e_esconde_se_livre(janela):
    janela.abrir()
    girar(50)
    digitar(janela, "x")
    QTest.keyClick(janela, Qt.Key.Key_Return)
    QTest.keyClick(janela, Qt.Key.Key_Escape)
    assert janela.client.cancelamentos == 1
    assert janela.isVisible()

    QTest.keyClick(janela, Qt.Key.Key_Escape)
    girar(400)  # animação de saída
    assert not janela.isVisible()


def test_fechar_a_janela_nao_cancela(janela):
    janela.abrir()
    janela.ctl.acionar("x", False)
    janela.close()
    assert janela.client.cancelamentos == 0
    assert janela.em_andamento

    janela.client.token_received.emit("chegou com a janela fechada ")
    janela.abrir()
    assert janela.texto_resposta() == "chegou com a janela fechada "


def test_com_stego_client_real(qapp, fake_stego):
    w = AskWindow(client=StegoClient(base_url=fake_stego.base_url))
    fases = []
    w.fase_mudou.connect(fases.append)

    w.ctl.acionar("como funciona o escalonador do linux", False)
    loop = QEventLoop()
    w.fase_mudou.connect(lambda f: loop.quit() if f not in (Fase.BUSCANDO, Fase.RESPONDENDO) else None)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    assert fases == [Fase.BUSCANDO, Fase.RESPONDENDO, Fase.PRONTO]
    assert w.texto_resposta() == "O escalonador usa CFS [1]."
    assert len(w.ctl.fontes) == 2
    w.close()
    w.deleteLater()
