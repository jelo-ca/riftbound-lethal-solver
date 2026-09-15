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
one is actually needed (e.g. Fortified Position's "When you defend
here, choose a unit. It gains [Shield 2] this combat.").

This module deliberately imports nothing from combat.py/actions.py/
traits.py — all three import THIS, so keeping the dependency one-
directional avoids a cycle.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

WINDSWEPT_HILLOCK = "ogn-297-298"  # "Units here have [Ganking]."
TRIFARIAN_WAR_CAMP = "ogn-294-298"  # "Units here have +1 Might. (This includes attackers.)"
VILEMAWS_LAIR = "ogn-295-298"  # "Units can't move from here to base."


@dataclasses.dataclass(frozen=True)
class BattlefieldEffect:
    """One record per static battlefield effect, replacing the three
    parallel dicts (`GRANTED_KEYWORDS`/`MIGHT_BONUS`/`NO_MOVE_TO_BASE`)
    the first version of this module used. `might_bonus_by_trait` exists
    for text shaped like "Shield units get +2 here" — a flat int alone
    can't express a bonus conditional on which trait a unit already has."""
    grants: frozenset[str] = frozenset()
    flat_might_bonus: int = 0
    might_bonus_by_trait: dict[str, int] = dataclasses.field(default_factory=dict)
    blocks_move_to_base: bool = False


BATTLEFIELD_EFFECTS: dict[str, BattlefieldEffect] = {
    WINDSWEPT_HILLOCK: BattlefieldEffect(grants=frozenset({"Ganking"})),
    TRIFARIAN_WAR_CAMP: BattlefieldEffect(flat_might_bonus=1),
    VILEMAWS_LAIR: BattlefieldEffect(blocks_move_to_base=True),
}

REGISTERED: frozenset[str] = frozenset(BATTLEFIELD_EFFECTS)


def _effect(effect_id: Optional[str]) -> Optional[BattlefieldEffect]:
    if effect_id is None:
        return None
    return BATTLEFIELD_EFFECTS.get(effect_id)


def granted_keywords(effect_id: Optional[str]) -> frozenset[str]:
    effect = _effect(effect_id)
    return effect.grants if effect else frozenset()


def might_bonus(effect_id: Optional[str]) -> int:
    effect = _effect(effect_id)
    return effect.flat_might_bonus if effect else 0


def might_bonus_by_trait(effect_id: Optional[str]) -> dict[str, int]:
    effect = _effect(effect_id)
    return effect.might_bonus_by_trait if effect else {}


def blocks_move_to_base(effect_id: Optional[str]) -> bool:
    effect = _effect(effect_id)
    return effect.blocks_move_to_base if effect else False
