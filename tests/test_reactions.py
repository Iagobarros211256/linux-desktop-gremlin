from types import SimpleNamespace

from src.assistant.dialog import Fase
from src.assistant.reactions import FALLBACK, REACOES, resolver_animacao


def test_toda_fase_tem_reacao():
    assert set(REACOES) == set(Fase)


def test_buscando_e_respondendo_sao_a_mesma_reacao():
    # Se fossem diferentes, a animação reiniciaria no primeiro token.
    assert REACOES[Fase.BUSCANDO] == REACOES[Fase.RESPONDENDO]


def test_pensando_dura_ate_a_proxima_fase():
    assert REACOES[Fase.BUSCANDO].voltas is None


def test_desfechos_tem_duracao_finita():
    for fase in (Fase.PRONTO, Fase.RECUSADO, Fase.ERRO):
        assert REACOES[fase].voltas, f"{fase} ficaria tocando para sempre"


def test_cancelar_encerra_a_reacao():
    assert REACOES[Fase.OCIOSO].animacao is None


def test_resolver_usa_a_animacao_quando_o_personagem_tem():
    sprites = SimpleNamespace(Poke="poke.png")
    quadros = SimpleNamespace(Poke=120)
    assert resolver_animacao("Poke", sprites, quadros) == "Poke"


def test_resolver_cai_no_idle_sem_quadros_ou_sem_sprite():
    assert resolver_animacao("Poke", SimpleNamespace(Poke="poke.png"), SimpleNamespace(Poke=0)) == FALLBACK
    assert resolver_animacao("Poke", SimpleNamespace(Poke=""), SimpleNamespace(Poke=120)) == FALLBACK
    assert resolver_animacao("Poke", SimpleNamespace(), SimpleNamespace()) == FALLBACK
