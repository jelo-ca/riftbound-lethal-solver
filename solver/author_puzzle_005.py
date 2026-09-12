"""Author puzzle 005: "Clear the Way" (design/08-puzzle-concepts.md #5).

At 7 points, we hold "left" (Caitlyn - Patrolling, Scored via Hold this
turn). "right" is held by a tough defender (Might 3) that we can't
profitably attack directly: our only free attacker (Might 2) can't kill
it (2 < 3) and would die to the counter-damage (3 >= 2), losing our unit
for nothing and leaving "right" uncontested by the opponent.

The real solution: Caitlyn's activated ability deals damage WITHOUT
triggering combat — no retaliation at all — so she can solo-kill the
Might-3 defender for free from across the board (her ability targets "a
unit at a battlefield", not restricted to her own). With "right" now
empty, our attacker walks in uncontested for the Final Point.

Exercises: ActivateAbility (Caitlyn), and the actual lesson of this
puzzle — direct combat isn't always correct even when a unit theoretically
could attack; removing the problem first is free where fighting it isn't.

Run with: python -m solver.author_puzzle_005
"""

from __future__ import annotations

import json
from pathlib import Path

from .engine.abilities import CAITLYN_PATROLLING
from .engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from .export import export_puzzle

OUTPUT_PATH = Path(__file__).parent.parent / "puzzles" / "puzzle-005-clear-the-way.json"


def build_root() -> GameState:
    caitlyn = UnitInstance(
        card_id=CAITLYN_PATROLLING,
        instance_id=1,
        controller=0,
        might=3,
        keywords=frozenset(),
        exhausted=False,
        damage=0,
        is_token=False,
    )
    attacker = UnitInstance(
        card_id="ogn-010-298",  # Legion Rearguard, 2 might (real Origins printing)
        instance_id=2,
        controller=0,
        might=2,
        keywords=frozenset(),
        exhausted=False,
        damage=0,
        is_token=False,
    )
    tough_defender = UnitInstance(
        card_id="ogn-218-298",  # Vanguard Captain, 3 might (real Origins printing)
        instance_id=3,
        controller=1,
        might=3,
        keywords=frozenset(),
        exhausted=False,
        damage=0,
        is_token=False,
    )
    return GameState(
        turn_player=0,
        players=(
            PlayerState(
                base_units=frozenset({attacker}),
                hand=(),
                runes=RunePool(available=()),
                score=7,
            ),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, frozenset({caitlyn}), None),
            BattlefieldState("right", 1, frozenset({tough_defender}), None),
        ),
        scored_this_turn=frozenset({"left"}),  # Held this turn, pre-resolved
        cards_played_this_turn=0,
    )


def main() -> None:
    root = build_root()
    result = export_puzzle("puzzle-005-clear-the-way", root, cards={})
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"Solution: {len(result['solution'])} states")
    print(f"Nodes: {len(result['nodes'])}, terminal states: {len(result['terminal'])}")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
