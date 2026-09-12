"""Author puzzle 004: "Extra Innings" (design/08-puzzle-concepts.md #4).

At 7 points, a unit already conquered "left" this turn and is now
exhausted — normally stuck, since a Standard Move requires the unit not
be exhausted. Ride The Wind moves it to "right" (open) AND readies it in
the same action, establishing control there too. Since "left" stays in
scored_this_turn even after losing control (rule 471.1.b, validated by
puzzle 2), this Scores both battlefields this turn and wins the Final
Point — the "hidden extra action" trick, in one move.

Run with: python -m solver.author_puzzle_004
"""

from __future__ import annotations

import json
from pathlib import Path

from .engine.abilities import RIDE_THE_WIND
from .engine.cards import CardDef
from .engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from .export import export_puzzle

OUTPUT_PATH = Path(__file__).parent.parent / "puzzles" / "puzzle-004-extra-innings.json"

RIDE_THE_WIND_CARD = CardDef(
    card_id=RIDE_THE_WIND, card_type="Spell", energy_cost=2, power_cost=1,
    power_domain="Chaos", keywords=frozenset(),
)


def build_root() -> GameState:
    exhausted_conqueror = UnitInstance(
        card_id="ogn-010-298",  # Legion Rearguard, 2 might (real Origins printing)
        instance_id=1, controller=0, might=2, keywords=frozenset(),
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
            BattlefieldState("left", 0, frozenset({exhausted_conqueror}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset({"left"}),  # Conquered earlier this turn, already exhausted from it
        cards_played_this_turn=0,
    )


def main() -> None:
    root = build_root()
    cards = {RIDE_THE_WIND: RIDE_THE_WIND_CARD}
    result = export_puzzle("puzzle-004-extra-innings", root, cards)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"Solution: {len(result['solution'])} states")
    print(f"Nodes: {len(result['nodes'])}, terminal states: {len(result['terminal'])}")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
