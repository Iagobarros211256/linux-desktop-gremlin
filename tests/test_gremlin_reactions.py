"""O Gremlin de verdade (GremlinWindow) reagindo às fases da pergunta.

O relógio da animação (master_timer) fica parado: os quadros avançam na
mão com tick(), então dá para contar exatamente quanto cada reação dura.
"""

import pytest

from src import config_manager, settings
from src.assistant.dialog import Fase
from src.settings import State


@pytest.fixture(scope="session")
def config(qapp):
    ok = (config_manager.load_master_config(["gremlin"]) and config_manager.load_sfx_map()
          and config_manager.load_sprite_map() and config_manager.load_frame_count()
          and config_manager.load_emote_config())
    assert ok


@pytest.fixture
def gremlin(config, monkeypatch):
    from src.gremlin import GremlinWindow
    from src.system_monitor import SystemMonitor

    # Sem a thread do monitor: chamar stop() depois não basta, porque a
    # 1ª leitura de CPU já pode estar em andamento e agendar um "estresse"
    # no meio do teste se a máquina estiver ocupada.
    monkeypatch.setattr(SystemMonitor, "start", lambda self: None)
    w = GremlinWindow()
    w.master_timer.stop()  # quadros avançam só com tick()
    w.monitor._is_music = False
    w.set_state(State.IDLE)  # pula a intro
    yield w
    w.idle_timer.stop()
    w.emote_duration_timer.stop()
    w.emote_timer.stop()
    if getattr(w, "tray_icon", None):
        w.tray_icon.hide()
    w.deleteLater()


def tick(w, n=1):
    for _ in range(n):
        w.animation_tick()


def quadros(nome):
    return getattr(settings.FrameCounts, nome)


# --- pensando ---------------------------------------------------------------------


def test_buscando_comeca_a_pensar(gremlin):
    gremlin.react_to_assistant(Fase.BUSCANDO)
    assert gremlin.current_state == State.ASSISTANT
    assert gremlin._assist_anim == "Grab"


def test_pensando_nao_acaba_sozinho(gremlin):
    gremlin.react_to_assistant(Fase.BUSCANDO)
    tick(gremlin, quadros("Grab") * 10)  # 10 voltas inteiras
    assert gremlin.current_state == State.ASSISTANT


def test_primeiro_token_nao_reinicia_a_animacao(gremlin):
    gremlin.react_to_assistant(Fase.BUSCANDO)
    tick(gremlin, 7)
    gremlin.react_to_assistant(Fase.RESPONDENDO)
    assert gremlin._assist_frame == 7


def test_acorda_se_estava_dormindo(gremlin):
    gremlin.set_state(State.SLEEP)
    gremlin.react_to_assistant(Fase.BUSCANDO)
    assert gremlin.current_state == State.ASSISTANT


# --- desfechos --------------------------------------------------------------------


@pytest.mark.parametrize("fase, anim, voltas", [
    (Fase.PRONTO, "Emote", 2),
    (Fase.RECUSADO, "Poke", 1),
    (Fase.ERRO, "Hover", 2),
])
def test_desfecho_toca_n_voltas_e_volta_ao_idle(gremlin, fase, anim, voltas):
    gremlin.react_to_assistant(Fase.BUSCANDO)
    tick(gremlin, 30)
    gremlin.react_to_assistant(fase)
    assert gremlin._assist_anim == anim

    total = quadros(anim) * voltas
    tick(gremlin, total - 1)
    assert gremlin.current_state == State.ASSISTANT, "acabou um quadro antes"
    tick(gremlin)
    assert gremlin.current_state == State.IDLE


def test_cancelar_volta_ao_idle_na_hora(gremlin):
    gremlin.react_to_assistant(Fase.BUSCANDO)
    gremlin.react_to_assistant(Fase.OCIOSO)
    assert gremlin.current_state == State.IDLE


def test_cancelar_sem_reacao_nao_mexe_no_estado(gremlin):
    gremlin.set_state(State.SLEEP)
    gremlin.react_to_assistant(Fase.OCIOSO)
    assert gremlin.current_state == State.SLEEP


def test_personagem_sem_a_animacao_usa_idle(gremlin, monkeypatch):
    monkeypatch.setattr(settings.FrameCounts, "Poke", 0)
    gremlin.react_to_assistant(Fase.RECUSADO)
    assert gremlin._assist_anim == "Idle"
    tick(gremlin, quadros("Idle"))
    assert gremlin.current_state == State.IDLE  # e não congela


# --- convivência com as reações que já existiam -----------------------------------


def test_cpu_alta_nao_interrompe_o_pensando(gremlin):
    gremlin.react_to_assistant(Fase.BUSCANDO)
    gremlin._queue_stress_reaction(90.0, 0.0)
    tick(gremlin)
    assert gremlin.current_state == State.ASSISTANT


def test_cpu_alta_continua_funcionando_fora_da_pergunta(gremlin):
    gremlin._queue_stress_reaction(90.0, 0.0)
    tick(gremlin)
    assert gremlin.current_state == State.STRESSED


def test_musica_nao_interrompe_o_pensando_e_volta_a_dancar_depois(gremlin):
    gremlin.react_to_assistant(Fase.BUSCANDO)
    gremlin.monitor._is_music = True
    gremlin._queue_music_reaction(True)
    tick(gremlin)
    assert gremlin.current_state == State.ASSISTANT

    gremlin.react_to_assistant(Fase.PRONTO)
    tick(gremlin, quadros("Emote") * 2)
    assert gremlin.current_state == State.EMOTE  # dançando
    assert not gremlin.emote_duration_timer.isActive()  # e não para sozinho


def test_durante_a_saida_ignora_a_pergunta(gremlin):
    gremlin.set_state(State.OUTRO)
    gremlin.react_to_assistant(Fase.BUSCANDO)
    assert gremlin.current_state == State.OUTRO


# --- ligação janela -> Gremlin ----------------------------------------------------


def test_a_janela_aberta_pela_bandeja_move_o_gremlin(gremlin):
    gremlin.open_ask_window()
    janela = gremlin.ask_window
    janela._mudar_fase(Fase.BUSCANDO)
    assert gremlin.current_state == State.ASSISTANT

    janela._mudar_fase(Fase.PRONTO)
    assert gremlin._assist_anim == "Emote"
    janela.close()


def test_reabrir_a_janela_nao_duplica_a_reacao(gremlin):
    # O espião precisa estar no lugar ANTES da 1ª abertura, que é quando
    # o sinal é conectado.
    chamadas = []
    gremlin.react_to_assistant = chamadas.append
    gremlin.open_ask_window()
    gremlin.ask_window.close()
    gremlin.open_ask_window()
    gremlin.ask_window.close()
    gremlin.open_ask_window()

    gremlin.ask_window._mudar_fase(Fase.BUSCANDO)
    assert chamadas == [Fase.BUSCANDO]
    gremlin.ask_window.close()


# --- atalho do KDE (scripts/gremlin-perguntar) -------------------------------------


def test_atalho_abre_a_janela_de_perguntas(gremlin):
    from test_ipc import carregar_script, em_thread

    assert gremlin.command_server.escutando
    assert gremlin.ask_window is None
    resposta = em_thread(lambda: carregar_script().enviar("perguntar", gremlin.command_server.caminho))
    assert resposta == "ok"
    assert gremlin.ask_window is not None and gremlin.ask_window.isVisible()
    gremlin.ask_window.close()


def test_fechar_o_gremlin_libera_o_socket(gremlin, ipc_path):
    import os

    assert os.path.exists(ipc_path)
    gremlin.close_app()
    assert not os.path.exists(ipc_path)
    gremlin.close_timer.stop()
