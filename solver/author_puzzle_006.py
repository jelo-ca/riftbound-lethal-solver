"""Author puzzle 006: "Redirection" (design/08-puzzle-concepts.md #6).

At 7 points, we hold "right" (Scored via Hold this turn) with a small
unit already there. The opponent has exactly one blocker, sitting at
"left" — the battlefield we still need. Attacking it head-on is the trap
this puzzle is about: the real solution plays Blitzcrank - Impassive to
"right" and uses his "when you play me, you may move an enemy unit to
here" trigger to pull the opponent's blocker away from "left" entirely.
"left" becomes empty and uncontrolled the instant the blocker leaves it —
our separate attacker then walks in for a free Conquer and the Final
Point, since "right" was already Scored this turn.

This is the case design/09-combat-resolution.md calls "we are not always
the Attacker": redirecting the enemy unit onto "right" (which we hold)
makes THEM the Attacker and us the Defender for that combat. The redirect
also incidentally kills their blocker (Blitzcrank's Might comfortably
covers it), but that's not the point of the puzzle — leaving "left" open
is.

Run with: python -m solver.author_puzzle_006
"""

from __future__ import annotations

import json
from pathlib import Path

from .engine.abilities import BLITZCRANK_IMPASSIVE
from .engine.card_pool import CARD_POOL
from .engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from .export import export_puzzle

BLITZCRANK_CARD = CARD_POOL[BLITZCRANK_IMPASSIVE]

OUTPUT_PATH = Path(__file__).parent.parent / "puzzles" / "puzzle-006-redirection.json"



def build_root() -> GameState:
    right_guard = UnitInstance(
        card_id="ogn-010-298",  # Legion Rearguard, 2 might (real Origins printing)
        instance_id=1, controller=0, might=2, keywords=frozenset(),
        exhausted=False, damage=0, is_token=False,
    )
    attacker = UnitInstance(
        card_id="ogn-211-298",  # Faithful Manufactor, 2 might (real Origins printing)
        instance_id=2, controller=0, might=2, keywords=frozenset(),
        exhausted=False, damage=0, is_token=False,
    )
    blocker = UnitInstance(
        card_id="ogn-218-298",  # Vanguard Captain, 3 might (real Origins printing)
        instance_id=3, controller=1, might=3, keywords=frozenset(),
        exhausted=False, damage=0, is_token=False,
    )
    return GameState(
        turn_player=0,
        players=(
            PlayerState(
                base_units=frozenset({attacker}),
                hand=(BLITZCRANK_IMPASSIVE,),
                runes=RunePool(available=("Fury", "Fury", "Fury", "Fury", "Fury")),
                score=7,
            ),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 1, frozenset({blocker}), None),
            BattlefieldState("right", 0, frozenset({right_guard}), None),
        ),
        scored_this_turn=frozenset({"right"}),  # Held this turn, pre-resolved
        cards_played_this_turn=0,
    )


def main() -> None:
    root = build_root()
    cards = {BLITZCRANK_IMPASSIVE: BLITZCRANK_CARD}
    result = export_puzzle("puzzle-006-redirection", root, cards)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"Solution: {len(result['solution'])} states")
    print(f"Nodes: {len(result['nodes'])}, terminal states: {len(result['terminal'])}")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
