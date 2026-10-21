"""Roda o protótipo em QML.

    uv run python prototipos/qml/main.py            # janela transparente
    uv run python prototipos/qml/main.py --gravar   # com fundo, para gravar

O roteiro repete sozinho. Esc fecha.
"""

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QRegion, QShortcut
from PySide6.QtQuick import QQuickView

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent.parent))


def main() -> int:
    gravando = "--gravar" in sys.argv
    app = QGuiApplication(sys.argv)

    view = QQuickView()
    view.setTitle("Protótipo QML")
    view.rootContext().setContextProperty("gravando", gravando)
    view.rootContext().setContextProperty(
        "spritesDir", QUrl.fromLocalFile(str(AQUI.parent / "sprites")).toString())
    if not gravando:
        view.setColor(QColor(0, 0, 0, 0))
        view.setFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                      | Qt.WindowType.Tool)
    view.setSource(QUrl.fromLocalFile(str(AQUI / "Cena.qml")))
    if view.status() == QQuickView.Status.Error:
        for erro in view.errors():
            print(erro.toString())
        return 1

    if not gravando:
        # Clique só pega no balão e no Gremlin; fora deles passa para o
        # desktop. Reaproveita o desenho do balão do src/assistant.
        from src.assistant.bubble import caminho_balao
        forma = caminho_balao(440, 342, 220, True).toFillPolygon().toPolygon()
        forma.translate(40, 20)
        view.setMask(QRegion(forma) + QRegion(110, 332, 300, 300))

    QShortcut(QKeySequence("Esc"), view, activated=app.quit)
    view.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
