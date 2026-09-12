"""Author puzzle 001: "One Point Short" (design/08-puzzle-concepts.md #1).

At 7 points, two readied units sit at Base, both battlefields open. The
obvious line — Conquer just one battlefield — fails the Final Point
restriction (rule 474-476: the player must have Scored every battlefield
this turn). The real solution commits both units, one to each battlefield.

Uses two real Origins units already on the board, not played this turn —
so no CardDef/cost lookup is needed here. This doesn't yet exercise Sneaky
Deckhand's "play to an open battlefield" text (the mechanism originally
sketched for this concept): that's a PlayUnit target-override the engine
doesn't support yet (PlayUnit currently only allows Base or an
already-controlled battlefield, rule 355.7/355.8's default). Deferred to a
later puzzle once that override is actually needed — see
design/07-scope-and-cut-list.md's "add mechanics on demand" policy. This
puzzle still faithfully tests the trap itself: obvious single-Conquer
fails, committing both units wins.

Run with: python -m solver.author_puzzle_001
"""

from __future__ import annotations

import json
from pathlib import Path

from .engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from .export import export_puzzle

OUTPUT_PATH = Path(__file__).parent.parent / "puzzles" / "puzzle-001-one-point-short.json"


def build_root() -> GameState:
    legion_rearguard = UnitInstance(
        card_id="ogn-010-298",  # Legion Rearguard, 2 might (real Origins printing)
        instance_id=1,
        controller=0,
        might=2,
        keywords=frozenset(),
        exhausted=False,
        damage=0,
        is_token=False,
    )
    faithful_manufactor = UnitInstance(
        card_id="ogn-211-298",  # Faithful Manufactor, 2 might (real Origins printing)
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
                base_units=frozenset({legion_rearguard, faithful_manufactor}),
                hand=(),
                runes=RunePool(available=()),
                score=7,
            ),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def main() -> None:
    root = build_root()
    result = export_puzzle("puzzle-001-one-point-short", root, cards={})
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"Solution: {len(result['solution'])} actions")
    print(f"Nodes: {len(result['nodes'])}, terminal states: {len(result['terminal'])}")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
