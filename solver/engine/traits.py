"""Trait resolution and effective Might. See findings.md's "Trait system"
section for the design history.

Rule that drives this module: an UNCONDITIONAL Might change is just
Might (`UnitInstance.might` — a "+7 Might this turn" spell raises it
directly, no separate bonus field). A CIRCUMSTANTIAL one — depends on
attacking vs defending, on standing at a particular battlefield, on
another unit being alive and co-located — is a trait, resolved fresh
every time `effective_might` is called.

Non-circularity invariant: trait grants (printed, battlefield-positional,
aura) are computed purely from board state — controller, zone occupancy,
card identity — and NEVER from Might. `effective_might` resolves the
trait set once, then sums deltas from it; nothing in that sum feeds back
into which traits are granted. (Fiora, Victorious's own "while I'm
Mighty (5+ Might), I have Deflect/Ganking/Shield" would violate this if
she also picked up Shield's own Might bonus and that tipped her over the
threshold — a real edge case, but Fiora isn't wired yet, only Taric.)

Trait strings are the printed grammar: `Name` or `Name N` (`assault 2`,
`shield 3`, `deflect 2` are real printed traits, not an invented
convention — see findings.md's keyword-vocabulary cache scan).
"""

from __future__ import annotations

import dataclasses
from typing import Literal, Optional

from . import battlefields
from .state import GameState, UnitInstance

Zone = str  # "base" or a battlefield_id


@dataclasses.dataclass(frozen=True)
class TraitDef:
    might_delta: int
    applies_when: Optional[Literal["attacker", "defender"]]


TRAIT_REGISTRY: dict[str, TraitDef] = {
    "Shield": TraitDef(might_delta=1, applies_when="defender"),
    "Assault": TraitDef(might_delta=1, applies_when="attacker"),
    "Tank": TraitDef(might_delta=0, applies_when=None),
    "Ganking": TraitDef(might_delta=0, applies_when=None),
    # Zero Might, like Tank and Ganking — it does its work elsewhere
    # (actions.play_unit_cost / apply_play_unit's exhaustion), at play
    # time rather than on the board. Registered so it parses as a trait
    # rather than falling through as unknown.
    "Accelerate": TraitDef(might_delta=0, applies_when=None),
}

TARIC_PROTECTOR = "ogn-074-298"  # "Other friendly units here have [Shield]."


@dataclasses.dataclass(frozen=True)
class AuraDef:
    """A continuous, positional grant from another co-located unit being
    alive — computed here every call, never stored, so it can't go stale
    when the source dies or either unit moves (see module docstring)."""
    grants: frozenset[str]


AURA_SOURCES: dict[str, AuraDef] = {
    TARIC_PROTECTOR: AuraDef(grants=frozenset({"Shield"})),
}


def parse_trait(trait: str) -> tuple[str, Optional[int]]:
    """`"Shield 2"` -> `("Shield", 2)`; `"Shield"` -> `("Shield", None)` —
    `None` means "use TRAIT_REGISTRY's default for the bare form"."""
    name, _, suffix = trait.rpartition(" ")
    if name and suffix.isdigit():
        return name, int(suffix)
    return trait, None


def _battlefield(state: GameState, zone: Zone):
    return next((bf for bf in state.battlefields if bf.battlefield_id == zone), None)


def resolved_traits(state: GameState, unit: UnitInstance, zone: Zone) -> frozenset[str]:
    """The full trait set for `unit` standing at `zone` right now: printed
    (plus anything a spell/ability has already unioned into
    `unit.keywords` — same mutate-in-place pattern as Might, no separate
    stored field needed) | battlefield-positional | aura. Always call this
    rather than reading `unit.keywords` directly wherever the unit's
    location could matter — reading `unit.keywords` alone is how a
    battlefield granting [Shield] went invisible to damage math before
    this module existed."""
    traits = set(unit.keywords)
    if zone == "base":
        return frozenset(traits)

    bf = _battlefield(state, zone)
    if bf is None:
        return frozenset(traits)

    traits |= battlefields.granted_keywords(bf.effect_id)

    for source_card_id, aura in AURA_SOURCES.items():
        for other in bf.units:
            if (other.card_id == source_card_id and other.controller == unit.controller
                    and other.instance_id != unit.instance_id):
                traits |= aura.grants

    return frozenset(traits)


def effective_might(state: GameState, unit: UnitInstance, zone: Zone,
                     designation: Optional[str] = None) -> int:
    """Might is ONE stat doing two jobs — how much damage the unit deals,
    and how much damage kills it (Lethal Damage is non-zero damage >=
    Might) — so every bonus to it raises BOTH. `designation`
    ("attacker"/"defender") gates traits whose bonus is conditional on
    that role; pass `None` for any non-combat context (a Shield unit
    still dies to non-combat damage equal to its base Might, since it
    isn't defending at that moment).

    Resolution order: traits resolve first (`resolved_traits`), then this
    sums Might off the resolved set — never the reverse (see module
    docstring) — which is what lets a battlefield that both grants
    [Shield] and pays [Shield] units +2 stack correctly."""
    traits = resolved_traits(state, unit, zone)
    bonus = 0

    effect_id = None if zone == "base" else (
        bf.effect_id if (bf := _battlefield(state, zone)) else None
    )
    bonus += battlefields.might_bonus(effect_id)
    by_trait = battlefields.might_bonus_by_trait(effect_id)

    for trait in traits:
        name, amount = parse_trait(trait)
        bonus += by_trait.get(name, 0)
        trait_def = TRAIT_REGISTRY.get(name)
        if trait_def is None:
            continue
        if trait_def.applies_when is not None and trait_def.applies_when != designation:
            continue
        bonus += amount if amount is not None else trait_def.might_delta

    return unit.might + bonus
