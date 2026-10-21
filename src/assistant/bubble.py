"""Geometria do balão de fala: onde ele fica e o desenho dele.

posicionar() é pura (só números) para poder ser testada sem tela. O
balão fica em cima da cabeça do Gremlin com a cauda apontando para
ela; se não couber em cima (Gremlin no topo da tela), vai para baixo
com a cauda para cima. Na horizontal ele não sai da tela, e a cauda
corre ao longo da borda para continuar apontando para o Gremlin.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath

RAIO = 20  # canto do corpo do balão
BORDA = 3.5  # espessura do contorno de "tinta"
CAUDA_ALTURA = 30
CAUDA_LARGURA = 42
MARGEM_TELA = 6  # o balão nunca encosta na borda da tela
# Quanto a ponta da cauda invade o retângulo do Gremlin: o sprite tem
# um respiro transparente em cima, então a ponta precisa descer um
# pouco para encostar nas orelhas.
SOBREPOSICAO = 18


@dataclass(frozen=True)
class Posicao:
    x: int
    y: int
    cauda_x: int  # x da ponta da cauda, relativo ao balão
    cauda_embaixo: bool  # True = balão acima do Gremlin


def posicionar(largura: int, altura: int, alvo: tuple[int, int, int, int],
               tela: tuple[int, int, int, int]) -> Posicao:
    """alvo e tela são (x, y, largura, altura) em coordenadas globais."""
    ax, ay, aw, ah = alvo
    tx, ty, tw, th = tela
    ponta_x = ax + aw // 2

    topo_tela = ty + MARGEM_TELA
    base_tela = ty + th - MARGEM_TELA
    y_acima = ay + SOBREPOSICAO - altura  # ponta da cauda encosta na cabeça
    y_abaixo = ay + ah - SOBREPOSICAO  # ponta da cauda encosta nos pés

    if y_acima >= topo_tela:
        y, cauda_embaixo = y_acima, True
    elif y_abaixo + altura <= base_tela:
        y, cauda_embaixo = y_abaixo, False
    elif (ay - topo_tela) >= (base_tela - (ay + ah)):
        # Não cabe em lugar nenhum (balão alto, tela baixa): fica do lado
        # com mais espaço, preso na borda. Cobre no máximo o topo da
        # cabeça, em vez de cair por cima do Gremlin inteiro.
        y, cauda_embaixo = topo_tela, True
    else:
        y, cauda_embaixo = base_tela - altura, False

    x = ponta_x - largura // 2
    x = max(tx + MARGEM_TELA, min(x, tx + tw - largura - MARGEM_TELA))

    # A cauda não pode sair do trecho reto da borda (fora dos cantos).
    # (+16: a base da cauda é deslocada para a esquerda da ponta)
    limite = RAIO + CAUDA_LARGURA // 2 + 16
    cauda_x = max(limite, min(ponta_x - x, largura - limite))
    return Posicao(x, y, cauda_x, cauda_embaixo)


def caminho_balao(largura: float, altura: float, cauda_x: float,
                  cauda_embaixo: bool) -> QPainterPath:
    """Contorno do balão: corpo arredondado + cauda, como uma peça só."""
    m = BORDA / 2 + 0.5  # o traço fica inteiro dentro da janela
    topo = m if cauda_embaixo else m + CAUDA_ALTURA
    corpo = QRectF(m, topo, largura - 2 * m, altura - 2 * m - CAUDA_ALTURA)

    caminho = QPainterPath()
    caminho.addRoundedRect(corpo, RAIO, RAIO)

    # Cauda de quadrinho: a base fica deslocada para a esquerda da ponta
    # e os dois lados são curvas que se cruzam na ponta, como um traço
    # de pincel. Um triângulo reto pareceria tooltip, não fala.
    desvio = 16
    base_esq = cauda_x - CAUDA_LARGURA / 2 - desvio
    base_dir = cauda_x + CAUDA_LARGURA / 2 - desvio
    if cauda_embaixo:
        base_y, ponta = corpo.bottom() - 3, QPointF(cauda_x, altura - m)
    else:
        base_y, ponta = corpo.top() + 3, QPointF(cauda_x, m)
    meio_y = base_y + (ponta.y() - base_y) * 0.6

    cauda = QPainterPath(QPointF(base_esq, base_y))
    cauda.quadTo(QPointF(base_esq + 4, meio_y), ponta)          # lado de fora, bojudo
    cauda.quadTo(QPointF(base_dir - 4, meio_y), QPointF(base_dir, base_y))  # lado de dentro
    cauda.closeSubpath()

    return caminho.united(cauda).simplified()
