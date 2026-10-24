"""Lógica do balão de perguntas, sem tela.

O AskController fica entre o StegoClient (rede) e o Balao.qml (tela):
guarda a fase da pergunta, o status, as fontes e o texto da resposta, e
expõe tudo como propriedades e sinais Qt que o QML observa. Toda regra
mora aqui, então é aqui que os testes olham.

Tokens viram palavras: o LLM manda pedaços de palavra ("escal" +
"onador"), e o QML anima palavra por palavra. O controlador segura o
pedaço até chegar um espaço ou quebra de linha e só então emite a
palavra inteira (pedacoChegou).
"""

from __future__ import annotations

import re
from enum import Enum, auto

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication

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
# Parágrafo (linha em branco), quebra simples ou palavra.
_PEDACOS = re.compile(r"\n[ \t]*\n\s*|\n|\S+")


def _num(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


class AskController(QObject):
    fase_mudou = Signal(object)  # Fase, para o Python (gremlin.py)

    # --- para o QML ---
    estadoMudou = Signal()
    fontesMudaram = Signal()
    caudaMudou = Signal()
    respostaLimpa = Signal()
    pedacoChegou = Signal(str, str)  # (texto, "palavra" | "linha" | "paragrafo")
    terminou = Signal()  # resposta completa: o balão dá um pulinho
    pedidoAbrir = Signal()  # a janela apareceu: animação de entrada + foco
    fechamentoConcluido = Signal()  # a animação de saída acabou: pode esconder

    def __init__(self, client: StegoClient | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.client = client if client is not None else StegoClient(parent=self)
        self.fase = Fase.OCIOSO
        self._status = ""
        self._recusada = False
        self._fontes: list[dict] = []
        self._resposta = ""
        self._pendente = ""
        self._ultimo_pedaco = ""
        self._cauda_x = 220.0
        self._cauda_embaixo = True

        self.client.hits_received.connect(self._on_hits)
        self.client.token_received.connect(self._on_token)
        self.client.finished.connect(self._on_finished)
        self.client.failed.connect(self._on_failed)
        self.client.cancelled.connect(self._on_cancelled)

    # --- propriedades lidas pelo QML ------------------------------------------------

    def _fase_nome(self) -> str:
        return self.fase.name

    def _get_em_andamento(self) -> bool:
        return self.em_andamento

    def _get_status(self) -> str:
        return self._status

    def _get_status_erro(self) -> bool:
        return self.fase == Fase.ERRO

    def _get_recusada(self) -> bool:
        return self._recusada

    def _get_texto_botao(self) -> str:
        return "Cancelar" if self.em_andamento else "Perguntar"

    def _get_tem_resposta(self) -> bool:
        return bool(self._resposta.strip())

    def _get_fontes(self) -> list:
        return self._fontes

    def _get_cauda_x(self) -> float:
        return self._cauda_x

    def _get_cauda_embaixo(self) -> bool:
        return self._cauda_embaixo

    faseNome = Property(str, _fase_nome, notify=estadoMudou)
    emAndamento = Property(bool, _get_em_andamento, notify=estadoMudou)
    status = Property(str, _get_status, notify=estadoMudou)
    statusErro = Property(bool, _get_status_erro, notify=estadoMudou)
    recusada = Property(bool, _get_recusada, notify=estadoMudou)
    textoBotao = Property(str, _get_texto_botao, notify=estadoMudou)
    temResposta = Property(bool, _get_tem_resposta, notify=estadoMudou)
    fontes = Property("QVariantList", _get_fontes, notify=fontesMudaram)
    caudaX = Property(float, _get_cauda_x, notify=caudaMudou)
    caudaEmbaixo = Property(bool, _get_cauda_embaixo, notify=caudaMudou)

    # --- API Python ---------------------------------------------------------------------

    @property
    def em_andamento(self) -> bool:
        return self.fase in _EM_ANDAMENTO

    def texto_resposta(self) -> str:
        return self._resposta

    def definir_cauda(self, x: float, embaixo: bool) -> None:
        if (x, embaixo) != (self._cauda_x, self._cauda_embaixo):
            self._cauda_x, self._cauda_embaixo = float(x), embaixo
            self.caudaMudou.emit()

    # --- ações vindas do QML ------------------------------------------------------------

    @Slot(str, bool)
    def acionar(self, texto: str, restrito: bool) -> None:
        """Enter ou botão: pergunta, ou cancela se já há uma em andamento."""
        if self.em_andamento:
            self.client.cancel()
            return
        pergunta = texto.strip()
        if not pergunta:
            return
        self._resposta = ""
        self._pendente = ""
        self._ultimo_pedaco = ""
        self._recusada = False
        self._fontes = []
        self.fontesMudaram.emit()
        self.respostaLimpa.emit()
        self.client.ask(pergunta, include_restricted=restrito)
        self._mudar_fase(Fase.BUSCANDO)

    @Slot()
    def cancelar(self) -> None:
        if self.em_andamento:
            self.client.cancel()

    @Slot(int)
    def abrirFonte(self, indice: int) -> None:
        if 0 <= indice < len(self._fontes) and (caminho := self._fontes[indice]["caminho"]):
            QDesktopServices.openUrl(QUrl.fromLocalFile(caminho))

    @Slot()
    def copiarResposta(self) -> None:
        QGuiApplication.clipboard().setText(self._resposta.strip())

    @Slot()
    def concluirFechamento(self) -> None:
        self.fechamentoConcluido.emit()

    # --- sinais do cliente --------------------------------------------------------------

    def _on_hits(self, hits: list) -> None:
        # Mesma numeração que o Stego usa no prompt (build_prompt começa
        # em 1, na ordem dos hits): o [2] da resposta é a fonte [2].
        self._fontes = [
            {
                "numero": numero,
                "titulo": hit.get("citation") or "?",
                "caminho": hit.get("source_path") or "",
                "restrito": hit.get("sensitivity") == "restricted",
                "trecho": (hit.get("content") or "").strip()[:600],
            }
            for numero, hit in enumerate(hits, start=1)
        ]
        self.fontesMudaram.emit()
        if self.fase == Fase.BUSCANDO:
            # A busca acabou; agora o modelo lê as fontes (com o modelo frio,
            # isso pode levar dezenas de segundos). A interface web do Stego
            # também troca o aviso nesse ponto.
            n = len(self._fontes)
            self._status = f"Lendo {n} fonte{'s' if n != 1 else ''}…" if n else "Nenhuma fonte encontrada…"
            self.estadoMudou.emit()

    def _on_token(self, token: str) -> None:
        if self.fase == Fase.BUSCANDO:
            self._mudar_fase(Fase.RESPONDENDO)
        self._resposta += token
        self._alimentar(token)
        self.estadoMudou.emit()  # temResposta

    def _on_finished(self, done: dict) -> None:
        self._alimentar("", final=True)
        total_ms = sum((done.get("timings") or {}).values())
        tempo = f"{_num(total_ms / 1000)} s"
        tps = done.get("tokens_per_second")
        if done.get("refused"):
            self._recusada = True
            self._mudar_fase(Fase.RECUSADO, f"Não está no acervo ({tempo})")
        elif tps:
            self._mudar_fase(Fase.PRONTO, f"Pronto em {tempo}, {_num(tps)} tokens/s")
        else:
            self._mudar_fase(Fase.PRONTO, f"Pronto em {tempo}")
        self.terminou.emit()

    def _on_failed(self, mensagem: str) -> None:
        self._alimentar("", final=True)  # mostra o que chegou até a falha
        prefixo = "Resposta interrompida" if self._resposta.strip() else "Erro"
        self._mudar_fase(Fase.ERRO, f"{prefixo}: {mensagem}")

    def _on_cancelled(self) -> None:
        self._alimentar("", final=True)
        self._mudar_fase(Fase.OCIOSO, "Pergunta cancelada.")

    # --- tokens -> palavras ---------------------------------------------------------------

    def _alimentar(self, texto: str, final: bool = False) -> None:
        self._pendente += texto
        if final:
            completo, self._pendente = self._pendente, ""
        else:
            # Só o que vem antes do último espaço/quebra está completo;
            # o resto pode ser o começo de uma palavra que ainda chega.
            corte = max(self._pendente.rfind(c) for c in " \n\t")
            if corte < 0:
                return
            completo, self._pendente = self._pendente[: corte + 1], self._pendente[corte + 1 :]

        for m in _PEDACOS.finditer(completo):
            pedaco = m.group()
            if not pedaco.startswith("\n"):
                # Marcador de lista do Markdown no começo da linha vira "•".
                if pedaco in ("*", "-") and self._ultimo_pedaco in ("", "linha", "paragrafo"):
                    pedaco = "•"
                self._emitir(pedaco, "palavra")
            elif self._ultimo_pedaco:  # quebra antes da 1ª palavra não conta
                dupla = pedaco.count("\n") >= 2 or self._ultimo_pedaco == "linha"
                self._emitir("", "paragrafo" if dupla else "linha")

    def _emitir(self, texto: str, tipo: str) -> None:
        # Duas quebras seguidas (vindas em tokens separados) viram um
        # parágrafo só, em vez de duas linhas vazias.
        if tipo != "palavra" and self._ultimo_pedaco in ("linha", "paragrafo"):
            if tipo == "paragrafo" or self._ultimo_pedaco == "linha":
                self._ultimo_pedaco = "paragrafo"
                self.pedacoChegou.emit("", "paragrafo")
            return
        self._ultimo_pedaco = tipo
        self.pedacoChegou.emit(texto, tipo)

    # --- estado -------------------------------------------------------------------------

    def _mudar_fase(self, fase: Fase, status: str | None = None) -> None:
        self.fase = fase
        self._status = _STATUS.get(fase, "") if status is None else status
        self.estadoMudou.emit()
        self.fase_mudou.emit(fase)
