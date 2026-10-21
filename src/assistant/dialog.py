"""Janela de perguntas ao Stego.

É uma janela Qt comum, separada do Gremlin: o Gremlin é click-through
(ignora mouse e teclado de propósito), então não dá para digitar nele.

A janela não sabe nada de HTTP: fala só com o StegoClient (ou qualquer
objeto com os mesmos sinais, o que permite testar sem rede).

Fechar a janela NÃO cancela a pergunta: a resposta continua chegando e
fica lá quando a janela for reaberta. Quem cancela é o botão ou o Esc.
"""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QKeyEvent, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .stego_client import StegoClient


class Fase(Enum):
    """Em que pé está a pergunta. A próxima etapa liga isso às animações."""

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


class AskWindow(QWidget):
    fase_mudou = Signal(object)  # Fase

    def __init__(self, client: StegoClient | None = None, parent: QWidget | None = None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Perguntar ao Gremlin")
        self.resize(560, 540)

        self.client = client if client is not None else StegoClient(parent=self)
        self.fase = Fase.OCIOSO

        # --- widgets --------------------------------------------------------------
        self.campo = QLineEdit()
        self.campo.setPlaceholderText("Pergunte algo sobre o seu acervo…")
        self.campo.setClearButtonEnabled(True)

        self.botao = QPushButton("Perguntar")
        self.botao.setDefault(True)

        self.restrito = QCheckBox("Incluir documentos restritos")

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.resposta = QTextBrowser()
        self.resposta.setPlaceholderText("A resposta aparece aqui, com as fontes citadas como [1], [2]…")

        self.fontes = QListWidget()
        self.fontes.setToolTip("Duplo clique abre o arquivo")
        self.fontes.setMaximumHeight(150)

        # --- layout ---------------------------------------------------------------
        linha = QHBoxLayout()
        linha.addWidget(self.campo, 1)
        linha.addWidget(self.botao)

        layout = QVBoxLayout(self)
        layout.addLayout(linha)
        layout.addWidget(self.restrito)
        layout.addWidget(self.status)
        layout.addWidget(self.resposta, 1)
        layout.addWidget(QLabel("Fontes"))
        layout.addWidget(self.fontes)

        # --- conexões -------------------------------------------------------------
        self.campo.returnPressed.connect(self._on_botao)
        self.botao.clicked.connect(self._on_botao)
        self.fontes.itemDoubleClicked.connect(self._abrir_fonte)

        self.client.hits_received.connect(self._on_hits)
        self.client.token_received.connect(self._on_token)
        self.client.finished.connect(self._on_finished)
        self.client.failed.connect(self._on_failed)
        self.client.cancelled.connect(self._on_cancelled)

    # --- API pública ------------------------------------------------------------

    def abrir(self) -> None:
        """Mostra a janela e já deixa o cursor no campo de pergunta."""
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

    # --- ações do usuário -------------------------------------------------------

    def _on_botao(self) -> None:
        if self.em_andamento:
            self.client.cancel()
            return

        pergunta = self.campo.text().strip()
        if not pergunta:
            return

        self.resposta.clear()
        self.resposta.setFont(QFont())
        self.fontes.clear()
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
                titulo += "  · restrito"
            item = QListWidgetItem(titulo)
            item.setData(Qt.ItemDataRole.UserRole, hit.get("source_path"))
            trecho = (hit.get("content") or "").strip()
            item.setToolTip(f"{hit.get('source_path', '')}\n\n{trecho[:600]}")
            self.fontes.addItem(item)

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
        medidas = [f"{total_ms / 1000:.1f} s"]
        if tps := done.get("tokens_per_second"):
            medidas.append(f"{tps} tok/s")

        if done.get("refused"):
            fonte = QFont()
            fonte.setItalic(True)
            self.resposta.setFont(fonte)
            self._mudar_fase(Fase.RECUSADO, "Não está no acervo  ·  " + "  ·  ".join(medidas))
        else:
            self._mudar_fase(Fase.PRONTO, "Pronto em " + "  ·  ".join(medidas))

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
        self.status.setStyleSheet("color: #c0392b;" if fase == Fase.ERRO else "")
        self.fase_mudou.emit(fase)
