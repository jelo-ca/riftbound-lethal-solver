"""Author puzzle 007: "Feint" (surfaced by the generation
pipeline as `generated-21128` — the first candidate whose solution needs
the showdown window and is legal under the Hold invariant).

At 6 points with nothing scored yet. "left" is empty and Uncontrolled,
sitting under Vilemaw's Lair ("units can't move from here to base").
"right" belongs to the opponent, guarded by a Might-4 body. Our base
holds Yasuo - Rider of the Wind ([Ganking]; "the third time I move in a
turn, you score 1 point"), plus two spare bodies, and the hand is a
single Ride The Wind.

Two points are needed and only one battlefield is takeable, so the
second has to come from Yasuo's move counter — he needs three moves.

The obvious route is the one puzzle 3 uses: walk into "left" (move 1),
Ride The Wind back to base (move 2), walk in again (move 3). Vilemaw's
Lair denies it. Its restriction binds spell-granted moves too, not just
Standard Moves, so once Yasuo is standing on "left" Ride The Wind cannot
pull him off it. That line strands him one move short.

So the counter has to be run somewhere else, and "right" is the only
other board there is — guarded by a body that beats him:

  1. Yasuo attacks "right", opening a showdown (move 1).
  2. Ride The Wind, an [Action] spell and so legal inside the window,
     pulls him out to base before damage (move 2).
  3. The showdown resolves with no attacker present. The guard is
     untouched and keeps "right".
  4. Yasuo walks base -> "left" (move 3). Conquering the empty
     battlefield scores the 7th point, and the move is his third this
     turn, so his own trigger scores the 8th.

The fight is entered purely to be abandoned: it deals no damage, takes
no ground, and exists only to spend a move Vilemaw's Lair would
otherwise deny. Remove that one battlefield effect and the puzzle
collapses to puzzle 3's three-step line.

Ride The Wind is single-use here (the runes pay for it exactly once) and
is both the escape and the middle move, so there is no spare tempo
anywhere. The Faithful Manufactor and Vanguard Captain in base are
decoys — each can move, neither reaches 8.

Run with: python -m solver.author_puzzle_007
"""

from __future__ import annotations

import json
from pathlib import Path

from .engine.abilities import RIDE_THE_WIND, YASUO_WINDRIDER
from .engine.battlefields import VILEMAWS_LAIR
from .engine.card_pool import CARD_POOL, FAITHFUL_MANUFACTOR, VANGUARD_CAPTAIN
from .engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from .export import export_puzzle

OUTPUT_PATH = Path(__file__).parent.parent / "puzzles" / "puzzle-007-feint.json"


def build_root() -> GameState:
    manufactor = UnitInstance(
        card_id=FAITHFUL_MANUFACTOR, instance_id=2, controller=0, might=2,
        keywords=frozenset(), exhausted=False, damage=0, is_token=False,
    )
    captain = UnitInstance(
        card_id=VANGUARD_CAPTAIN, instance_id=3, controller=0, might=3,
        keywords=frozenset(), exhausted=False, damage=0, is_token=False,
    )
    yasuo = UnitInstance(
        card_id=YASUO_WINDRIDER, instance_id=4, controller=0, might=2,
        keywords=frozenset({"Ganking"}), exhausted=False, damage=0, is_token=False,
    )
    guard = UnitInstance(
        card_id="generic-opponent", instance_id=1, controller=1, might=4,
        keywords=frozenset(), exhausted=False, damage=0, is_token=False,
    )
    return GameState(
        turn_player=0,
        players=(
            PlayerState(
                base_units=frozenset({manufactor, captain, yasuo}),
                hand=(RIDE_THE_WIND,),
                # Exactly Ride The Wind's cost (2 energy + 1 Chaos power),
                # so the escape can only be bought once.
                runes=RunePool(available=("Chaos", "Fury", "Fury")),
                score=6,
            ),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            # Vilemaw's Lair is the whole puzzle: it blocks left -> base for
            # spell-granted moves as well as Standard Moves, so Yasuo cannot
            # run his counter on the empty battlefield the way puzzle 3 does.
            BattlefieldState("left", None, frozenset(), VILEMAWS_LAIR),
            BattlefieldState("right", 1, frozenset({guard}), None),
        ),
        # We hold nothing, so nothing is pre-seeded (see the Hold invariant
        # in scoring.unseeded_holds).
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def main() -> None:
    root = build_root()
    cards = {cid: CARD_POOL[cid] for cid in
             (RIDE_THE_WIND, YASUO_WINDRIDER, FAITHFUL_MANUFACTOR, VANGUARD_CAPTAIN)}
    result = export_puzzle("puzzle-007-feint", root, cards)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"Solution: {len(result['solution'])} states")
    print(f"Nodes: {len(result['nodes'])}, terminal states: {len(result['terminal'])}")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
