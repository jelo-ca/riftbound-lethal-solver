"""Author puzzle 008: "No Way Back" (surfaced by the generation pipeline
as `generated-01910` — the first candidate whose solution is impossible
without showdowns).

At 6 points, "left" is already ours, held by Yasuo - Rider of the Wind
([Ganking]; "the third time I move in a turn, you score 1 point"). But
"left" is Vilemaw's Lair: units can't move from there to base. "right"
belongs to the opponent and is guarded by a Might-5 body that kills
Yasuo (Might 2) outright. `scored_this_turn` already contains "right",
so re-taking it would score nothing even if we could.

The trap: the only point left to take is a re-conquer of "left", which
means Yasuo has to leave and come back. Vilemaw's Lair denies the
obvious exit (left -> base), so his single legal exit is [Ganking]ing
left -> right — straight into a fight he loses.

The line spends that suicidal attack as a *move*, not as combat:

  1. Yasuo attacks "right", opening a showdown (move 1). "left" is now
     uncontrolled.
  2. Ride The Wind, an [Action] spell and so legal inside the showdown
     window, pulls him out to base mid-combat (move 2). This is the
     whole puzzle: the showdown is entered purely to be abandoned.
  3. The showdown resolves with no attacker present. The defender is
     untouched and keeps "right".
  4. Yasuo walks base -> "left" (move 3). Conquering "left" scores the
     7th point, and the move is his third this turn, so his own trigger
     scores the 8th.

Ride The Wind is also what makes the exit survivable *and* supplies the
middle move of the three; there is no spare move anywhere else on the
board. Rearguard and the second Yasuo in base are live decoys — both
can move, neither reaches 8.

Distinct from puzzle 3 (Yasuo's move counter, but reached by three plain
Standard Moves) and puzzle 7 (a deep chain that never needs the showdown
window): this is the first puzzle where combat is used as an escape
hatch rather than to kill anything, and it cannot be expressed at all if
combat resolves atomically.

Run with: python -m solver.author_puzzle_008
"""

from __future__ import annotations

import json
from pathlib import Path

from .engine.abilities import RIDE_THE_WIND, YASUO_WINDRIDER
from .engine.battlefields import VILEMAWS_LAIR
from .engine.card_pool import CARD_POOL, LEGION_REARGUARD
from .engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance

from .export import export_puzzle

OUTPUT_PATH = Path(__file__).parent.parent / "puzzles" / "puzzle-008-no-way-back.json"


def build_root() -> GameState:
    stranded_yasuo = UnitInstance(
        card_id=YASUO_WINDRIDER, instance_id=1, controller=0, might=2,
        keywords=frozenset({"Ganking"}), exhausted=False, damage=0, is_token=False,
    )
    rearguard = UnitInstance(
        card_id=LEGION_REARGUARD, instance_id=3, controller=0, might=2,
        keywords=frozenset(), exhausted=False, damage=0, is_token=False,
    )
    spare_yasuo = UnitInstance(
        card_id=YASUO_WINDRIDER, instance_id=4, controller=0, might=2,
        keywords=frozenset({"Ganking"}), exhausted=False, damage=0, is_token=False,
    )
    guard = UnitInstance(
        card_id="generic-opponent", instance_id=2, controller=1, might=5,
        keywords=frozenset(), exhausted=False, damage=0, is_token=False,
    )
    return GameState(
        turn_player=0,
        players=(
            PlayerState(
                base_units=frozenset({rearguard, spare_yasuo}),
                hand=(RIDE_THE_WIND,),
                # Exactly Ride The Wind's cost (2 energy + 1 Chaos power):
                # no rune is spare, so the spell can only be cast once.
                runes=RunePool(available=("Chaos", "Fury", "Fury")),
                score=6,
            ),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, frozenset({stranded_yasuo}), VILEMAWS_LAIR),
            BattlefieldState("right", 1, frozenset({guard}), None),
        ),
        # "right" is spent: re-taking it this turn scores nothing, so the
        # only live point is a re-conquer of "left".
        scored_this_turn=frozenset({"right"}),
        cards_played_this_turn=0,
    )


def main() -> None:
    root = build_root()
    cards = {cid: CARD_POOL[cid] for cid in (RIDE_THE_WIND, YASUO_WINDRIDER, LEGION_REARGUARD)}
    result = export_puzzle("puzzle-008-no-way-back", root, cards)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"Solution: {len(result['solution'])} states")
    print(f"Nodes: {len(result['nodes'])}, terminal states: {len(result['terminal'])}")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
