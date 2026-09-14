"""Author puzzle 007: "Feint" — a fight entered only to be abandoned.

Surfaced by the generation pipeline as `generated-21128`, then reframed
by hand. The generator's board put Yasuo safely in base with "left"
empty and neutral, so the walk-in Conquered for the 7th point and the
move trigger paid the 8th. This version strands him instead, and makes
the Conquer worth nothing.

At 7 points. "left" is ours, held since the start of the turn — which is
exactly why it is already in `scored_this_turn`: Hold scored it during
the Beginning Phase and took us to 7 (the Hold invariant, see
scoring.unseeded_holds). Re-taking it this turn is worth zero. It also
sits under Vilemaw's Lair ("units can't move from here to base"), and
Yasuo - Rider of the Wind ([Ganking]; "the third time I move in a turn,
you score 1 point") is standing on it. "right" belongs to the opponent,
guarded by a Might-5 body that beats Yasuo's Might 4 — he cannot kill
it and it kills him.

So there is no battlefield left to score. The only point available
anywhere is Yasuo's trigger, and it needs three moves.

Vilemaw's Lair denies the obvious way to run the counter — walk off to
base and back — and its restriction binds spell-granted moves too, not
just Standard Moves, so Ride The Wind cannot pull him off "left" either.
His one legal exit is [Ganking] into "right", straight into a fight he
loses.

The line spends that suicidal attack as a move rather than as combat:

  1. Yasuo attacks "right", opening a showdown (move 1). "left" is now
     Uncontrolled behind him.
  2. Ride The Wind, an [Action] spell and so legal inside the showdown
     window, pulls him out to base before damage (move 2).
  3. The showdown resolves with no attacker present. The guard takes
     nothing and keeps "right".

     (The guard has to out-Might Yasuo rather than merely match him. At
     equal Might the attack becomes a mutual kill, "right" empties, and
     any spare body walks in to Conquer it — a duller three-step line
     that skips the feint entirely. That is exactly what happened when
     Yasuo's stats were corrected from a mis-transcribed Might 2 to his
     printed Might 4.)
  4. Yasuo walks base -> "left" (move 3). The Conquer scores nothing —
     "left" was Scored this turn already — but the move is his third,
     and the trigger is a card-effect point, which rule 473 exempts from
     the Final Point restriction. 8 points.

The fight deals no damage, takes no ground, and gains no tempo. It
exists only to spend a move that Vilemaw's Lair would otherwise deny.
Remove that one battlefield effect and the whole thing collapses into
puzzle 3's three-step line.

Ride The Wind is affordable exactly once and is both the escape and the
middle move, so there is no spare tempo anywhere. The Legion Rearguard
in base is a decoy: it can move, it just cannot score.

Run with: python -m solver.author_puzzle_007
"""

from __future__ import annotations

import json
from pathlib import Path

from .engine.abilities import RIDE_THE_WIND, YASUO_WINDRIDER
from .engine.battlefields import VILEMAWS_LAIR
from .engine.card_pool import CARD_POOL, LEGION_REARGUARD
from .engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from .export import export_puzzle

OUTPUT_PATH = Path(__file__).parent.parent / "puzzles" / "puzzle-007-feint.json"


def build_root() -> GameState:
    stranded_yasuo = UnitInstance(
        card_id=YASUO_WINDRIDER, instance_id=1, controller=0, might=4,
        keywords=frozenset({"Ganking"}), exhausted=False, damage=0, is_token=False,
    )
    guard = UnitInstance(
        card_id="generic-opponent", instance_id=2, controller=1, might=5,
        keywords=frozenset(), exhausted=False, damage=0, is_token=False,
    )
    decoy = UnitInstance(
        card_id=LEGION_REARGUARD, instance_id=3, controller=0, might=2,
        keywords=frozenset(), exhausted=False, damage=0, is_token=False,
    )
    return GameState(
        turn_player=0,
        players=(
            PlayerState(
                base_units=frozenset({decoy}),
                hand=(RIDE_THE_WIND,),
                # Exactly Ride The Wind's cost (2 energy + 1 Chaos power),
                # so the escape can only be bought once.
                runes=RunePool(available=("Chaos", "Fury", "Fury")),
                score=7,
            ),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            # Vilemaw's Lair is the whole puzzle: it blocks left -> base for
            # spell-granted moves as well as Standard Moves, so Yasuo cannot
            # run his counter on his own battlefield the way puzzle 3 does.
            BattlefieldState("left", 0, frozenset({stranded_yasuo}), VILEMAWS_LAIR),
            BattlefieldState("right", 1, frozenset({guard}), None),
        ),
        # We hold "left", so Hold already Scored it this turn and took us
        # to 7 — re-Conquering it is worth nothing. Seeding this is not a
        # formality; without it the position admits a re-Conquer of ground
        # we never lost, which is what got the first puzzles 7 and 8
        # withdrawn (see scoring.unseeded_holds).
        scored_this_turn=frozenset({"left"}),
        cards_played_this_turn=0,
    )


def main() -> None:
    root = build_root()
    cards = {cid: CARD_POOL[cid] for cid in (RIDE_THE_WIND, YASUO_WINDRIDER, LEGION_REARGUARD)}
    result = export_puzzle("puzzle-007-feint", root, cards)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"Solution: {len(result['solution'])} states")
    print(f"Nodes: {len(result['nodes'])}, terminal states: {len(result['terminal'])}")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
