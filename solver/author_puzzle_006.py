"""Author puzzle 006: "Redirection" (design/08-puzzle-concepts.md #6).

RE-AUTHORED after [Tank] was implemented. The original version's
adversarial fork — the opponent choosing whether to kill our fragile unit
or Blitzcrank — was never legal Riftbound: Blitzcrank prints [Tank], so
that choice never existed. It only appeared because combat.py ignored the
keyword. Rather than withdraw the puzzle, this version makes Tank the
load-bearing piece instead of an accident.

At 7 points we hold "right" (Scored via Hold this turn), where our only
mobile unit stands — a 2-Might Legion Rearguard, which "right" being
Windswept Hillock grants [Ganking], so it alone can hop straight to
"left". The opponent's single blocker sits on "left", the battlefield we
still need.

The line: play Blitzcrank - Impassive to "right" and use his "when you
play me, you may move an enemy unit to here" trigger to drag the blocker
off "left" entirely. That leaves "left" empty and uncontrolled, and the
Rearguard walks in for the Conquer and the Final Point.

Why it needs Tank. Dragging the blocker onto "right" starts a combat with
US as Defender (design/09-combat-resolution.md's "we are not always the
Attacker"). The blocker's 3 damage would comfortably kill the 2-Might
Rearguard — and the Rearguard is the only unit that can reach "left",
since Blitzcrank enters exhausted the turn he is played and cannot move.
Tank forces that damage onto Blitzcrank instead, who at 5 Might shrugs
off 3. Strip Tank and the same line kills our own conqueror; the puzzle
is exactly the margin the keyword provides, which
test_puzzle_006.py asserts directly.

Run with: python -m solver.author_puzzle_006
"""

from __future__ import annotations

import json
from pathlib import Path

from .engine.abilities import BLITZCRANK_IMPASSIVE
from .engine.battlefields import WINDSWEPT_HILLOCK
from .engine.card_pool import CARD_POOL
from .engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from .export import export_puzzle

BLITZCRANK_CARD = CARD_POOL[BLITZCRANK_IMPASSIVE]

OUTPUT_PATH = Path(__file__).parent.parent / "puzzles" / "puzzle-006-redirection.json"



def build_root() -> GameState:
    # Our only mobile unit, and deliberately fragile: 2 Might dies to the
    # blocker's 3 damage, which is the whole tension Tank resolves. It
    # gets [Ganking] from Windswept Hillock underneath it, so it can go
    # "right" -> "left" directly (rule 810).
    conqueror = UnitInstance(
        card_id="ogn-010-298",  # Legion Rearguard, 2 might (real Origins printing)
        instance_id=1, controller=0, might=2, keywords=frozenset(),
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
                base_units=frozenset(),
                hand=(BLITZCRANK_IMPASSIVE,),
                # Blitzcrank costs 5 Energy + 1 Calm Power. Energy is
                # domain-agnostic, the Power rune is not — five Fury runes
                # paid for him only while his printed Power cost was
                # mis-transcribed as 0.
                runes=RunePool(available=("Fury", "Fury", "Fury", "Fury", "Fury", "Calm")),
                score=7,
            ),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 1, frozenset({blocker}), None),
            # Windswept Hillock: "Units here have [Ganking]" — what lets the
            # Rearguard reach "left" in one hop once it is emptied.
            BattlefieldState("right", 0, frozenset({conqueror}), WINDSWEPT_HILLOCK),
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
