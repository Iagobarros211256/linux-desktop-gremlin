// Protótipo em QML (Qt Quick) — mesmo roteiro do protótipo em Godot.
// Tudo é declarativo: o roteiro é uma SequentialAnimation, e cada
// efeito (mola do balão, pontinhos, palavras entrando) é uma animação
// presa a uma propriedade. Medidas e cores iguais às do src/assistant.
import QtQuick

Item {
    id: raiz
    width: 520; height: 650

    // --- paleta (a mesma do balão em QWidget) --------------------------------------
    readonly property color papel: "#FBFAFF"
    readonly property color tinta: "#2B2D52"
    readonly property color laco: "#C8323C"
    readonly property color boina: "#EEEDFA"
    readonly property color sussurro: "#6B6E8F"
    readonly property string familia: "Nunito"

    // --- geometria (igual a bubble.py) -----------------------------------------------
    readonly property real borda: 3.5
    readonly property real raio: 20
    readonly property real caudaAltura: 30
    readonly property real caudaLargura: 42
    readonly property real caudaX: 220  // ponta, relativo ao balão

    readonly property string pergunta: "como funciona o escalonador do linux?"
    readonly property var resposta: ("O escalonador do Linux usa o CFS, que organiza as tarefas "
        + "numa árvore rubro-negra ordenada por vruntime [1]. A tarefa com menor "
        + "vruntime roda primeiro [3].").split(" ")

    // estado da cena, mexido pelo roteiro
    property int letras: 0
    property int palavras: 0
    property bool pensando: false
    property string status: ""
    property string botao: "Perguntar"

    // Fundo só na gravação (sem compositor, transparente sairia preto).
    Rectangle {
        anchors.fill: parent
        visible: gravando
        gradient: Gradient {
            GradientStop { position: 0; color: "#1b1b22" }
            GradientStop { position: 1; color: "#0d0d12" }
        }
    }

    // --- Gremlin -----------------------------------------------------------------------
    Item {
        id: gremlin
        x: 110; y: 332; width: 300; height: 300
        clip: true
        property string anim: "idle"
        property int quadro: 0
        property var total: ({ idle: 340, grab: 60, emote: 54 })
        function tocar(nome) { anim = nome; quadro = 0 }

        Image {
            source: spritesDir + "/" + gremlin.anim + ".png"
            x: -(gremlin.quadro % 10) * 300
            y: -Math.floor(gremlin.quadro / 10) * 300
            smooth: true
        }
        Timer {  // 25 fps, como o sprite-map.json
            interval: 40; running: true; repeat: true
            onTriggered: gremlin.quadro = (gremlin.quadro + 1) % gremlin.total[gremlin.anim]
        }
    }

    // --- Balão -------------------------------------------------------------------------
    Item {
        id: balao
        x: 40; y: 20; width: 440; height: 342
        opacity: 0
        property real escala: 0.2
        // Cresce a partir da ponta da cauda: parece sair da boca do Gremlin.
        transform: Scale { origin.x: raiz.caudaX; origin.y: balao.height; xScale: balao.escala; yScale: balao.escala }

        Canvas {
            anchors.fill: parent
            antialiasing: true
            onPaint: {
                const c = getContext("2d"), m = raiz.borda / 2 + 0.5
                const w = width, h = height, r = raiz.raio
                const base = h - m - raiz.caudaAltura
                const desvio = 16, meia = raiz.caudaLargura / 2, cx = raiz.caudaX
                const esq = cx - meia - desvio, dir = cx + meia - desvio
                const pontaY = h - m, meioY = base + (pontaY - base) * 0.6
                c.reset()
                c.beginPath()
                c.moveTo(m + r, m)
                c.arcTo(w - m, m, w - m, base, r)
                c.arcTo(w - m, base, m, base, r)
                c.lineTo(dir, base)
                c.quadraticCurveTo(dir - 4, meioY, cx, pontaY)   // lado de dentro
                c.quadraticCurveTo(esq + 4, meioY, esq, base)    // lado de fora
                c.arcTo(m, base, m, m, r)
                c.arcTo(m, m, w - m, m, r)
                c.closePath()
                c.fillStyle = raiz.papel
                c.fill()
                c.lineWidth = raiz.borda
                c.lineJoin = "round"
                c.strokeStyle = raiz.tinta
                c.stroke()
            }
        }

        Column {
            x: 18; y: 14; width: balao.width - 32
            spacing: 6

            Row {
                spacing: 8
                Rectangle {  // campo de pergunta
                    width: 300; height: 34; radius: 12
                    color: raiz.boina
                    border.width: 2; border.color: raiz.laco
                    Text {
                        x: 12; anchors.verticalCenter: parent.verticalCenter
                        text: raiz.letras > 0 ? raiz.pergunta.slice(0, raiz.letras) : "Pergunte sobre o seu acervo"
                        color: raiz.letras > 0 ? raiz.tinta : raiz.sussurro
                        font { family: raiz.familia; pointSize: 10 }
                    }
                }
                Rectangle {  // botão
                    width: 86; height: 34; radius: 12; color: raiz.tinta
                    Text {
                        anchors.centerIn: parent; text: raiz.botao; color: raiz.papel
                        font { family: raiz.familia; pointSize: 10; weight: Font.DemiBold }
                    }
                }
                Text { text: "✕"; color: raiz.sussurro; anchors.verticalCenter: parent.verticalCenter }
            }

            Text {
                text: raiz.status; color: raiz.sussurro; height: 18
                font { family: raiz.familia; pointSize: 9 }
            }

            Item {  // área da resposta
                width: parent.width; height: 150

                Row {  // três pontinhos pensando
                    spacing: 7; y: 10
                    opacity: raiz.pensando ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: 200 } }
                    Repeater {
                        model: 3
                        Rectangle {
                            width: 9; height: 9; radius: 4.5; color: raiz.tinta
                            transform: Translate { id: pulo; y: 0 }
                            SequentialAnimation {
                                running: raiz.pensando; loops: Animation.Infinite
                                PauseAnimation { duration: index * 140 }
                                NumberAnimation { target: pulo; property: "y"; to: -7; duration: 220; easing.type: Easing.OutQuad }
                                NumberAnimation { target: pulo; property: "y"; to: 0; duration: 260; easing.type: Easing.InQuad }
                                PauseAnimation { duration: (2 - index) * 140 + 120 }
                            }
                        }
                    }
                }

                Flow {  // palavras da resposta
                    width: parent.width; spacing: 4
                    Repeater {
                        // Modelo fixo (a lista de palavras): cada palavra só
                        // anima quando "chega". Usar um número como modelo
                        // recriaria todas as palavras a cada nova.
                        model: raiz.resposta
                        Text {
                            id: palavra
                            text: modelData; color: raiz.tinta
                            font { family: raiz.familia; pointSize: 10 }
                            opacity: 0
                            transform: Translate { id: sobe; y: 6 }
                            property bool chegou: index < raiz.palavras
                            onChegouChanged: chegou ? entrada.start() : (opacity = 0, sobe.y = 6)
                            ParallelAnimation {
                                id: entrada
                                NumberAnimation { target: palavra; property: "opacity"; to: 1; duration: 180 }
                                NumberAnimation { target: sobe; property: "y"; to: 0; duration: 220; easing.type: Easing.OutCubic }
                            }
                        }
                    }
                }
            }

            Item {
                width: parent.width; height: 22
                Text {
                    id: fontes
                    text: "Fontes (3) ▸"; color: raiz.sussurro; opacity: 0
                    font { family: raiz.familia; pointSize: 9 }
                    transform: Translate { id: fontesX; x: -8 }
                }
                Text {
                    anchors.right: parent.right
                    text: "☐ Incluir restritos"; color: raiz.tinta
                    font { family: raiz.familia; pointSize: 9 }
                }
            }
        }
    }

    // --- Roteiro (idêntico ao do Godot; tempos em ms) -----------------------------------
    SequentialAnimation {
        id: roteiro
        running: true
        loops: Animation.Infinite

        ScriptAction { script: {
            raiz.letras = 0; raiz.palavras = 0; raiz.pensando = false
            raiz.status = ""; raiz.botao = "Perguntar"
            fontes.opacity = 0; fontesX.x = -8; gremlin.tocar("idle")
        } }
        PauseAnimation { duration: 800 }

        // abre: mola a partir da ponta da cauda
        ParallelAnimation {
            NumberAnimation { target: balao; property: "escala"; from: 0.2; to: 1; duration: 420; easing.type: Easing.OutBack; easing.overshoot: 1.6 }
            NumberAnimation { target: balao; property: "opacity"; from: 0; to: 1; duration: 180 }
        }
        PauseAnimation { duration: 0 }

        // digita a pergunta (35 ms por letra)
        NumberAnimation { target: raiz; property: "letras"; from: 0; to: raiz.pergunta.length; duration: raiz.pergunta.length * 35 }
        PauseAnimation { duration: 370 }

        // envia: Gremlin pensa
        ScriptAction { script: {
            raiz.botao = "Cancelar"; raiz.status = "Buscando no acervo…"
            raiz.pensando = true; gremlin.tocar("grab")
        } }
        PauseAnimation { duration: 2300 }

        // resposta chegando, palavra por palavra (90 ms)
        ScriptAction { script: { raiz.pensando = false; raiz.status = "Respondendo…" } }
        NumberAnimation { target: raiz; property: "palavras"; from: 0; to: raiz.resposta.length; duration: raiz.resposta.length * 90 }
        PauseAnimation { duration: 200 }

        // pronto: pulinho do balão, fontes deslizam, Gremlin comemora
        ScriptAction { script: {
            raiz.botao = "Perguntar"; raiz.status = "Pronto em 4,4 s, 11,8 tokens/s"
            gremlin.tocar("emote")
        } }
        ParallelAnimation {
            SequentialAnimation {
                NumberAnimation { target: balao; property: "escala"; to: 1.04; duration: 90; easing.type: Easing.OutQuad }
                NumberAnimation { target: balao; property: "escala"; to: 1; duration: 320; easing.type: Easing.OutBack; easing.overshoot: 2.2 }
            }
            NumberAnimation { target: fontes; property: "opacity"; to: 1; duration: 260 }
            NumberAnimation { target: fontesX; property: "x"; to: 0; duration: 320; easing.type: Easing.OutCubic }
        }
        PauseAnimation { duration: 3920 }  // emote: 2 voltas de 54 quadros a 25 fps

        ScriptAction { script: gremlin.tocar("idle") }
        PauseAnimation { duration: 1000 }

        // fecha
        ParallelAnimation {
            NumberAnimation { target: balao; property: "escala"; to: 0.8; duration: 220; easing.type: Easing.InQuad }
            NumberAnimation { target: balao; property: "opacity"; to: 0; duration: 220 }
        }
        PauseAnimation { duration: 1500 }
    }
}
