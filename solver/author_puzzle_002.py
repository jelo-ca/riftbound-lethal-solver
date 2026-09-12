"""Author puzzle 002: "Borrowed Time" (design/08-puzzle-concepts.md #2).

At 7 points, the player already holds "right" — Scored via Hold at this
turn's Beginning Phase, pre-baked into the starting position's
scored_this_turn (Hold isn't a live search action, see
design/02-state-model.md). Only "left" needs a Conquer to win.

This is the exact case that validates the rules correction from the
design pass: the Final Point condition is "Scored every battlefield this
turn" (rule 472-476), not "Conquered every battlefield" — Hold counts.
Two blog sources both said Conquer specifically, which would make this
puzzle wrongly look unsolvable in one move.

Run with: python -m solver.author_puzzle_002
"""

from __future__ import annotations

import json
from pathlib import Path

from .engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from .export import export_puzzle

OUTPUT_PATH = Path(__file__).parent.parent / "puzzles" / "puzzle-002-borrowed-time.json"


def build_root() -> GameState:
    holder = UnitInstance(
        card_id="ogn-010-298",  # Legion Rearguard, 2 might — already holding "right"
        instance_id=1,
        controller=0,
        might=2,
        keywords=frozenset(),
        exhausted=False,
        damage=0,
        is_token=False,
    )
    conqueror = UnitInstance(
        card_id="ogn-211-298",  # Faithful Manufactor, 2 might — at Base, ready to move
        instance_id=2,
        controller=0,
        might=2,
        keywords=frozenset(),
        exhausted=False,
        damage=0,
        is_token=False,
    )
    return GameState(
        turn_player=0,
        players=(
            PlayerState(
                base_units=frozenset({conqueror}),
                hand=(),
                runes=RunePool(available=()),
                score=7,
            ),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", 0, frozenset({holder}), None),
        ),
        scored_this_turn=frozenset({"right"}),  # Held this turn, pre-resolved
        cards_played_this_turn=0,
    )


def main() -> None:
    root = build_root()
    result = export_puzzle("puzzle-002-borrowed-time", root, cards={})
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"Solution: {len(result['solution'])} actions")
    print(f"Nodes: {len(result['nodes'])}, terminal states: {len(result['terminal'])}")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
