// Balão de fala do Gremlin. Toda a lógica está no AskController
// (exposto aqui como `ctl`); este arquivo só desenha e anima.
//
// Só QtQuick puro, sem QtQuick.Controls: os Controls pegariam o estilo
// do KDE, e o balão tem que ter a mesma cara em qualquer tema.
import QtQuick

Item {
    id: raiz
    // Margem transparente em volta: a mola de abertura passa de 100% e
    // seria cortada pela borda da janela.
    readonly property real margem: 16
    width: corpo.width + 2 * margem
    height: corpo.height + 2 * margem
    focus: true

    // --- paleta (tirada do personagem) ---------------------------------------------------
    readonly property color papel: "#FBFAFF"     // branco puxado para o lilás da boina
    readonly property color tinta: "#2B2D52"     // azul-marinho do uniforme
    readonly property color laco: "#C8323C"      // laço vermelho: foco e erro
    readonly property color boina: "#EEEDFA"     // lilás claro: fundo do campo
    readonly property color sussurro: "#6B6E8F"  // texto secundário
    readonly property string familia: "Nunito"   // cai em sans-serif se não houver

    // --- geometria (a mesma de bubble.py) ------------------------------------------------
    readonly property real borda: 3.5
    readonly property real raio: 20
    readonly property real caudaAltura: 30
    readonly property real caudaLargura: 42

    property bool fontesAbertas: false
    property bool restrito: false
    property real escala: 1

    function fechar() { saida.start() }

    Keys.onEscapePressed: ctl.emAndamento ? ctl.cancelar() : fechar()

    Item {
    id: corpo
    x: raiz.margem; y: raiz.margem
    width: 440
    height: coluna.implicitHeight + 28 + raiz.caudaAltura
    transform: Scale {
        // Cresce e encolhe a partir da ponta da cauda: sai da boca do Gremlin.
        origin.x: ctl.caudaX
        origin.y: ctl.caudaEmbaixo ? corpo.height : 0
        xScale: raiz.escala; yScale: raiz.escala
    }

    // --- desenho do balão ------------------------------------------------------------------
    Canvas {
        id: desenho
        anchors.fill: parent
        antialiasing: true
        onPaint: {
            const c = getContext("2d"), m = raiz.borda / 2 + 0.5
            const w = width, h = height, r = raiz.raio, ca = raiz.caudaAltura
            const embaixo = ctl.caudaEmbaixo, cx = ctl.caudaX
            const topo = embaixo ? m : m + ca, base = embaixo ? h - m - ca : h - m
            const esq = cx - raiz.caudaLargura / 2 - 16, dir = cx + raiz.caudaLargura / 2 - 16
            c.reset()
            c.beginPath()
            c.moveTo(m + r, topo)
            if (!embaixo) {  // cauda em cima, apontando para os pés do Gremlin
                const meio = topo - (topo - m) * 0.6
                c.lineTo(esq, topo)
                c.quadraticCurveTo(esq + 4, meio, cx, m)
                c.quadraticCurveTo(dir - 4, meio, dir, topo)
            }
            c.arcTo(w - m, topo, w - m, base, r)
            c.arcTo(w - m, base, m, base, r)
            if (embaixo) {  // cauda embaixo, apontando para a cabeça
                const meio = base + (h - m - base) * 0.6
                c.lineTo(dir, base)
                c.quadraticCurveTo(dir - 4, meio, cx, h - m)
                c.quadraticCurveTo(esq + 4, meio, esq, base)
            }
            c.arcTo(m, base, m, topo, r)
            c.arcTo(m, topo, w - m, topo, r)
            c.closePath()
            c.fillStyle = raiz.papel
            c.fill()
            c.lineWidth = raiz.borda
            c.lineJoin = "round"
            c.strokeStyle = raiz.tinta
            c.stroke()
        }
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections {
            target: ctl
            function onCaudaMudou() { desenho.requestPaint() }
        }
    }

    // --- conteúdo -------------------------------------------------------------------------
    Column {
        id: coluna
        x: 18
        y: ctl.caudaEmbaixo ? 14 : 14 + raiz.caudaAltura
        width: corpo.width - 32
        spacing: 6

        Row {
            spacing: 8

            Rectangle {  // campo de pergunta
                width: 300; height: 34; radius: 12
                color: raiz.boina
                border.width: 2
                border.color: campo.activeFocus ? raiz.laco : "transparent"

                TextInput {
                    id: campo
                    objectName: "campo"
                    anchors { fill: parent; leftMargin: 12; rightMargin: 12 }
                    verticalAlignment: TextInput.AlignVCenter
                    color: raiz.tinta
                    selectionColor: raiz.tinta
                    selectedTextColor: raiz.papel
                    selectByMouse: true
                    clip: true
                    readOnly: ctl.emAndamento
                    font { family: raiz.familia; pointSize: 10 }
                    Keys.onReturnPressed: ctl.acionar(text, raiz.restrito)
                    Keys.onEnterPressed: ctl.acionar(text, raiz.restrito)
                    Keys.onEscapePressed: ctl.emAndamento ? ctl.cancelar() : raiz.fechar()

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: !campo.text
                        text: "Pergunte sobre o seu acervo"
                        color: raiz.sussurro
                        font: campo.font
                    }
                }
            }

            Rectangle {  // Perguntar / Cancelar
                width: 86; height: 34; radius: 12
                color: raiz.tinta
                opacity: botaoArea.pressed ? 0.8 : 1
                Text {
                    anchors.centerIn: parent
                    text: ctl.textoBotao
                    color: raiz.papel
                    font { family: raiz.familia; pointSize: 10; weight: Font.DemiBold }
                }
                MouseArea {
                    id: botaoArea
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: ctl.acionar(campo.text, raiz.restrito)
                }
            }

            Text {  // esconder
                anchors.verticalCenter: parent.verticalCenter
                text: "✕"
                color: fecharArea.containsMouse ? raiz.tinta : raiz.sussurro
                font.pointSize: 10
                MouseArea {
                    id: fecharArea
                    anchors { fill: parent; margins: -6 }
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: raiz.fechar()
                }
            }
        }

        Text {
            width: parent.width
            visible: text !== ""
            text: ctl.status
            color: ctl.statusErro ? raiz.laco : raiz.sussurro
            wrapMode: Text.Wrap
            font { family: raiz.familia; pointSize: 9 }
        }

        Item {  // área da resposta
            width: parent.width
            height: 150

            Text {
                visible: palavras.count === 0 && ctl.faseNome !== "BUSCANDO"
                width: parent.width
                text: "A resposta aparece aqui, citando as fontes como [1], [2]…"
                color: raiz.sussurro
                wrapMode: Text.Wrap
                font { family: raiz.familia; pointSize: 10 }
            }

            Row {  // pensando
                y: 8
                spacing: 7
                opacity: ctl.faseNome === "BUSCANDO" ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 200 } }
                Repeater {
                    model: 3
                    Rectangle {
                        width: 9; height: 9; radius: 4.5
                        color: raiz.tinta
                        transform: Translate { id: pulo }
                        SequentialAnimation {
                            running: ctl.faseNome === "BUSCANDO"
                            loops: Animation.Infinite
                            onStopped: pulo.y = 0
                            PauseAnimation { duration: index * 140 }
                            NumberAnimation { target: pulo; property: "y"; to: -7; duration: 220; easing.type: Easing.OutQuad }
                            NumberAnimation { target: pulo; property: "y"; to: 0; duration: 260; easing.type: Easing.InQuad }
                            PauseAnimation { duration: (2 - index) * 140 + 120 }
                        }
                    }
                }
            }

            Flickable {
                id: rolagem
                anchors.fill: parent
                contentHeight: fluxo.height
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                Flow {
                    id: fluxo
                    width: rolagem.width
                    spacing: 4
                    onHeightChanged: rolagem.contentY = Math.max(0, height - rolagem.height)

                    Repeater {
                        model: ListModel { id: palavras }
                        delegate: Item {
                            id: pedaco
                            required property string texto
                            required property string tipo
                            // Quebra = item da largura toda; parágrafo ganha respiro.
                            // Altura nunca 0: o Flow ignora itens de altura zero.
                            width: tipo === "palavra" ? rotulo.implicitWidth : fluxo.width
                            height: tipo === "palavra" ? rotulo.implicitHeight : (tipo === "paragrafo" ? 6 : 1)

                            Text {
                                id: rotulo
                                visible: pedaco.tipo === "palavra"
                                text: pedaco.texto
                                // [1], [2]… em tom mais baixo, como nota de rodapé
                                color: /^\[\d+\]/.test(pedaco.texto) ? raiz.sussurro : raiz.tinta
                                font { family: raiz.familia; pointSize: 10; italic: ctl.recusada }
                                opacity: 0
                                transform: Translate { id: sobe; y: 6 }
                                Component.onCompleted: entrada.start()
                                ParallelAnimation {
                                    id: entrada
                                    NumberAnimation { target: rotulo; property: "opacity"; to: 1; duration: 180 }
                                    NumberAnimation { target: sobe; property: "y"; to: 0; duration: 220; easing.type: Easing.OutCubic }
                                }
                            }
                        }
                    }
                }
            }
        }

        Column {  // fontes (abertas)
            width: parent.width
            visible: raiz.fontesAbertas && ctl.fontes.length > 0
            spacing: 2
            Repeater {
                model: ctl.fontes
                Column {
                    required property var modelData
                    required property int index
                    width: parent ? parent.width : 0
                    Text {
                        width: parent.width
                        elide: Text.ElideRight
                        text: "[" + modelData.numero + "] " + modelData.titulo + (modelData.restrito ? "  (restrito)" : "")
                        color: fonteArea.containsMouse ? raiz.tinta : raiz.sussurro
                        font { family: raiz.familia; pointSize: 9; underline: fonteArea.containsMouse }
                        MouseArea {
                            id: fonteArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onDoubleClicked: ctl.abrirFonte(index)
                        }
                    }
                    Text {  // caminho aparece ao passar o mouse
                        width: parent.width
                        visible: fonteArea.containsMouse
                        elide: Text.ElideMiddle
                        text: modelData.caminho + "  (duplo clique abre)"
                        color: raiz.sussurro
                        font { family: raiz.familia; pointSize: 8 }
                    }
                }
            }
        }

        Item {  // rodapé
            width: parent.width
            height: 22

            Row {
                spacing: 14
                anchors.verticalCenter: parent.verticalCenter

                Text {
                    id: botaoFontes
                    visible: ctl.fontes.length > 0
                    text: "Fontes (" + ctl.fontes.length + ") " + (raiz.fontesAbertas ? "▾" : "▸")
                    color: fontesArea.containsMouse ? raiz.tinta : raiz.sussurro
                    font { family: raiz.familia; pointSize: 9 }
                    opacity: 0
                    transform: Translate { id: fontesX; x: -8 }
                    onVisibleChanged: if (visible) chegada.start(); else { opacity = 0; fontesX.x = -8 }
                    ParallelAnimation {
                        id: chegada
                        NumberAnimation { target: botaoFontes; property: "opacity"; to: 1; duration: 260 }
                        NumberAnimation { target: fontesX; property: "x"; to: 0; duration: 320; easing.type: Easing.OutCubic }
                    }
                    MouseArea {
                        id: fontesArea
                        anchors { fill: parent; margins: -4 }
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: raiz.fontesAbertas = !raiz.fontesAbertas
                    }
                }

                Text {
                    visible: ctl.temResposta && !ctl.emAndamento
                    text: copiado.running ? "Copiado" : "Copiar"
                    color: copiarArea.containsMouse ? raiz.tinta : raiz.sussurro
                    font { family: raiz.familia; pointSize: 9 }
                    Timer { id: copiado; interval: 1200 }
                    MouseArea {
                        id: copiarArea
                        anchors { fill: parent; margins: -4 }
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: { ctl.copiarResposta(); copiado.restart() }
                    }
                }
            }

            Row {  // caixa de seleção
                id: caixaRestrito
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                spacing: 6
                Rectangle {
                    width: 15; height: 15; radius: 4
                    anchors.verticalCenter: parent.verticalCenter
                    color: raiz.restrito ? raiz.laco : "transparent"
                    border.width: 2
                    border.color: raiz.restrito ? raiz.laco : raiz.sussurro
                }
                Text {
                    text: "Incluir restritos"
                    color: raiz.tinta
                    font { family: raiz.familia; pointSize: 9 }
                }
            }
            MouseArea {  // fora da Row: dentro dela, anchors quebra o layout
                anchors { fill: caixaRestrito; margins: -4 }
                objectName: "restritoArea"
                cursorShape: Qt.PointingHandCursor
                onClicked: raiz.restrito = !raiz.restrito
            }
        }
    }

    }  // corpo

    // --- animações e ligação com o controlador ---------------------------------------------
    ParallelAnimation {
        id: entradaBalao
        NumberAnimation { target: raiz; property: "escala"; from: 0.2; to: 1; duration: 420; easing.type: Easing.OutBack; easing.overshoot: 1.6 }
        NumberAnimation { target: raiz; property: "opacity"; from: 0; to: 1; duration: 180 }
    }

    SequentialAnimation {
        id: saida
        ParallelAnimation {
            NumberAnimation { target: raiz; property: "escala"; to: 0.85; duration: 200; easing.type: Easing.InQuad }
            NumberAnimation { target: raiz; property: "opacity"; to: 0; duration: 200 }
        }
        ScriptAction { script: ctl.concluirFechamento() }
    }

    SequentialAnimation {
        id: pulinho
        NumberAnimation { target: raiz; property: "escala"; to: 1.04; duration: 90; easing.type: Easing.OutQuad }
        NumberAnimation { target: raiz; property: "escala"; to: 1; duration: 320; easing.type: Easing.OutBack; easing.overshoot: 2.2 }
    }

    Connections {
        target: ctl
        function onPedidoAbrir() {
            saida.stop()
            entradaBalao.restart()
            campo.forceActiveFocus()
            campo.selectAll()
        }
        function onRespostaLimpa() { palavras.clear(); raiz.fontesAbertas = false }
        function onPedacoChegou(texto, tipo) { palavras.append({ texto: texto, tipo: tipo }) }
        function onTerminou() { pulinho.restart() }
    }
}
