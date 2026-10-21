"""Balão de fala para perguntar ao Stego.

É uma janela Qt separada do Gremlin: o Gremlin é click-through (ignora
mouse e teclado de propósito), então não dá para digitar nele. Para
parecer a fala do personagem, a janela não tem moldura, desenha um
balão de quadrinho e, quando ancorada (ancorar_em), fica em cima da
cabeça do Gremlin e o acompanha se ele andar.

A janela não sabe nada de HTTP: fala só com o StegoClient (ou qualquer
objeto com os mesmos sinais, o que permite testar sem rede).

Fechar o balão NÃO cancela a pergunta: a resposta continua chegando e
fica lá quando ele for reaberto. Quem cancela é o botão ou o Esc.
"""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import QEvent, QObject, Qt, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QKeyEvent,
    QPainter,
    QPalette,
    QPen,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import bubble
from .stego_client import StegoClient


class Fase(Enum):
    """Em que pé está a pergunta. O Gremlin reage a isso (reactions.py)."""

    OCIOSO = auto()  # nada em andamento (início ou depois de cancelar)
    BUSCANDO = auto()  # pergunta enviada, esperando as fontes
    RESPONDENDO = auto()  # o texto da resposta está chegando
    PRONTO = auto()  # resposta completa
    RECUSADO = auto()  # completa, mas "não encontrei isso no seu acervo"
    ERRO = auto()  # falhou (Stego/Ollama fora, conexão caiu...)


_EM_ANDAMENTO = (Fase.BUSCANDO, Fase.RESPONDENDO)

_STATUS = {
    Fase.OCIOSO: "",
    Fase.BUSCANDO: "Buscando no acervo…",
    Fase.RESPONDENDO: "Respondendo…",
}

# --- Paleta, tirada do próprio personagem ----------------------------------------
PAPEL = "#FBFAFF"  # branco puxado para o lilás da boina
TINTA = "#2B2D52"  # azul-marinho do uniforme: contorno e texto
LACO = "#C8323C"  # laço vermelho: foco e erro, e só
BOINA = "#EEEDFA"  # lilás claro da boina: fundo do campo
SUSSURRO = "#6B6E8F"  # texto secundário

FONTES_ARREDONDADAS = ["Nunito", "Quicksand", "Noto Sans", "sans-serif"]
LARGURA = 440
ALTURA_RESPOSTA = 150

# Cores explícitas em tudo: o balão é sempre papel claro com tinta
# escura, seja qual for o tema do sistema (num tema escuro com texto
# vermelho, herdar a paleta daria vermelho sobre branco).
_ESTILO = f"""
#balao {{ background: transparent; }}
#balao QLabel, #balao QCheckBox {{ color: {TINTA}; }}
#balao QLabel#status {{ color: {SUSSURRO}; }}
#balao QLabel#status[erro="true"] {{ color: {LACO}; }}
#balao QLineEdit {{
    background: {BOINA}; color: {TINTA};
    border: 2px solid transparent; border-radius: 12px;
    padding: 6px 10px; selection-background-color: {TINTA};
}}
#balao QLineEdit:focus {{ border-color: {LACO}; }}
#balao QPushButton#enviar {{
    background: {TINTA}; color: {PAPEL};
    border: none; border-radius: 12px; padding: 6px 14px; font-weight: 600;
}}
#balao QPushButton#enviar:focus {{ outline: none; border: 2px solid {LACO}; }}
#balao QToolButton {{ background: transparent; border: none; color: {SUSSURRO}; }}
#balao QToolButton:hover, #balao QToolButton:focus {{ color: {TINTA}; }}
#balao QTextBrowser, #balao QListWidget {{
    background: transparent; color: {TINTA}; border: none;
    selection-background-color: {BOINA}; selection-color: {TINTA};
}}
#balao QListWidget::item {{ padding: 3px 0; color: {SUSSURRO}; }}
#balao QListWidget::item:hover {{ color: {TINTA}; }}
#balao QCheckBox::indicator {{
    width: 13px; height: 13px; border: 2px solid {SUSSURRO}; border-radius: 4px;
}}
#balao QCheckBox::indicator:checked {{ background: {LACO}; border-color: {LACO}; }}
#balao QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
#balao QScrollBar::handle:vertical {{ background: {BOINA}; border-radius: 4px; min-height: 24px; }}
#balao QScrollBar::add-line, #balao QScrollBar::sub-line {{ height: 0; }}
"""


def _num(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


class AskWindow(QWidget):
    fase_mudou = Signal(object)  # Fase

    def __init__(self, client: StegoClient | None = None, parent: QWidget | None = None):
        super().__init__(
            parent,
            Qt.WindowType.Tool  # sem botão na barra de tarefas
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setObjectName("balao")
        self.setWindowTitle("Perguntar ao Gremlin")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(LARGURA)
        self.setStyleSheet(_ESTILO)

        fonte = QFont()
        fonte.setFamilies(FONTES_ARREDONDADAS)
        fonte.setPointSize(10)
        self.setFont(fonte)

        self.client = client if client is not None else StegoClient(parent=self)
        self.fase = Fase.OCIOSO
        self._alvo: QWidget | None = None
        self._cauda_x = LARGURA // 2
        self._cauda_embaixo = True

        # --- widgets --------------------------------------------------------------
        self.campo = QLineEdit()
        self.campo.setPlaceholderText("Pergunte sobre o seu acervo")
        self._cor_do_placeholder(self.campo)

        self.botao = QPushButton("Perguntar")
        self.botao.setObjectName("enviar")
        self.botao.setCursor(Qt.CursorShape.PointingHandCursor)

        self.botao_fechar = QToolButton()
        self.botao_fechar.setText("✕")
        self.botao_fechar.setToolTip("Esconder (Esc)")
        self.botao_fechar.setCursor(Qt.CursorShape.PointingHandCursor)

        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.resposta = QTextBrowser()
        self.resposta.setFixedHeight(ALTURA_RESPOSTA)
        self.resposta.setPlaceholderText("A resposta aparece aqui, citando as fontes como [1], [2]…")
        self._cor_do_placeholder(self.resposta)
        self.resposta.viewport().setAutoFillBackground(False)

        self.botao_fontes = QToolButton()
        self.botao_fontes.setCheckable(True)
        self.botao_fontes.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_fontes.hide()

        self.fontes = QListWidget()
        self.fontes.setToolTip("Duplo clique abre o arquivo")
        self.fontes.setFixedHeight(120)
        self.fontes.viewport().setAutoFillBackground(False)
        self.fontes.hide()

        self.restrito = QCheckBox("Incluir restritos")
        self.restrito.setToolTip("Inclui documentos marcados como restritos no Stego")

        # --- layout ---------------------------------------------------------------
        topo = QHBoxLayout()
        topo.setSpacing(8)
        topo.addWidget(self.campo, 1)
        topo.addWidget(self.botao)
        topo.addWidget(self.botao_fechar)

        rodape = QHBoxLayout()
        rodape.addWidget(self.botao_fontes)
        rodape.addStretch(1)
        rodape.addWidget(self.restrito)

        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(6)
        self._layout.addLayout(topo)
        self._layout.addWidget(self.status)
        self._layout.addWidget(self.resposta)
        self._layout.addWidget(self.fontes)
        self._layout.addLayout(rodape)
        self._ajustar_margens()

        # --- conexões -------------------------------------------------------------
        self.campo.returnPressed.connect(self._on_botao)
        self.botao.clicked.connect(self._on_botao)
        self.botao_fechar.clicked.connect(self.hide)
        self.botao_fontes.toggled.connect(self._mostrar_fontes)
        self.fontes.itemDoubleClicked.connect(self._abrir_fonte)

        self.client.hits_received.connect(self._on_hits)
        self.client.token_received.connect(self._on_token)
        self.client.finished.connect(self._on_finished)
        self.client.failed.connect(self._on_failed)
        self.client.cancelled.connect(self._on_cancelled)

    # --- API pública ------------------------------------------------------------

    def ancorar_em(self, alvo: QWidget) -> None:
        """Passa a ficar em cima de `alvo` (o Gremlin) e segui-lo."""
        if self._alvo is not None:
            self._alvo.removeEventFilter(self)
        self._alvo = alvo
        alvo.installEventFilter(self)
        self._reposicionar()

    def abrir(self) -> None:
        """Mostra o balão e já deixa o cursor no campo de pergunta."""
        self.adjustSize()
        self._reposicionar()
        self.show()
        self.raise_()
        self.activateWindow()
        self.campo.setFocus()
        self.campo.selectAll()

    @property
    def em_andamento(self) -> bool:
        return self.fase in _EM_ANDAMENTO

    def texto_resposta(self) -> str:
        return self.resposta.toPlainText()

    # --- balão --------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(QPen(QColor(TINTA), bubble.BORDA))
        pintor.setBrush(QColor(PAPEL))
        pintor.drawPath(bubble.caminho_balao(
            self.width(), self.height(), self._cauda_x, self._cauda_embaixo))

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._alvo and event.type() in (QEvent.Type.Move, QEvent.Type.Resize):
            self._reposicionar()
        return False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reposicionar()  # fontes abertas/fechadas mudam a altura

    def _reposicionar(self) -> None:
        if self._alvo is None:
            return
        g = self._alvo.frameGeometry()
        tela = (self._alvo.screen() or self.screen()).availableGeometry()
        pos = bubble.posicionar(
            self.width(), self.height(),
            (g.x(), g.y(), g.width(), g.height()),
            (tela.x(), tela.y(), tela.width(), tela.height()),
        )
        mudou_cauda = pos.cauda_embaixo != self._cauda_embaixo
        self._cauda_x, self._cauda_embaixo = pos.cauda_x, pos.cauda_embaixo
        if mudou_cauda:
            self._ajustar_margens()
        self.move(pos.x, pos.y)
        self.update()

    def _ajustar_margens(self) -> None:
        # O espaço da cauda fica fora da área de conteúdo, do lado dela.
        cauda = bubble.CAUDA_ALTURA
        cima, baixo = (14, 14 + cauda) if self._cauda_embaixo else (14 + cauda, 14)
        self._layout.setContentsMargins(18, cima, 14, baixo)

    @staticmethod
    def _cor_do_placeholder(widget: QWidget) -> None:
        paleta = widget.palette()
        paleta.setColor(QPalette.ColorRole.PlaceholderText, QColor(SUSSURRO))
        paleta.setColor(QPalette.ColorRole.Text, QColor(TINTA))
        widget.setPalette(paleta)

    # --- ações do usuário -------------------------------------------------------

    def _on_botao(self) -> None:
        if self.em_andamento:
            self.client.cancel()
            return

        pergunta = self.campo.text().strip()
        if not pergunta:
            return

        self.resposta.clear()
        self.resposta.setFont(self.font())
        self.fontes.clear()
        self.botao_fontes.setChecked(False)
        self.botao_fontes.hide()
        self.client.ask(pergunta, include_restricted=self.restrito.isChecked())
        self._mudar_fase(Fase.BUSCANDO)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self.em_andamento:
                self.client.cancel()
            else:
                self.hide()
            return
        super().keyPressEvent(event)

    def _mostrar_fontes(self, visivel: bool) -> None:
        self.fontes.setVisible(visivel)
        self._texto_botao_fontes()
        self.adjustSize()  # o balão cresce para cima, a cauda fica no lugar

    def _texto_botao_fontes(self) -> None:
        seta = "▾" if self.botao_fontes.isChecked() else "▸"
        self.botao_fontes.setText(f"Fontes ({self.fontes.count()}) {seta}")

    def _abrir_fonte(self, item: QListWidgetItem) -> None:
        caminho = item.data(Qt.ItemDataRole.UserRole)
        if caminho:
            QDesktopServices.openUrl(QUrl.fromLocalFile(caminho))

    # --- sinais do cliente --------------------------------------------------------

    def _on_hits(self, hits: list) -> None:
        # Mesma numeração que o Stego usa no prompt (build_prompt começa
        # em 1, na ordem dos hits): o [2] da resposta é o item [2] daqui.
        for numero, hit in enumerate(hits, start=1):
            titulo = f"[{numero}] {hit.get('citation', '?')}"
            if hit.get("sensitivity") == "restricted":
                titulo += "  (restrito)"
            item = QListWidgetItem(titulo)
            item.setData(Qt.ItemDataRole.UserRole, hit.get("source_path"))
            trecho = (hit.get("content") or "").strip()
            item.setToolTip(f"{hit.get('source_path', '')}\n\n{trecho[:600]}")
            self.fontes.addItem(item)
        self.botao_fontes.setVisible(self.fontes.count() > 0)
        self._texto_botao_fontes()

    def _on_token(self, token: str) -> None:
        if self.fase == Fase.BUSCANDO:
            self._mudar_fase(Fase.RESPONDENDO)
        # Cursor próprio no fim do documento: inserir pelo cursor visível
        # escreveria no meio do texto se o usuário clicasse na resposta.
        cursor = QTextCursor(self.resposta.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(token)
        barra = self.resposta.verticalScrollBar()
        barra.setValue(barra.maximum())

    def _on_finished(self, done: dict) -> None:
        total_ms = sum((done.get("timings") or {}).values())
        tempo = f"{_num(total_ms / 1000)} s"
        tps = done.get("tokens_per_second")
        if done.get("refused"):
            fonte = self.resposta.font()
            fonte.setItalic(True)
            self.resposta.setFont(fonte)
            self._mudar_fase(Fase.RECUSADO, f"Não está no acervo ({tempo})")
        elif tps:
            self._mudar_fase(Fase.PRONTO, f"Pronto em {tempo}, {_num(tps)} tokens/s")
        else:
            self._mudar_fase(Fase.PRONTO, f"Pronto em {tempo}")

    def _on_failed(self, mensagem: str) -> None:
        prefixo = "Resposta interrompida" if self.texto_resposta() else "Erro"
        self._mudar_fase(Fase.ERRO, f"{prefixo}: {mensagem}")

    def _on_cancelled(self) -> None:
        self._mudar_fase(Fase.OCIOSO, "Pergunta cancelada.")

    # --- estado -----------------------------------------------------------------

    def _mudar_fase(self, fase: Fase, status: str | None = None) -> None:
        self.fase = fase
        self.botao.setText("Cancelar" if self.em_andamento else "Perguntar")
        self.campo.setReadOnly(self.em_andamento)
        self.status.setText(_STATUS.get(fase, "") if status is None else status)
        # Propriedade dinâmica + repolish: o estilo escolhe a cor do erro.
        self.status.setProperty("erro", fase == Fase.ERRO)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.fase_mudou.emit(fase)
