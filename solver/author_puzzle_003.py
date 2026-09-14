"""Author puzzle 003: "The Long Way Around" (design/08-puzzle-concepts.md #3).

At 7 points, both battlefields are already ours (anchored by a small
guard each, so neither ever goes uncontrolled) — no Conquer is available
here, only Yasuo - Windrider's own card-effect point: "The third time I
move in a turn, you score 1 point." That's unrestricted by the Final
Point rule (rule 473 — it isn't a Conquer), so it wins outright the
instant it fires.

A Standard Move always exhausts its unit (rule 145.1), so Yasuo can't
just move three times in a row — Ganking lets him hop battlefield-to-
battlefield directly, but readying is a separate problem. The line: a
Standard Move (1st), Ride The Wind to move him back AND ready him in the
same action (2nd), then a second Standard Move (3rd) — which fires the
point.

Run with: python -m solver.author_puzzle_003
"""

from __future__ import annotations

import json
from pathlib import Path

from .engine.abilities import RIDE_THE_WIND, YASUO_WINDRIDER
from .engine.card_pool import CARD_POOL
from .engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from .export import export_puzzle

RIDE_THE_WIND_CARD = CARD_POOL[RIDE_THE_WIND]

OUTPUT_PATH = Path(__file__).parent.parent / "puzzles" / "puzzle-003-the-long-way-around.json"



def build_root() -> GameState:
    yasuo = UnitInstance(
        card_id=YASUO_WINDRIDER, instance_id=1, controller=0, might=4,
        keywords=frozenset({"Ganking"}), exhausted=False, damage=0, is_token=False,
    )
    anchor_left = UnitInstance(
        card_id="ogn-010-298",  # Legion Rearguard, 2 might (real Origins printing)
        instance_id=2, controller=0, might=1, keywords=frozenset(),
        exhausted=True, damage=0, is_token=False,
    )
    anchor_right = UnitInstance(
        card_id="ogn-211-298",  # Faithful Manufactor, 2 might (real Origins printing)
        instance_id=3, controller=0, might=1, keywords=frozenset(),
        exhausted=True, damage=0, is_token=False,
    )
    return GameState(
        turn_player=0,
        players=(
            PlayerState(
                base_units=frozenset(),
                hand=(RIDE_THE_WIND,),
                runes=RunePool(available=("Fury", "Fury", "Chaos")),
                score=7,
            ),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, frozenset({yasuo, anchor_left}), None),
            BattlefieldState("right", 0, frozenset({anchor_right}), None),
        ),
        scored_this_turn=frozenset({"left", "right"}),  # both already Held this turn
        cards_played_this_turn=0,
    )


def main() -> None:
    root = build_root()
    cards = {RIDE_THE_WIND: RIDE_THE_WIND_CARD}
    result = export_puzzle("puzzle-003-the-long-way-around", root, cards, max_solver_depth=6)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"Solution: {len(result['solution'])} states")
    print(f"Nodes: {len(result['nodes'])}, terminal states: {len(result['terminal'])}")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
