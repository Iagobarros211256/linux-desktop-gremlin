import json
from pathlib import Path

import pytest

from src.assistant.sse import SSEEvent, SSEParser

FIXTURES = Path(__file__).parent / "fixtures"


def parse_all(dados: bytes, tamanho_pedaco: int | None = None) -> list[SSEEvent]:
    parser = SSEParser()
    if tamanho_pedaco is None:
        return parser.feed(dados)
    eventos = []
    for i in range(0, len(dados), tamanho_pedaco):
        eventos.extend(parser.feed(dados[i : i + tamanho_pedaco]))
    return eventos


def test_evento_simples():
    assert parse_all(b'event: token\ndata: "oi"\n\n') == [SSEEvent("token", '"oi"')]


def test_evento_so_fecha_na_linha_vazia():
    parser = SSEParser()
    assert parser.feed(b'event: token\ndata: "oi"\n') == []
    assert parser.feed(b"\n") == [SSEEvent("token", '"oi"')]


def test_sem_event_vira_message():
    assert parse_all(b"data: x\n\n") == [SSEEvent("message", "x")]


def test_data_em_varias_linhas_junta_com_quebra():
    assert parse_all(b"data: a\ndata: b\n\n") == [SSEEvent("message", "a\nb")]


def test_comentario_e_bloco_sem_data_sao_ignorados():
    assert parse_all(b": keep-alive\n\nevent: x\n\ndata: y\n\n") == [
        SSEEvent("message", "y")
    ]


def test_tipo_nao_vaza_para_o_evento_seguinte():
    eventos = parse_all(b"event: hits\ndata: []\n\ndata: z\n\n")
    assert [e.type for e in eventos] == ["hits", "message"]


@pytest.mark.parametrize("fim", [b"\n", b"\r\n", b"\r"])
def test_aceita_os_tres_terminadores(fim):
    dados = b"event: done" + fim + b"data: {}" + fim + fim
    assert parse_all(dados) == [SSEEvent("done", "{}")]


def test_crlf_partido_entre_pedacos():
    parser = SSEParser()
    eventos = parser.feed(b"data: a\r")
    eventos += parser.feed(b"\n\r")
    eventos += parser.feed(b"\n")
    assert eventos == [SSEEvent("message", "a")]


def test_caractere_utf8_partido_entre_pedacos():
    dados = 'event: token\ndata: "árvore rubro-negra"\n\n'.encode()
    corte = dados.index("á".encode()) + 1  # no meio dos 2 bytes do "á"
    parser = SSEParser()
    eventos = parser.feed(dados[:corte]) + parser.feed(dados[corte:])
    assert json.loads(eventos[0].data) == "árvore rubro-negra"


@pytest.mark.parametrize("fixture", sorted(p.name for p in FIXTURES.glob("*.sse")))
def test_gravacoes_reais_dao_o_mesmo_resultado_em_qualquer_fatiamento(fixture):
    """A rede pode fatiar a resposta em qualquer ponto; o resultado não muda."""
    dados = (FIXTURES / fixture).read_bytes()
    inteiro = parse_all(dados)
    assert inteiro, "fixture sem eventos"
    for tamanho in (1, 2, 3, 7, 64):
        assert parse_all(dados, tamanho) == inteiro


def test_gravacao_ok_tem_a_sequencia_do_contrato():
    eventos = parse_all((FIXTURES / "ask_ok.sse").read_bytes())
    assert [e.type for e in eventos] == ["hits", "token", "token", "token", "done"]

    hits = json.loads(eventos[0].data)
    assert {"chunk_id", "content", "citation", "source_path", "sensitivity"} <= hits[0].keys()
    assert "".join(json.loads(e.data) for e in eventos[1:4]) == "O escalonador usa CFS [1]."
    assert json.loads(eventos[-1].data)["refused"] is False


def test_gravacao_erro_no_meio_nao_tem_done():
    tipos = [e.type for e in parse_all((FIXTURES / "ask_erro_no_meio.sse").read_bytes())]
    assert tipos == ["hits", "token", "error"]
