"""Balão de fala para perguntar ao Stego (Qt Quick).

A tela é o qml/Balao.qml; a lógica é o AskController (controller.py).
Esta classe só junta os dois numa janela sem moldura, transparente e
por cima de tudo, e a mantém em cima da cabeça do Gremlin.

API mantida da versão em QWidget (usada pelo gremlin.py e pelos testes):
fase_mudou, ancorar_em, abrir, client, fase, em_andamento,
texto_resposta, hide/close/isVisible e _mudar_fase.

Fechar o balão NÃO cancela a pergunta: a resposta continua chegando e
fica lá quando ele for reaberto. Quem cancela é o botão ou o Esc.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QSurfaceFormat
from PySide6.QtQuick import QQuickView
from PySide6.QtWidgets import QWidget

from . import bubble
from .controller import AskController, Fase
from .stego_client import StegoClient

__all__ = ["AskWindow", "Fase"]

QML = Path(__file__).resolve().parent / "qml" / "Balao.qml"
MARGEM = 16  # igual a `margem` no Balao.qml: folga para a mola passar de 100%


class AskWindow(QQuickView):
    fase_mudou = Signal(object)  # Fase

    def __init__(self, client: StegoClient | None = None):
        super().__init__()
        self.ctl = AskController(client, parent=self)
        self.client = self.ctl.client
        self.ctl.fase_mudou.connect(self.fase_mudou)
        self.ctl.fechamentoConcluido.connect(self.hide)
        self._alvo: QWidget | None = None
        # O SizeViewToRootObject redimensiona a janela no ciclo seguinte e,
        # nesse caminho, um resizeEvent sobrescrito em Python não é chamado.
        # Os sinais de tamanho da QWindow disparam sempre.
        self.widthChanged.connect(self._reposicionar)
        self.heightChanged.connect(self._reposicionar)

        formato = QSurfaceFormat(self.format())
        formato.setAlphaBufferSize(8)  # sem isso, o transparente vira preto
        self.setFormat(formato)
        self.setColor(QColor(0, 0, 0, 0))
        self.setFlags(
            Qt.WindowType.Tool  # sem botão na barra de tarefas
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setTitle("Perguntar ao Gremlin")
        self.setResizeMode(QQuickView.ResizeMode.SizeViewToRootObject)
        self.rootContext().setContextProperty("ctl", self.ctl)
        self.setSource(QUrl.fromLocalFile(str(QML)))
        if self.status() == QQuickView.Status.Error:
            erros = "\n".join(e.toString() for e in self.errors())
            raise RuntimeError(f"Balao.qml não carregou:\n{erros}")

        # O SizeViewToRootObject segue a raiz com um ciclo de atraso (a
        # janela fica um tamanho atrás e o balão desalinha por um quadro).
        # Acompanhar a raiz direto deixa janela e posição sempre juntas.
        raiz = self.rootObject()
        raiz.widthChanged.connect(self._seguir_raiz)
        raiz.heightChanged.connect(self._seguir_raiz)
        self._seguir_raiz()

    # --- API mantida ----------------------------------------------------------------------

    @property
    def fase(self) -> Fase:
        return self.ctl.fase

    @property
    def em_andamento(self) -> bool:
        return self.ctl.em_andamento

    def texto_resposta(self) -> str:
        return self.ctl.texto_resposta()

    def _mudar_fase(self, fase: Fase, status: str | None = None) -> None:
        self.ctl._mudar_fase(fase, status)

    def ancorar_em(self, alvo: QWidget) -> None:
        """Passa a ficar em cima de `alvo` (o Gremlin) e segui-lo."""
        if self._alvo is not None:
            self._alvo.removeEventFilter(self)
        self._alvo = alvo
        alvo.installEventFilter(self)
        self._reposicionar()

    def abrir(self) -> None:
        """Mostra o balão (com a animação de entrada) e foca o campo."""
        self._reposicionar()
        self.show()
        self.raise_()
        self.requestActivate()
        self.ctl.pedidoAbrir.emit()

    # --- posição --------------------------------------------------------------------------

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._alvo and event.type() in (QEvent.Type.Move, QEvent.Type.Resize):
            self._reposicionar()
        return False

    def _seguir_raiz(self) -> None:
        raiz = self.rootObject()
        self.resize(round(raiz.width()), round(raiz.height()))

    def tamanho_balao(self) -> tuple[int, int]:
        """Tamanho do balão desenhado, sem a margem transparente."""
        return self.width() - 2 * MARGEM, self.height() - 2 * MARGEM

    def _reposicionar(self) -> None:
        if self._alvo is None:
            return
        g = self._alvo.frameGeometry()
        tela = (self._alvo.screen() or self.screen()).availableGeometry()
        largura, altura = self.tamanho_balao()
        pos = bubble.posicionar(
            largura, altura,
            (g.x(), g.y(), g.width(), g.height()),
            (tela.x(), tela.y(), tela.width(), tela.height()),
        )
        self.ctl.definir_cauda(pos.cauda_x, pos.cauda_embaixo)
        self.setPosition(pos.x - MARGEM, pos.y - MARGEM)
