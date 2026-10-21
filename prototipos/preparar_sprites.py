"""Remonta as spritesheets do iago-gremlin para caberem numa textura de GPU.

QML (Qt Quick) e Godot desenham na GPU, e GPU tem limite de tamanho de
textura (16384 px na maioria, incluindo a RX 580). A idle.png original
tem 5 colunas x 68 linhas = 1500 x 20400 px: não cabe. Em 10 colunas
fica 3000 x 10200. O Gremlin atual (QWidget) não sofre com isso porque
recorta cada quadro na CPU.

Uso, na raiz do repositório:
    uv run python prototipos/preparar_sprites.py
Gera prototipos/sprites/{idle,grab,emote}.png e quadros.json.
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ORIGEM = RAIZ / "spritesheet" / "iago-gremlin"
DESTINO = Path(__file__).resolve().parent / "sprites"
COLUNAS = 10
LIMITE_GPU = 16384
ANIMACOES = {"idle": "Idle", "grab": "Grab", "emote": "Emote"}


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841 (QImage/QPainter precisam dela)
    mapa = json.loads((ORIGEM / "sprite-map.json").read_text())
    quadros = json.loads((ORIGEM / "frame-count.json").read_text())
    lado, colunas_orig = mapa["FrameWidth"], mapa["SpriteColumn"]
    DESTINO.mkdir(exist_ok=True)

    info = {"lado": lado, "colunas": COLUNAS, "fps": mapa["FrameRate"], "animacoes": {}}
    for arquivo, chave in ANIMACOES.items():
        n = quadros[chave]
        origem = QImage(str(ORIGEM / f"{arquivo}.png"))
        linhas = -(-n // COLUNAS)
        saida = QImage(COLUNAS * lado, linhas * lado, QImage.Format.Format_ARGB32_Premultiplied)
        saida.fill(0)
        pintor = QPainter(saida)
        for i in range(n):
            ox, oy = (i % colunas_orig) * lado, (i // colunas_orig) * lado
            dx, dy = (i % COLUNAS) * lado, (i // COLUNAS) * lado
            pintor.drawImage(dx, dy, origem, ox, oy, lado, lado)
        pintor.end()
        assert max(saida.width(), saida.height()) <= LIMITE_GPU, arquivo
        saida.save(str(DESTINO / f"{arquivo}.png"))
        info["animacoes"][arquivo] = {"quadros": n, "linhas": linhas}
        print(f"{arquivo:6} {origem.width()}x{origem.height()} -> {saida.width()}x{saida.height()}")

    (DESTINO / "quadros.json").write_text(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
