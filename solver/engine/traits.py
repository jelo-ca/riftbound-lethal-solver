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
    # Also zero Might, and also play-time: it gates whether a card's own
    # printed effect happens at all (abilities.legion_condition_met).
    "Legion": TraitDef(might_delta=0, applies_when=None),
    # Zero Might too — it taxes the OPPONENT's targeting instead. The
    # numeric form ("Deflect 2") scales the tax, not any Might. See
    # deflect_tax.
    "Deflect": TraitDef(might_delta=0, applies_when=None),
    # Fires on death rather than affecting the board while alive — see
    # engine/deaths.py.
    "Deathknell": TraitDef(might_delta=0, applies_when=None),
    # Registered, and deliberately inert: "Kill me at the start of your
    # Beginning Phase, before scoring" — a single-turn puzzle never
    # reaches a next Beginning Phase, so nothing can ever observe it.
    # Here so it parses as a known trait instead of falling through.
    "Temporary": TraitDef(might_delta=0, applies_when=None),
}

TARIC_PROTECTOR = "ogn-074-298"  # "Other friendly units here have [Shield]."
CAPTAIN_FARRON = "ogn-015-298"  # "Other friendly units here have [Assault]."


@dataclasses.dataclass(frozen=True)
class AuraDef:
    """A continuous, positional grant from another co-located unit being
    alive — computed here every call, never stored, so it can't go stale
    when the source dies or either unit moves (see module docstring)."""
    grants: frozenset[str]


@dataclasses.dataclass(frozen=True)
class SelfConditional:
    """Text of the form "while <condition>, I have <something>" — a card
    granting itself traits or Might only while some fact about it holds.

    THE CONDITION MAY NOT READ MIGHT. The module's non-circularity
    invariant is that grants are computed from board state and never from
    Might, because Might is computed FROM the resolved grants. A condition
    like "while I'm buffed" is fine — `buffed` is plain state. Fiora,
    Victorious's "while I'm [Mighty]" (5+ Might) is exactly the case that
    isn't, since Shield could push her over her own threshold, and she
    stays unmodelled for that reason rather than by oversight.

    `designation` is the unit's current combat role ("attacker" /
    "defender" / None) — threaded through from wherever effective_might
    already carries it (RULES ANSWER, project owner, 2026-09-17: needed
    to express "while I'm attacking or defending alone"). A condition
    that doesn't care about role simply ignores the parameter, so every
    pre-existing entry stays correct unchanged.
    """
    condition: "object"  # (state, unit, zone, designation) -> bool
    grants: frozenset[str] = frozenset()
    might_delta: int = 0


WIZENED_ELDER = "ogn-065-298"  # "While I'm buffed, I have an additional +1 Might."
BILGEWATER_BULLY = "ogn-125-298"  # "While I'm buffed, I have [Ganking]."
WIELDER_OF_WATER = "ogn-055-298"  # "While I'm attacking or defending alone, I have +2 Might."


def _is_buffed(state: GameState, unit: UnitInstance, zone: Zone, designation: Optional[str] = None) -> bool:
    return unit.buffed


def _attacking_or_defending_alone(state: GameState, unit: UnitInstance, zone: Zone,
                                   designation: Optional[str] = None) -> bool:
    """"While I'm attacking or defending alone." "Alone" means the unit is
    the only one of its side (attacker or defender) in this combat.

    The ATTACKING side in this engine's action space is always exactly
    one unit — combat.py's module docstring: "our action space only ever
    moves a single unit per action," and a destination can't already hold
    any of the mover's own units when a Standard Move triggers combat
    (determine_sides requires the defender's units to belong to a single
    OTHER controller). So an attacking Wielder of Water is unconditionally
    alone whenever this engine can put her in combat at all — not an
    assumption, a consequence of a scope note already on record.

    Defending is different: reachable only via an enemy unit redirected
    onto ground we hold (Charm, Blitzcrank), where more than one of our
    units could already be standing there — so it's checked for real,
    same shape as En Garde's "only unit you control there."
    """
    if designation == "attacker":
        return True
    if designation != "defender":
        return False
    bf = _battlefield(state, zone)
    if bf is None:
        return False
    return sum(1 for u in bf.units if u.controller == unit.controller) == 1


SELF_CONDITIONALS: dict[str, SelfConditional] = {
    WIZENED_ELDER: SelfConditional(condition=_is_buffed, might_delta=1),
    BILGEWATER_BULLY: SelfConditional(condition=_is_buffed, grants=frozenset({"Ganking"})),
    WIELDER_OF_WATER: SelfConditional(condition=_attacking_or_defending_alone, might_delta=2),
}


AURA_SOURCES: dict[str, AuraDef] = {
    TARIC_PROTECTOR: AuraDef(grants=frozenset({"Shield"})),
    # Identical shape to Taric, different trait — the whole point of
    # resolving auras from board state rather than storing them is that a
    # second card like this costs one line.
    CAPTAIN_FARRON: AuraDef(grants=frozenset({"Assault"})),
}


LEE_SIN_CENTERED = "ogn-151-298"  # "Other buffed friendly units at my battlefield have +2 Might."
LEE_SIN_CENTERED_ALT = "ogn-151a-298"  # same card, alternate printing

# card_id -> flat Might a co-located, same-controller, OTHER unit gets
# while buffed. Unlike AURA_SOURCES (a trait grant, unconditional on the
# receiver), this is Might and conditional on the RECEIVER's own buffed
# state — the source itself need not be buffed. Kept as its own dict
# rather than folded into AURA_SOURCES/AuraDef since AuraDef's `grants`
# has no room for a per-receiver condition; a second card of this shape
# costs one line here, same as AURA_SOURCES's own comment says for traits.
BUFF_MIGHT_AURA_SOURCES: dict[str, int] = {
    LEE_SIN_CENTERED: 2,
    LEE_SIN_CENTERED_ALT: 2,
}


SETT_KINGPIN = "ogn-240-298"  # "[Tank] I get +1 Might for each buffed friendly unit at my battlefield."
SETT_KINGPIN_ALT = "ogn-240a-298"  # same card, alternate printing

# card_id -> Might gained per buffed friendly unit at the card's own
# battlefield, itself included (the text doesn't say "other"). A COUNT,
# not a threshold, so it doesn't fit SelfConditional's boolean condition
# — the count reads unit.buffed (plain state) on each occupant, never
# Might, so the module's non-circularity invariant still holds.
SELF_COUNT_MIGHT: dict[str, int] = {
    SETT_KINGPIN: 1,
    SETT_KINGPIN_ALT: 1,
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


def resolved_traits(state: GameState, unit: UnitInstance, zone: Zone,
                     designation: Optional[str] = None) -> frozenset[str]:
    """The full trait set for `unit` standing at `zone` right now: printed
    (plus anything a spell/ability has already unioned into
    `unit.keywords` — same mutate-in-place pattern as Might, no separate
    stored field needed) | battlefield-positional | aura. Always call this
    rather than reading `unit.keywords` directly wherever the unit's
    location could matter — reading `unit.keywords` alone is how a
    battlefield granting [Shield] went invisible to damage math before
    this module existed.

    `designation` ("attacker"/"defender"/None) is passed straight through
    to any SelfConditional whose GRANT depends on combat role (e.g. "while
    I'm attacking or defending alone, I have <trait>") — most callers pass
    nothing, which is correct outside combat or where role doesn't apply.
    """
    traits = set(unit.keywords)

    own = SELF_CONDITIONALS.get(unit.card_id)
    if own is not None and own.condition(state, unit, zone, designation):
        traits |= own.grants

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


def deflect_tax(state: GameState, unit: UnitInstance, zone: Zone, chooser: int) -> int:
    """Extra runes `chooser` must Recycle (any domain) to choose `unit`
    with a spell or ability — [Deflect]'s "Opponents must pay ⟨rainbow⟩ to
    choose me," where "Deflect N" charges N.

    Zero when `chooser` controls the unit: the tax is on OPPONENTS, so
    targeting your own units is always free. In these puzzles the
    opponent never acts, which means this only ever bites in one
    direction — us paying to touch an enemy unit.

    Resolved through resolved_traits rather than unit.keywords so a
    granted or aura-granted Deflect would count too (Fiora, Victorious
    grants herself Deflect while Mighty — not wired, but the resolver is
    the right source regardless).
    """
    if unit.controller == chooser:
        return 0
    tax = 0
    for trait in resolved_traits(state, unit, zone):
        name, amount = parse_trait(trait)
        if name == "Deflect":
            tax += amount if amount is not None else 1
    return tax


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
    traits = resolved_traits(state, unit, zone, designation)
    # A buff is a flat, unconditional +1 — it doesn't care about attacking
    # or defending, so it lands here rather than in TRAIT_REGISTRY, whose
    # entries are all designation-gated or zero.
    bonus = 1 if unit.buffed else 0

    own = SELF_CONDITIONALS.get(unit.card_id)
    if own is not None and own.condition(state, unit, zone, designation):
        bonus += own.might_delta

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

    if zone != "base":
        bf = _battlefield(state, zone)
        if bf is not None:
            if unit.buffed:
                for other in bf.units:
                    if (other.controller == unit.controller and other.instance_id != unit.instance_id
                            and other.card_id in BUFF_MIGHT_AURA_SOURCES):
                        bonus += BUFF_MIGHT_AURA_SOURCES[other.card_id]

            per_buffed = SELF_COUNT_MIGHT.get(unit.card_id)
            if per_buffed is not None:
                buffed_here = sum(1 for u in bf.units if u.controller == unit.controller and u.buffed)
                bonus += per_buffed * buffed_here

    return unit.might + bonus
