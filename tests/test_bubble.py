"""Geometria do balão (src/assistant/bubble.py) e o balão ancorado no Gremlin."""

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QWidget

from src.assistant import bubble
from src.assistant.bubble import CAUDA_ALTURA, MARGEM_TELA, SOBREPOSICAO, posicionar

TELA = (0, 0, 1920, 1080)
GREMLIN = (800, 700, 300, 300)  # perto do rodapé, como no desktop real


def ponta_global(p, altura):
    """Onde a ponta da cauda cai na tela."""
    y = p.y + altura if p.cauda_embaixo else p.y
    return p.x + p.cauda_x, y


# --- posicionar ---------------------------------------------------------------------


def test_balao_fica_em_cima_com_a_ponta_na_cabeca():
    p = posicionar(440, 330, GREMLIN, TELA)
    assert p.cauda_embaixo
    assert ponta_global(p, 330) == (800 + 150, 700 + SOBREPOSICAO)


def test_balao_centralizado_no_gremlin():
    p = posicionar(440, 330, GREMLIN, TELA)
    assert p.x == 950 - 220


def test_sem_espaco_em_cima_vai_para_baixo_com_a_cauda_para_cima():
    p = posicionar(440, 330, (800, 40, 300, 300), TELA)
    assert not p.cauda_embaixo
    assert p.y == 40 + 300 - SOBREPOSICAO


def test_nao_cabe_em_lugar_nenhum_fica_no_lado_maior_sem_cobrir_o_gremlin():
    # O bug que a prévia mostrou: balão alto + tela baixa.
    tela = (0, 0, 760, 640)
    gremlin = (330, 340, 300, 300)
    p = posicionar(440, 410, gremlin, tela)
    assert p.cauda_embaixo  # em cima há mais espaço que embaixo
    assert p.y == MARGEM_TELA
    cobre = (p.y + 410) - 340  # quanto do Gremlin fica atrás do balão
    assert cobre < 300 / 3, f"cobriu {cobre}px do Gremlin"


@pytest.mark.parametrize("gx", [-120, 0, 1700, 1800])
def test_balao_nunca_sai_da_tela_e_cauda_segue_o_gremlin(gx):
    largura = 440
    p = posicionar(largura, 330, (gx, 700, 300, 300), TELA)
    assert MARGEM_TELA <= p.x <= 1920 - largura - MARGEM_TELA
    # a cauda fica no trecho reto da borda, do lado do Gremlin
    limite = bubble.RAIO + bubble.CAUDA_LARGURA // 2 + 16
    assert limite <= p.cauda_x <= largura - limite
    centro_gremlin = gx + 150
    if centro_gremlin < p.x + largura / 2:
        assert p.cauda_x < largura / 2
    else:
        assert p.cauda_x > largura / 2


def test_tela_com_origem_deslocada():
    # Segundo monitor à direita do primeiro.
    p = posicionar(440, 330, (2700, 700, 300, 300), (1920, 0, 1920, 1080))
    assert 1920 <= p.x <= 1920 + 1920 - 440
    assert ponta_global(p, 330)[0] == 2850


# --- desenho ------------------------------------------------------------------------


@pytest.mark.parametrize("embaixo", [True, False])
def test_desenho_tem_a_ponta_no_lugar_calculado(embaixo):
    caminho = bubble.caminho_balao(440, 330, 200, embaixo)
    perto_da_ponta = QPointF(200, 330 - 4) if embaixo else QPointF(200, 4)
    longe = QPointF(60, 330 - 4) if embaixo else QPointF(60, 4)
    assert caminho.contains(perto_da_ponta)
    assert not caminho.contains(longe)  # cauda, não uma faixa inteira


def test_desenho_cabe_na_janela():
    r = bubble.caminho_balao(440, 330, 200, True).boundingRect()
    assert r.left() >= 0 and r.top() >= 0
    assert r.right() <= 440 and r.bottom() <= 330


# --- balão ancorado num widget ------------------------------------------------------


@pytest.fixture
def balao_ancorado(qapp):
    from test_dialog import FakeClient

    from src.assistant.dialog import AskWindow

    alvo = QWidget()
    alvo.setGeometry(250, 300, 300, 300)
    alvo.show()
    w = AskWindow(client=FakeClient())
    w.ancorar_em(alvo)
    w.abrir()
    qapp.processEvents()
    yield w, alvo
    w.close()
    alvo.close()


def esperado(w, alvo):
    g = alvo.frameGeometry()
    t = w.screen().availableGeometry()
    largura, altura = w.tamanho_balao()
    return posicionar(largura, altura, (g.x(), g.y(), g.width(), g.height()),
                      (t.x(), t.y(), t.width(), t.height()))


def posicao_do_balao(w):
    from src.assistant.dialog import MARGEM

    return w.x() + MARGEM, w.y() + MARGEM  # a janela tem uma folga em volta


def test_abrir_posiciona_pela_geometria(balao_ancorado):
    w, alvo = balao_ancorado
    p = esperado(w, alvo)
    assert posicao_do_balao(w) == (p.x, p.y)
    assert (w.ctl.caudaX, w.ctl.caudaEmbaixo) == (p.cauda_x, p.cauda_embaixo)


def test_balao_segue_o_gremlin_quando_ele_anda(qapp, balao_ancorado):
    w, alvo = balao_ancorado
    alvo.move(alvo.x() + 120, alvo.y())
    qapp.processEvents()
    p = esperado(w, alvo)
    assert posicao_do_balao(w) == (p.x, p.y)


def test_abrir_as_fontes_mantem_a_ponta_no_lugar(qapp, balao_ancorado):
    from test_dialog import HITS

    w, alvo = balao_ancorado
    from test_dialog import girar

    w.ctl.acionar("x", False)
    w.client.hits_received.emit(HITS)
    girar(100)  # Column/Row do QML só recalculam o tamanho ao desenhar um quadro
    altura_antes = w.height()
    w.rootObject().setProperty("fontesAbertas", True)
    girar(100)
    assert w.height() > altura_antes  # cresceu
    p = esperado(w, alvo)
    assert posicao_do_balao(w) == (p.x, p.y)  # e foi reposicionado


def test_esconder_pelo_esc_nao_cancela(qapp, balao_ancorado):
    from test_dialog import girar

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    w, _ = balao_ancorado
    w.ctl.acionar("x", False)
    w.ctl._mudar_fase(w.ctl.fase.__class__.OCIOSO)  # já respondida
    QTest.keyClick(w, Qt.Key.Key_Escape)
    girar(400)
    assert not w.isVisible()
    assert w.client.cancelamentos == 0
