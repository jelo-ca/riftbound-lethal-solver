"""Author puzzle 007: "Snipe and Trade" (surfaced by the generation
pipeline, `generated-00278`/`generated-00869` — two numerically-different
twins of the same maneuver; this is 00278's numbers).

At 6 points, "right" is already ours (Sneaky Deckhand holding it) but
"left" is blocked by a tough Might-5 defender. Our base holds Caitlyn -
Patrolling (Might 3, ranged damage), Vanguard Captain (Might 3, vanilla),
and a second Sneaky Deckhand (Might 2).

Attacking the Might-5 blocker head-on with anything in hand loses the
attacker for nothing (3 or 2 Might both die without killing it). The real
line: retreat the Sneaky Deckhand off "right" back to Base, freeing the
battlefield; Ride The Wind moves Caitlyn onto "right" (readied, not
exhausted, and claims it — Scores the Final Point's first half). Now
planted at a battlefield, Caitlyn's ability snipes the Might-5 blocker for
3 damage from across the board — no retaliation, since it isn't combat.
The spare Sneaky Deckhand (Might 2) then attacks the weakened blocker (3
damage already + 2 more = lethal): a genuine trade, both die, but "left"
is cleared. Vanguard Captain (Might 3, untouched all game) walks into the
now-empty "left" uncontested for the second half of the Final Point.

Distinct from puzzles 5/6 (which each use one mechanic in isolation):
this chains retreat -> spell-redeploy -> ranged snipe -> a real combat
trade -> walk-in, the deepest combo yet.

Run with: python -m solver.author_puzzle_007
"""

from __future__ import annotations

import json
from pathlib import Path

from .engine.abilities import CAITLYN_PATROLLING, RIDE_THE_WIND
from .engine.cards import CardDef
from .engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from .export import export_puzzle

OUTPUT_PATH = Path(__file__).parent.parent / "puzzles" / "puzzle-007-snipe-and-trade.json"

RIDE_THE_WIND_CARD = CardDef(
    card_id=RIDE_THE_WIND, card_type="Spell", energy_cost=2, power_cost=1,
    power_domain="Chaos", keywords=frozenset(),
)


def build_root() -> GameState:
    caitlyn = UnitInstance(
        card_id=CAITLYN_PATROLLING, instance_id=3, controller=0, might=3,
        keywords=frozenset(), exhausted=False, damage=0, is_token=False,
    )
    vanguard_captain = UnitInstance(
        card_id="ogn-218-298",  # Vanguard Captain, 3 might (real Origins printing)
        instance_id=4, controller=0, might=3, keywords=frozenset(),
        exhausted=False, damage=0, is_token=False,
    )
    spare_deckhand = UnitInstance(
        card_id="ogn-176-298",  # Sneaky Deckhand, 2 might (real Origins printing)
        instance_id=5, controller=0, might=2, keywords=frozenset(),
        exhausted=False, damage=0, is_token=False,
    )
    holding_deckhand = UnitInstance(
        card_id="ogn-176-298", instance_id=2, controller=0, might=2,
        keywords=frozenset(), exhausted=False, damage=0, is_token=False,
    )
    blocker = UnitInstance(
        card_id="generic-opponent", instance_id=1, controller=1, might=5,
        keywords=frozenset(), exhausted=False, damage=0, is_token=False,
    )
    return GameState(
        turn_player=0,
        players=(
            PlayerState(
                base_units=frozenset({caitlyn, vanguard_captain, spare_deckhand}),
                hand=(RIDE_THE_WIND, RIDE_THE_WIND),
                runes=RunePool(available=("Chaos", "Chaos", "Fury", "Fury", "Fury", "Fury")),
                score=6,
            ),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 1, frozenset({blocker}), None),
            BattlefieldState("right", 0, frozenset({holding_deckhand}), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def main() -> None:
    root = build_root()
    cards = {RIDE_THE_WIND: RIDE_THE_WIND_CARD}
    result = export_puzzle("puzzle-007-snipe-and-trade", root, cards)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"Solution: {len(result['solution'])} states")
    print(f"Nodes: {len(result['nodes'])}, terminal states: {len(result['terminal'])}")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
