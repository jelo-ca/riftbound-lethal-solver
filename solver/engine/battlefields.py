"""Per-battlefield effect registry — the `BattlefieldState.effect_id`
field has existed in the state model since the start but nothing was
ever wired to it. Same "add mechanics on demand" policy as abilities.py
(design/07-scope-and-cut-list.md): one battlefield at a time, only the
ones a puzzle actually needs.

Deliberately limited to STATIC effects — ones that modify a unit's
combat math or movement legality purely by virtue of the unit being
physically at that battlefield. Battlefields whose text is a TRIGGER
("when you conquer here...", "when you defend here...") need a whole
trigger-timing hook that doesn't exist yet and stay out of scope until
one is actually needed.

This module deliberately imports nothing from combat.py/actions.py —
both of those import THIS, so keeping the dependency one-directional
avoids a cycle.
"""

from __future__ import annotations

from typing import Optional

WINDSWEPT_HILLOCK = "ogn-297-298"  # "Units here have [Ganking]."
TRIFARIAN_WAR_CAMP = "ogn-294-298"  # "Units here have +1 Might. (This includes attackers.)"
VILEMAWS_LAIR = "ogn-295-298"  # "Units can't move from here to base."

# effect_id -> keywords granted to any unit physically at this battlefield.
GRANTED_KEYWORDS: dict[str, frozenset[str]] = {
    WINDSWEPT_HILLOCK: frozenset({"Ganking"}),
}

# effect_id -> flat Might bonus for any unit physically at this
# battlefield. Applies to attackers moving in too, per the card's own
# parenthetical — combat resolves AT the destination, so everyone
# involved counts as "here".
MIGHT_BONUS: dict[str, int] = {
    TRIFARIAN_WAR_CAMP: 1,
}

# effect_ids that forbid a unit moving from this battlefield back to Base.
# Applied to spell/ability-granted moves as well as a unit's own Standard
# Move: the text is a flat restriction on movement, not one scoped to a
# particular way of moving.
NO_MOVE_TO_BASE: frozenset[str] = frozenset({VILEMAWS_LAIR})

REGISTERED: frozenset[str] = frozenset(GRANTED_KEYWORDS) | frozenset(MIGHT_BONUS) | NO_MOVE_TO_BASE


def granted_keywords(effect_id: Optional[str]) -> frozenset[str]:
    if effect_id is None:
        return frozenset()
    return GRANTED_KEYWORDS.get(effect_id, frozenset())


def might_bonus(effect_id: Optional[str]) -> int:
    if effect_id is None:
        return 0
    return MIGHT_BONUS.get(effect_id, 0)


def blocks_move_to_base(effect_id: Optional[str]) -> bool:
    return effect_id is not None and effect_id in NO_MOVE_TO_BASE
