# Protótipos: QML vs Godot

O mesmo balão de fala nas duas tecnologias, para decidir vendo. Os dois
seguem o mesmo roteiro, com os mesmos tempos, curvas de easing, cores e
medidas:

| tempo | o que acontece |
|---|---|
| 0,8 s | o balão abre com uma mola, crescendo a partir da ponta da cauda |
| 1,2 s | a pergunta é "digitada" (35 ms por letra) |
| 2,9 s | envia: o Gremlin pensa (grab) e três pontinhos pulam |
| 5,2 s | a resposta chega palavra por palavra (90 ms cada, com fade e subida) |
| 7,6 s | pronto: o balão dá um pulinho, "Fontes (3)" desliza, o Gremlin comemora |
| 12 s | o Gremlin volta ao idle; aos 13 s o balão fecha |

É uma demonstração com roteiro fixo: não conversa com o Stego, e os
botões não fazem nada. O roteiro repete sozinho. Esc fecha.

## Rodar no Nobara

Uma vez só, na raiz do repositório:

```bash
uv run python prototipos/preparar_sprites.py
```

As spritesheets originais não cabem numa textura de GPU (a `idle.png`
tem 1500×20400 px; o limite é 16384). O script remonta em 10 colunas
dentro de `prototipos/sprites/`. **Qualquer migração para QML ou Godot
precisa disso**: o Gremlin atual escapa porque recorta na CPU.

**QML** (usa o PySide6 que o projeto já tem):

```bash
QT_QPA_PLATFORM=xcb uv run python prototipos/qml/main.py
```

**Godot** (precisa do Godot 4.7: baixe o `Godot_v4.7.2-stable_linux.x86_64.zip`
em godotengine.org, ou `flatpak install flathub org.godotengine.Godot`):

```bash
godot --display-driver x11 --path prototipos/godot
```

Os dois abrem sem moldura, transparentes e por cima de tudo. O clique só
pega no balão e no Gremlin; fora deles passa para o desktop (QML com
`setMask`, Godot com `window_set_mouse_passthrough`).

## O que observei construindo

**Resultado visual:** praticamente igual. Os dois desenham na GPU,
fazem mola, fade e subida suave. A diferença não está no que dá para
fazer, está em como se trabalha e no que se aproveita.

**QML (260 linhas)**
- O roteiro inteiro é uma `SequentialAnimation` declarativa; animação
  presa a propriedade (`Behavior`, `NumberAnimation`) é o jeito natural
  da linguagem.
- O balão é desenhado com `Canvas`, que tem a mesma API do canvas do
  HTML.
- Reaproveita o Python: a máscara de clique usa o `bubble.py` que já
  existe. Cliente do Stego, socket do atalho, reações e os 107 testes
  continuam valendo.
- Pegadinha que me pegou: `Repeater` com um número como modelo recria
  todos os itens a cada mudança (todas as palavras refaziam o fade).

**Godot (298 linhas)**
- `await` + `Tween` deixam roteiros sequenciais muito legíveis. Num
  projeto de verdade daria para usar o editor de animação (AnimationPlayer)
  em vez de código.
- Click-through por polígono é nativo e o Gremlin poderia voltar a ser
  clicável (o QML consegue o mesmo com máscara no X11).
- Layout de texto em containers deu mais trabalho: o `HFlowContainer`
  justificou as linhas até eu mudar os size flags, e o tamanho de cada
  palavra precisou ser medido na fonte.
- Migrar significa refazer em GDScript o cliente SSE do Stego
  (`HTTPClient` com polling), trocar o socket Unix do atalho por TCP
  local (o Godot não tem socket Unix nativo) e refazer os testes (GUT).
