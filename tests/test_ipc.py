import importlib.machinery
import importlib.util
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from src.assistant import ipc
from src.assistant.ipc import CommandServer

SCRIPT = Path(__file__).parent.parent / "scripts" / "gremlin-perguntar"


def carregar_script():
    """Importa o script (sem extensão .py) para testar as funções dele."""
    loader = importlib.machinery.SourceFileLoader("gremlin_perguntar", str(SCRIPT))
    spec = importlib.util.spec_from_loader("gremlin_perguntar", loader)
    modulo = importlib.util.module_from_spec(spec)
    loader.exec_module(modulo)
    return modulo


def girar_ate(condicao, timeout_s=5.0):
    """Roda o event loop do Qt até a condição valer (o servidor precisa dele)."""
    fim = time.monotonic() + timeout_s
    loop = QEventLoop()
    while not condicao() and time.monotonic() < fim:
        QTimer.singleShot(5, loop.quit)
        loop.exec()
    assert condicao(), "tempo esgotado"


def em_thread(funcao):
    """Executa um cliente bloqueante enquanto o Qt atende na thread principal."""
    resultado = {}

    def alvo():
        try:
            resultado["valor"] = funcao()
        except Exception as e:  # noqa: BLE001
            resultado["erro"] = e

    t = threading.Thread(target=alvo)
    t.start()
    girar_ate(lambda: not t.is_alive())
    if "erro" in resultado:
        raise resultado["erro"]
    return resultado["valor"]


def mandar_bruto(caminho, *pedacos, pausa=0.05):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(3)
        s.connect(caminho)
        for p in pedacos:
            s.sendall(p)
            time.sleep(pausa)
        resposta = b""
        while b"\n" not in resposta:
            pedaco = s.recv(256)
            if not pedaco:
                break
            resposta += pedaco
    return resposta.decode()


@pytest.fixture
def servidor(qapp, ipc_path):
    s = CommandServer()
    pedidos = []
    s.perguntar_pedido.connect(lambda: pedidos.append(1))
    s.pedidos = pedidos
    assert s.start()
    yield s
    s.close()


# --- caminho do socket ------------------------------------------------------------


@pytest.mark.parametrize("env", [
    {"GREMLIN_IPC_PATH": "/x/y.sock", "XDG_RUNTIME_DIR": "/run/user/1000"},
    {"XDG_RUNTIME_DIR": "/run/user/1000"},
    {},
])
def test_script_e_servidor_concordam_no_caminho(monkeypatch, env):
    for var in ("GREMLIN_IPC_PATH", "XDG_RUNTIME_DIR"):
        monkeypatch.delenv(var, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert carregar_script().socket_path() == ipc.socket_path()


def test_caminho_padrao_fica_no_runtime_do_usuario(monkeypatch):
    monkeypatch.delenv("GREMLIN_IPC_PATH")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    assert ipc.socket_path() == "/run/user/1000/linux-desktop-gremlin.sock"


# --- protocolo --------------------------------------------------------------------


def test_perguntar_responde_ok_e_emite_o_sinal(servidor):
    script = carregar_script()
    resposta = em_thread(lambda: script.enviar("perguntar", servidor.caminho))
    assert resposta == "ok"
    assert servidor.pedidos == [1]


def test_comando_chegando_em_pedacos(servidor):
    resposta = em_thread(lambda: mandar_bruto(servidor.caminho, b"pergun", b"tar\n"))
    assert resposta == "ok\n"
    assert servidor.pedidos == [1]


def test_comando_desconhecido(servidor):
    resposta = em_thread(lambda: mandar_bruto(servidor.caminho, b"rm -rf\n"))
    assert resposta.startswith("erro: comando desconhecido")
    assert servidor.pedidos == []


def test_linha_sem_fim_e_longa_demais_e_recusada(servidor):
    resposta = em_thread(lambda: mandar_bruto(servidor.caminho, b"a" * 400))
    assert resposta == "erro: linha longa demais\n"


def test_varios_atalhos_seguidos(servidor):
    script = carregar_script()
    for _ in range(5):
        assert em_thread(lambda: script.enviar("perguntar", servidor.caminho)) == "ok"
    assert len(servidor.pedidos) == 5


# --- ciclo de vida do socket ------------------------------------------------------


def test_close_apaga_o_arquivo_do_socket(qapp, ipc_path):
    s = CommandServer()
    assert s.start()
    assert os.path.exists(ipc_path)
    s.close()
    assert not os.path.exists(ipc_path)


def test_sobra_de_gremlin_que_crashou_e_limpa(qapp, ipc_path):
    # Socket criado e abandonado sem listen: o arquivo existe, ninguém atende.
    morto = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    morto.bind(ipc_path)
    morto.close()
    assert os.path.exists(ipc_path)

    s = CommandServer()
    assert s.start()
    assert em_thread(lambda: carregar_script().enviar("perguntar", ipc_path)) == "ok"
    s.close()


def test_segundo_gremlin_nao_rouba_o_socket_do_primeiro(servidor):
    segundo = CommandServer()
    assert segundo.start() is False
    assert not segundo.escutando

    em_thread(lambda: carregar_script().enviar("perguntar", servidor.caminho))
    assert servidor.pedidos == [1]  # o primeiro continua atendendo


# --- o script de verdade, como o KDE vai rodar ------------------------------------


@pytest.fixture
def notify_falso(tmp_path, monkeypatch):
    """notify-send de mentira que grava a mensagem num arquivo."""
    pasta = tmp_path / "bin"
    pasta.mkdir()
    registro = tmp_path / "notificacoes.txt"
    falso = pasta / "notify-send"
    falso.write_text(f'#!/bin/sh\necho "$@" >> {registro}\n')
    falso.chmod(0o755)
    monkeypatch.setenv("PATH", f"{pasta}:{os.environ['PATH']}")
    return registro


def rodar_script():
    return subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True,
                          env=os.environ.copy(), timeout=10)


def test_script_com_gremlin_aberto(servidor):
    inicio = time.monotonic()
    processo = em_thread(rodar_script)
    duracao = time.monotonic() - inicio

    assert processo.returncode == 0, processo.stderr
    assert servidor.pedidos == [1]
    assert duracao < 1.0, f"atalho lento: {duracao:.2f}s"


def test_script_com_gremlin_fechado_avisa_na_tela(qapp, notify_falso):
    processo = rodar_script()
    assert processo.returncode == 1
    assert "não está aberto" in notify_falso.read_text()


def test_script_e_executavel_e_nao_importa_pyside():
    assert os.access(SCRIPT, os.X_OK)
    assert SCRIPT.read_text().startswith("#!/usr/bin/env python3")
    assert "PySide6" not in SCRIPT.read_text().split('"""', 2)[2]  # fora da docstring


def test_socket_so_o_proprio_usuario_acessa(servidor):
    import stat

    modo = stat.S_IMODE(os.stat(servidor.caminho).st_mode)
    assert modo & 0o077 == 0, f"grupo/outros têm acesso: {oct(modo)}"
