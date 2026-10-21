"""Como o Gremlin reage a cada fase de uma pergunta ao Stego.

É só uma tabela de dados: o gremlin.py lê a reação e toca. Trocar a
animação de uma fase é mudar uma linha aqui, sem mexer na máquina de
estados.

As animações usam as chaves do sprite-map.json ("Grab", "Emote"...).
Para o iago-gremlin:
  Grab  = mão na cabeça, bochecha inflada   -> pensando
  Emote = animada, acenando                 -> resposta pronta
  Poke  = vira de costas e volta            -> procurei e não achei
  Hover = mãos na boca, sem graça           -> deu erro
"""

from __future__ import annotations

from dataclasses import dataclass

from .dialog import Fase

FALLBACK = "Idle"


@dataclass(frozen=True)
class Reacao:
    animacao: str | None  # chave do SpriteMap; None = encerra a reação
    voltas: int | None = None  # vezes que a animação toca inteira; None = até a próxima fase
    som: str | None = None  # chave do SfxMap, tocada ao entrar


PENSANDO = Reacao("Grab")

REACOES: dict[Fase, Reacao] = {
    Fase.OCIOSO: Reacao(None),  # cancelou: volta ao normal na hora
    Fase.BUSCANDO: PENSANDO,
    # Mesma reação de BUSCANDO de propósito: a animação não reinicia
    # quando chega o primeiro token.
    Fase.RESPONDENDO: PENSANDO,
    Fase.PRONTO: Reacao("Emote", voltas=2, som="Emote"),
    Fase.RECUSADO: Reacao("Poke", voltas=1, som="Poke"),
    Fase.ERRO: Reacao("Hover", voltas=2),
}


def resolver_animacao(nome: str, sprite_map, frame_counts) -> str:
    """Devolve `nome` se o personagem tem essa animação; senão, Idle.

    Nem todo personagem tem todas: um sem "Poke" teria frame count 0 e
    o Gremlin ficaria congelado no último quadro.
    """
    tem_sprite = bool(getattr(sprite_map, nome, None))
    tem_quadros = bool(getattr(frame_counts, nome, None))
    return nome if tem_sprite and tem_quadros else FALLBACK
