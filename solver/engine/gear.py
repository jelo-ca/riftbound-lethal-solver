"""Gear: standalone permanents with activated abilities.

WHAT THE CARD TEXT SAYS (derived from all 30 Origins Gear printings —
nothing here is assumed by analogy to units):

  * Gear does not attach. No printing says "attach" or "equip"; every one
    refers to itself as "this" and acts from wherever it sits ("Exhaust:
    Deal 2 to a unit at a battlefield"). A unit dying does nothing to it.
    The PlayGear action used to carry a `target_unit`, which encoded the
    opposite assumption and matched no card in the set.
  * Gear has no Might on any printing, so it never fights, never occupies
    a battlefield, and never contests control.
  * Gear enters READY. Iron Ballista spells out "This enters exhausted",
    which is only worth printing because the default is the opposite —
    the reverse of units (rule 143.4.a).
  * Most Gear pays an Exhaust cost to activate, several with runes on top
    ("1 Energy, Exhaust:", "Chaos rune, Exhaust:"). So Gear needs a real
    exhausted flag, which state.GearInstance carries.
  * Gear is killable and bounceable ("Kill this", "When this leaves the
    board", Pack of Wonders returning "another friendly gear").

Same "add mechanics on demand" policy as abilities.py and deaths.py: a
per-card registry, not a general effect engine.

NOT WIRED INTO ACTION GENERATION. search.legal_actions and
abilities.is_legal_activate_ability would both need edits to emit PlayGear
and to route gear abilities, and both files were owned by other work in
flight. Everything here is complete and tested against directly; wiring is
a small, separate change. Until then no line will ever play Gear, which is
the safe direction — the engine refuses Gear boards via the coverage
ledger rather than mis-solving them.
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Optional

from . import combat
from .actions import (
    ActivateAbility,
    Zone,
    find_gear,
    find_unit_anywhere,
    find_unit_at_any_battlefield,
    payment_is_affordable,
    consume_runes,
    relocate_unit,
    replace_battlefield,
    replace_gear,
)
from .state import Domain, GameState, add_runes, replace_player

IRON_BALLISTA = "ogn-017-298"  # "This enters exhausted. Exhaust: Deal 2 to a unit at a battlefield."
ORB_OF_REGRET = "ogn-090-298"  # "Exhaust: Give a unit -1 Might this turn, to a minimum of 1 Might."
ARENA_BAR = "ogn-124-298"  # "Exhaust: Buff an exhausted friendly unit."
THE_SYREN = "ogn-184-298"  # "1 Energy, Exhaust: Move a friendly unit at a battlefield to your base."

# card_id -> (energy, power, power_domain) charged by the ability ON TOP of
# exhausting the Gear. Absent means the Exhaust is the whole cost.
ABILITY_COSTS: dict[str, tuple[int, int, Optional[Domain]]] = {
    THE_SYREN: (1, 0, None),
}


def ability_cost(card_id: str) -> tuple[int, int, Optional[Domain]]:
    return ABILITY_COSTS.get(card_id, (0, 0, None))


TREASURE_TROVE = "ogn-186-298"  # "When this leaves the board, draw 1 and channel 1 rune exhausted."

# Gear whose OWN printed text reacts to it leaving the board — surfaced by
# actions.kill_gear's introduction, since until it existed nothing could
# ever kill someone else's Gear and this question never came up. No
# generic "on Gear death" hook exists (deaths.py's DEATH_TRIGGERS is
# unit-only); a caller offering "kill a gear" as a candidate MUST exclude
# these card_ids rather than silently drop the reaction — restrictive, not
# permissive, same convention as play_unit_from_trash excluding units with
# their own UNIT_PLAY_TRIGGERS.
#
# Scrapheap ALSO reacts to its own death ("...or killed, draw 1") but is
# NOT here: coverage.INERT_FOR_LETHAL clears its whole card on the
# argument that all three of its triggers are the same no-op draw, so
# whether kill_gear fires that reaction or not can never change the
# answer — nothing is being silently dropped. Treasure Trove stays
# excluded because its reaction additionally needs "channel 1 rune
# exhausted", a real RunePool change out of scope for this pass.
GEAR_DEATH_REACTIONS = frozenset({TREASURE_TROVE})


def _exhaust_source(state: GameState, action: ActivateAbility) -> GameState:
    """Pay the Exhaust, and any runes the ability charges on top."""
    located = find_gear(state, action.source_id)
    assert located is not None
    gear, controller = located
    state = replace_gear(state, controller, gear, dataclasses.replace(gear, exhausted=True))
    if action.rune_payment is not None:
        player = state.players[controller]
        state = replace_player(state, controller, dataclasses.replace(
            player, runes=consume_runes(player.runes, action.rune_payment)))
    return state


def _source_is_usable(state: GameState, action: ActivateAbility) -> bool:
    """Shared gate: the Gear must exist, belong to the acting player, be
    ready, and its rune cost must be both correctly shaped and payable."""
    located = find_gear(state, action.source_id)
    if located is None:
        return False
    gear, controller = located
    if controller != state.turn_player or gear.exhausted:
        return False
    energy, power, domain = ability_cost(gear.card_id)
    payment = action.rune_payment
    if energy == 0 and power == 0:
        return payment is None or not (
            payment.energy_runes or payment.power_runes or payment.rainbow_runes)
    if payment is None:
        return False
    if len(payment.energy_runes) != energy or len(payment.power_runes) != power:
        return False
    if power and any(d != domain for d in payment.power_runes):
        return False
    return payment_is_affordable(state.players[controller].runes, payment)


# --- Iron Ballista: "Exhaust: Deal 2 to a unit at a battlefield." ---


def _ballista_is_legal(state: GameState, action: ActivateAbility) -> bool:
    if len(action.params) != 1 or not _source_is_usable(state, action):
        return False
    # "a unit at a battlefield" — not Base, and not restricted to enemies.
    return find_unit_at_any_battlefield(state, action.params[0]) is not None


def _ballista_effect(state: GameState, action: ActivateAbility) -> GameState:
    state = _exhaust_source(state, action)
    target_id = action.params[0]
    _, battlefield_id = find_unit_at_any_battlefield(state, target_id)
    return combat.deal_damage_to_unit(state, battlefield_id, target_id, 2)


def _ballista_candidates(state: GameState) -> list[tuple]:
    return [(u.instance_id,) for bf in state.battlefields
            for u in sorted(bf.units, key=lambda u: u.instance_id)]


# --- Orb of Regret: "Give a unit -1 Might this turn, to a minimum of 1." ---


def _orb_is_legal(state: GameState, action: ActivateAbility) -> bool:
    if len(action.params) != 1 or not _source_is_usable(state, action):
        return False
    return find_unit_anywhere(state, action.params[0]) is not None


def _orb_effect(state: GameState, action: ActivateAbility) -> GameState:
    state = _exhaust_source(state, action)
    located = find_unit_anywhere(state, action.params[0])
    assert located is not None
    unit, zone = located
    # "to a minimum of 1 Might" — the floor is on the RESULT, so this can
    # never zero a unit out or make it trivially killable.
    weakened = dataclasses.replace(unit, might=max(1, unit.might - 1))
    if zone == "base":
        player = state.players[unit.controller]
        return replace_player(state, unit.controller, dataclasses.replace(
            player, base_units=(player.base_units - {unit}) | {weakened}))
    bf = next(b for b in state.battlefields if b.battlefield_id == zone)
    return replace_battlefield(state, dataclasses.replace(bf, units=(bf.units - {unit}) | {weakened}))


def _orb_candidates(state: GameState) -> list[tuple]:
    """"a unit" — either player's, anywhere."""
    candidates = []
    for player in state.players:
        candidates += [(u.instance_id,) for u in sorted(player.base_units, key=lambda u: u.instance_id)]
    for bf in state.battlefields:
        candidates += [(u.instance_id,) for u in sorted(bf.units, key=lambda u: u.instance_id)]
    return candidates


# --- The Syren: "1 Energy, Exhaust: Move a friendly unit at a battlefield to your base." ---


def _syren_is_legal(state: GameState, action: ActivateAbility) -> bool:
    if len(action.params) != 1 or not _source_is_usable(state, action):
        return False
    located = find_unit_at_any_battlefield(state, action.params[0])
    if located is None:
        return False
    unit, _ = located
    return unit.controller == state.turn_player  # "a FRIENDLY unit"


def _syren_effect(state: GameState, action: ActivateAbility) -> GameState:
    state = _exhaust_source(state, action)
    target_id = action.params[0]
    _, from_zone = find_unit_at_any_battlefield(state, target_id)
    # A card-granted move doesn't exhaust the unit unless it says so, and
    # this one doesn't — so the unit keeps whatever state it had.
    unit, _ = find_unit_at_any_battlefield(state, target_id)
    return relocate_unit(state, target_id, from_zone, "base", exhausted_after=unit.exhausted)


def _syren_candidates(state: GameState) -> list[tuple]:
    return [(u.instance_id,) for bf in state.battlefields
            for u in sorted(bf.units, key=lambda u: u.instance_id)
            if u.controller == state.turn_player]


# card_id -> (is_legal(state, action), effect(state, action), candidates(state))
#
# Deliberately the same triple as abilities.ABILITY_EFFECTS, so wiring this
# in later is a routing change rather than a new shape. Effects are
# deterministic — no Gear here forces a combat or an opponent choice — so
# a single GameState is returned rather than a list.
def _arena_bar_is_legal(state: GameState, action: ActivateAbility) -> bool:
    """"Buff an EXHAUSTED friendly unit" — the exhausted requirement is the
    whole restriction, and it points the card at bodies that have already
    acted this turn."""
    if not _source_is_usable(state, action) or len(action.params) != 1:
        return False
    from .actions import find_unit_anywhere
    located = find_unit_anywhere(state, action.params[0])
    return (located is not None and located[0].controller == state.turn_player
            and located[0].exhausted)


def _arena_bar_effect(state: GameState, action: ActivateAbility) -> GameState:
    from .abilities import apply_buff
    return apply_buff(_exhaust_source(state, action), action.params[0])


def _arena_bar_candidates(state: GameState) -> list[tuple]:
    out = [(u.instance_id,) for u in sorted(state.players[state.turn_player].base_units,
                                             key=lambda u: u.instance_id) if u.exhausted]
    out += [(u.instance_id,) for bf in state.battlefields
            for u in sorted(bf.units, key=lambda u: u.instance_id)
            if u.controller == state.turn_player and u.exhausted]
    return out


# --- Pack of Wonders: "Exhaust: Return another friendly gear, unit, or
# [Hidden] card to its owner's hand." ---
#
# [Hidden] is not modelled as a zone at all (design/00-overview.md: "no
# hidden zones"), so there is never a hidden card standing anywhere to
# name — an empty slice of the candidate set, not unmodelled STATE being
# silently ignored. The gear/unit halves are ordinary bounce targets.

PACK_OF_WONDERS = "ogn-181-298"


def _pack_of_wonders_is_legal(state: GameState, action: ActivateAbility) -> bool:
    """params = ("unit", instance_id) or ("gear", instance_id). "Another"
    only restricts the gear half — Pack of Wonders can't return itself,
    but nothing stops it bouncing a unit."""
    if not _source_is_usable(state, action) or len(action.params) != 2:
        return False
    kind, target_id = action.params
    if kind == "unit":
        located = find_unit_anywhere(state, target_id)
        return located is not None and located[0].controller == state.turn_player
    if kind == "gear":
        if target_id == action.source_id:
            return False  # "another" friendly gear — not itself
        located = find_gear(state, target_id)
        return located is not None and located[1] == state.turn_player
    return False


def _pack_of_wonders_effect(state: GameState, action: ActivateAbility) -> GameState:
    state = _exhaust_source(state, action)
    kind, target_id = action.params
    if kind == "gear":
        target_gear, controller = find_gear(state, target_id)
        player = state.players[controller]
        return replace_player(state, controller, dataclasses.replace(
            player, gear=player.gear - {target_gear}, hand=player.hand + (target_gear.card_id,)))
    unit, zone = find_unit_anywhere(state, target_id)
    if zone == "base":
        player = state.players[unit.controller]
        new_player = dataclasses.replace(player, base_units=player.base_units - {unit},
                                         hand=player.hand + (unit.card_id,))
        return replace_player(state, unit.controller, new_player)
    from .actions import return_unit_to_hand
    return return_unit_to_hand(state, zone, target_id)


def _pack_of_wonders_candidates(state: GameState) -> list[tuple]:
    """Every friendly gear (the source's own instance_id included — it's
    filtered out by is_legal's "another" check, not withheld here, the
    same convention as Zaunite Bouncer's self-target exclusion) plus every
    friendly unit anywhere, Base included."""
    out: list[tuple] = []
    for u in sorted(state.players[state.turn_player].base_units, key=lambda u: u.instance_id):
        out.append(("unit", u.instance_id))
    for bf in state.battlefields:
        for u in sorted(bf.units, key=lambda u: u.instance_id):
            if u.controller == state.turn_player:
                out.append(("unit", u.instance_id))
    for g in sorted(state.players[state.turn_player].gear, key=lambda g: g.instance_id):
        out.append(("gear", g.instance_id))
    return out


# --- The Seals: "Exhaust: [Reaction] Add 1 [domain] rune." ---
#
# RULING 2 (project owner, 2026-09-18): a card that STATES its own domain
# gets a normal, real-domain rune — none of RULING 1's domain-less
# machinery applies, since there's nothing unknowable about it. Nothing
# says "exhausted," so it arrives READY, immediately able to pay Energy
# AND Power of its domain like any other rune. All six Seals share this
# one shape, differing only in which domain — SEAL_DOMAINS below, not six
# near-duplicate effect functions.

SEAL_OF_RAGE = "ogn-040-298"  # "...Add 1 Fury rune."
SEAL_OF_FOCUS = "ogn-081-298"  # "...Add 1 Calm rune."
SEAL_OF_INSIGHT = "ogn-120-298"  # "...Add 1 Mind rune."
SEAL_OF_STRENGTH = "ogn-163-298"  # "...Add 1 Body rune."
SEAL_OF_DISCORD = "ogn-204-298"  # "...Add 1 Chaos rune."
SEAL_OF_UNITY = "ogn-245-298"  # "...Add 1 Order rune."

SEAL_DOMAINS: dict[str, Domain] = {
    SEAL_OF_RAGE: "Fury",
    SEAL_OF_FOCUS: "Calm",
    SEAL_OF_INSIGHT: "Mind",
    SEAL_OF_STRENGTH: "Body",
    SEAL_OF_DISCORD: "Chaos",
    SEAL_OF_UNITY: "Order",
}


def _seal_is_legal(state: GameState, action: ActivateAbility) -> bool:
    return action.params == () and _source_is_usable(state, action)


def _seal_effect(state: GameState, action: ActivateAbility) -> GameState:
    state = _exhaust_source(state, action)
    located = find_gear(state, action.source_id)
    assert located is not None
    _, controller = located
    player = state.players[controller]
    new_pool = add_runes(player.runes, (SEAL_DOMAINS[action.ability_id],))
    return replace_player(state, controller, dataclasses.replace(player, runes=new_pool))


def _seal_candidates(state: GameState) -> list[tuple]:
    return [()]


GEAR_ABILITIES: dict[str, tuple[
    Callable[[GameState, ActivateAbility], bool],
    Callable[[GameState, ActivateAbility], GameState],
    Callable[[GameState], list[tuple]],
]] = {
    IRON_BALLISTA: (_ballista_is_legal, _ballista_effect, _ballista_candidates),
    ORB_OF_REGRET: (_orb_is_legal, _orb_effect, _orb_candidates),
    THE_SYREN: (_syren_is_legal, _syren_effect, _syren_candidates),
    ARENA_BAR: (_arena_bar_is_legal, _arena_bar_effect, _arena_bar_candidates),
    PACK_OF_WONDERS: (_pack_of_wonders_is_legal, _pack_of_wonders_effect, _pack_of_wonders_candidates),
    SEAL_OF_RAGE: (_seal_is_legal, _seal_effect, _seal_candidates),
    SEAL_OF_FOCUS: (_seal_is_legal, _seal_effect, _seal_candidates),
    SEAL_OF_INSIGHT: (_seal_is_legal, _seal_effect, _seal_candidates),
    SEAL_OF_STRENGTH: (_seal_is_legal, _seal_effect, _seal_candidates),
    SEAL_OF_DISCORD: (_seal_is_legal, _seal_effect, _seal_candidates),
    SEAL_OF_UNITY: (_seal_is_legal, _seal_effect, _seal_candidates),
}


def is_legal_gear_ability(state: GameState, action: ActivateAbility) -> bool:
    entry = GEAR_ABILITIES.get(action.ability_id)
    if entry is None:
        return False
    return entry[0](state, action)


def apply_gear_ability(state: GameState, action: ActivateAbility) -> GameState:
    return GEAR_ABILITIES[action.ability_id][1](state, action)
