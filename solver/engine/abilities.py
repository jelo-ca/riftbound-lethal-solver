"""Per-card spell/gear effect registry. Added one card at a time as
puzzles need them — not a general effect engine (design/07-scope-and-cut-
list.md's "add mechanics on demand" policy). Each registered spell pairs a
target/params legality check with the actual game-effect function;
resolve_spell_outcomes() looks a card up here after actions.py's generic
cost/hand bookkeeping (apply_play_spell_cost) has already run.
"""

from __future__ import annotations

import dataclasses
import itertools
from typing import Callable, Optional

from . import combat, deaths, gear, scoring, traits
from .actions import (
    ActivateAbility,
    PlayGear,
    PlaySpell,
    PlayUnit,
    ResolveAttackTrigger,
    RunePayment,
    apply_play_gear,
    apply_play_spell_cost,
    apply_play_unit,
    find_gear,
    find_unit,
    find_unit_anywhere,
    find_unit_at_any_battlefield,
    generate_rune_payments,
    is_legal_ability_move_destination,
    is_legal_play_gear,
    is_legal_play_spell_cost,
    is_legal_play_unit,
    consume_runes,
    kill_gear,
    kill_unit,
    mint_token_unit,
    next_instance_id,
    payment_is_affordable,
    play_unit_from_trash,
    relocate_unit,
    replace_battlefield,
    return_unit_to_hand,
)
from .cards import CardDef
from .state import GameState, replace_player

RIDE_THE_WIND = "ogn-173-298"  # 2 Energy, 1 Chaos Power: "Move a friendly unit and ready it."
YASUO_WINDRIDER = "ogn-205-298"  # [Ganking] "The third time I move in a turn, you score 1 point."

# card_id -> move count that grants the point (checked for an exact match,
# not "every Nth move" - Yasuo's text fires once, at exactly the third).
MOVE_COUNT_TRIGGERS: dict[str, int] = {YASUO_WINDRIDER: 3}


def apply_move_triggers(state: GameState, moved_instance_id: int) -> GameState:
    """Call after ANY move completes (Standard Move, a spell-granted move,
    or moving into/as part of combat) on `moved_instance_id`. A no-op
    unless that unit's card has a registered move-count trigger and its
    new count exactly matches — e.g. Yasuo - Windrider's card-effect point
    (rule 473: unrestricted by the Final Point rule, unlike Conquer),
    needed for design/08-puzzle-concepts.md's puzzle 3 "The Long Way
    Around". Only the mover's own controller benefits (rule text is
    "you score," referring to the card's controller).
    """
    located = find_unit_at_any_battlefield(state, moved_instance_id)
    if located is None:
        located = (find_unit(state, moved_instance_id, "base"), "base")
    unit = located[0]
    if unit is None or unit.controller != state.turn_player:
        return state
    threshold = MOVE_COUNT_TRIGGERS.get(unit.card_id)
    if threshold is not None and unit.moved_this_turn == threshold:
        return scoring.grant_card_effect_point(state)
    return state
CAITLYN_PATROLLING = "ogn-068-298"  # Exhaust: Deal damage equal to my Might to a unit at a battlefield.
BLITZCRANK_IMPASSIVE = "ogn-067-298"  # When you play me to a battlefield, you may move an enemy unit to here.
SETT_BRAWLER = "ogn-164-298"  # "When I'm played and when I conquer, buff me. Spend my buff: +4 Might."
SETT_BRAWLER_ALT = "ogn-164a-298"  # same card, alternate art


def _locate_unit(state: GameState, instance_id: int) -> Optional[str]:
    """Which zone (Base or a battlefield_id) currently holds this
    instance_id, or None if not found."""
    for zone in ["base"] + [bf.battlefield_id for bf in state.battlefields]:
        if find_unit(state, instance_id, zone) is not None:
            return zone
    return None


def _ride_the_wind_is_legal(state: GameState, action: PlaySpell) -> bool:
    """params = (instance_id, destination_zone). "Move a friendly unit and
    ready it" — unlike a Standard Move, the unit does NOT need to already
    be unexhausted (that's the whole point of the card), and the
    destination isn't restricted to Base<->Battlefield-with-Ganking:
    spell-granted moves default to any zone unless the card text says
    otherwise, which this one doesn't (confirmed) — see
    is_legal_ability_move_destination."""
    if len(action.params) != 2:
        return False
    instance_id, destination = action.params
    from_zone = _locate_unit(state, instance_id)
    if from_zone is None:
        return False
    unit = find_unit(state, instance_id, from_zone)
    if unit.controller != state.turn_player:
        return False
    return is_legal_ability_move_destination(state, from_zone, destination)


def _ride_the_wind_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    instance_id, destination = action.params
    from_zone = _locate_unit(state, instance_id)
    assert from_zone is not None
    new_state = relocate_unit(state, instance_id, from_zone, destination, exhausted_after=False)
    if destination != "base":
        new_state = scoring.resolve_control_change(state, new_state, destination)
    return [apply_move_triggers(new_state, instance_id)]


def _ride_the_wind_candidates(state: GameState) -> list[tuple[int, str]]:
    """All (instance_id, destination_zone) pairs worth trying — every
    friendly unit anywhere, times every zone-legal destination for it
    (ignoring exhaustion, per the card's own text)."""
    all_zones = ["base"] + [bf.battlefield_id for bf in state.battlefields]
    candidates = []
    for zone in all_zones:
        units = (
            state.players[state.turn_player].base_units if zone == "base"
            else next(bf.units for bf in state.battlefields if bf.battlefield_id == zone)
        )
        for unit in sorted(units, key=lambda u: u.instance_id):
            if unit.controller != state.turn_player:
                continue
            for destination in all_zones:
                if destination != zone and is_legal_ability_move_destination(state, zone, destination):
                    candidates.append((unit.instance_id, destination))
    return candidates


VENGEANCE = "ogn-229-298"  # 4 Energy, 2 Order Power: "Kill a unit."


def _vengeance_is_legal(state: GameState, action: PlaySpell) -> bool:
    """params = (target_instance_id,). Unrestricted target: any unit
    anywhere on the board, either player's, Base or a battlefield -
    confirmed against the real card, including your own (opens
    sacrifice-style lines a same-controller-only reading would rule out)."""
    if len(action.params) != 1:
        return False
    return find_unit_anywhere(state, action.params[0]) is not None


def _vengeance_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    return [kill_unit(state, action.params[0])]


def _vengeance_candidates(state: GameState) -> list[tuple[int]]:
    """One candidate per unit anywhere on the board - both players' Base
    plus every battlefield."""
    candidates = []
    for player in state.players:
        candidates += [(u.instance_id,) for u in sorted(player.base_units, key=lambda u: u.instance_id)]
    for bf in state.battlefields:
        candidates += [(u.instance_id,) for u in sorted(bf.units, key=lambda u: u.instance_id)]
    return candidates


PRIMAL_STRENGTH = "ogn-154-298"  # 4 Energy, 1 Body Power, [Action]: "Give a unit +7 Might this turn."


def _replace_unit(state: GameState, unit, zone: str, updated) -> GameState:
    """Swap one unit for an updated copy, wherever it stands."""
    if zone == "base":
        player = state.players[unit.controller]
        new_units = (player.base_units - {unit}) | {updated}
        return replace_player(state, unit.controller,
                              dataclasses.replace(player, base_units=new_units))
    bf = next(b for b in state.battlefields if b.battlefield_id == zone)
    return replace_battlefield(state, dataclasses.replace(bf, units=(bf.units - {unit}) | {updated}))


def apply_buff(state: GameState, instance_id: int) -> GameState:
    """Give a unit a buff, worth +1 Might. Buffs don't stack — a unit
    either carries one or it doesn't (see UnitInstance.buffed) — so
    buffing an already-buffed unit is a deliberate no-op rather than a
    second +1. That matters for search: it keeps the action from looking
    like it changed the position when it didn't."""
    located = find_unit_anywhere(state, instance_id)
    assert located is not None
    unit, zone = located
    if unit.buffed:
        return state
    return _replace_unit(state, unit, zone, dataclasses.replace(unit, buffed=True))


def spend_buff(state: GameState, instance_id: int) -> GameState:
    """Remove a unit's buff, for the cards that pay them as a cost
    ("spend any number of buffs")."""
    located = find_unit_anywhere(state, instance_id)
    assert located is not None
    unit, zone = located
    if not unit.buffed:
        return state
    return _replace_unit(state, unit, zone, dataclasses.replace(unit, buffed=False))


def grant_trait(state: GameState, instance_id: int, trait: str) -> GameState:
    """Add a trait to a unit for the rest of the turn.

    Written straight into `unit.keywords` rather than a separate "granted"
    field. traits.resolved_traits reads keywords as the printed-plus-
    granted baseline precisely so this works, and a puzzle is one turn, so
    "this turn" needs no expiry — the same reasoning that folds a
    "+N Might this turn" spell straight into `might`.
    """
    located = find_unit_anywhere(state, instance_id)
    assert located is not None
    unit, zone = located
    if trait in unit.keywords:
        return state
    updated = dataclasses.replace(unit, keywords=unit.keywords | {trait})
    return _replace_unit(state, unit, zone, updated)


def ready_unit(state: GameState, instance_id: int) -> GameState:
    """Un-exhaust a unit, which is what lets it move or attack again this
    turn. A no-op on a unit that is already ready, so the search doesn't
    treat it as progress."""
    located = find_unit_anywhere(state, instance_id)
    assert located is not None
    unit, zone = located
    if not unit.exhausted:
        return state
    return _replace_unit(state, unit, zone, dataclasses.replace(unit, exhausted=False))


def stun_unit(state: GameState, instance_id: int) -> GameState:
    """Marks a unit stunned for the rest of the turn (UnitInstance.stunned).
    RULES ANSWER, project owner, 2026-09-18: this does NOT remove the unit
    from combat and does NOT touch its own Might or death threshold — it
    only makes combat.side_damage_pool ignore it when totaling its SIDE's
    damage-dealing pool for the Combat Damage Step. A no-op on an
    already-stunned unit, same convention as apply_buff/ready_unit/
    grant_trait not treating a repeat application as progress."""
    located = find_unit_anywhere(state, instance_id)
    assert located is not None
    unit, zone = located
    if unit.stunned:
        return state
    return _replace_unit(state, unit, zone, dataclasses.replace(unit, stunned=True))


def _grant_might(state: GameState, instance_id: int, amount: int) -> GameState:
    """Adds `amount` to a unit's `might` wherever it stands — unconditional
    Might raises are just Might (see engine/traits.py's module docstring).
    No expiry bookkeeping: a puzzle is a single turn, so "this turn" covers
    the rest of it."""
    located = find_unit_anywhere(state, instance_id)
    assert located is not None
    unit, zone = located
    buffed = dataclasses.replace(unit, might=unit.might + amount)
    if zone == "base":
        player = state.players[unit.controller]
        new_units = (player.base_units - {unit}) | {buffed}
        return replace_player(state, unit.controller, dataclasses.replace(player, base_units=new_units))
    bf = next(b for b in state.battlefields if b.battlefield_id == zone)
    return replace_battlefield(state, dataclasses.replace(bf, units=(bf.units - {unit}) | {buffed}))


def _primal_strength_is_legal(state: GameState, action: PlaySpell) -> bool:
    """params = (target_instance_id,). "Give a unit +7 Might this turn" —
    "a unit", so either player's, anywhere on the board."""
    if len(action.params) != 1:
        return False
    return find_unit_anywhere(state, action.params[0]) is not None


def _primal_strength_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    return [_grant_might(state, action.params[0], 7)]


def _primal_strength_candidates(state: GameState) -> list[tuple[int]]:
    candidates = []
    for player in state.players:
        candidates += [(u.instance_id,) for u in sorted(player.base_units, key=lambda u: u.instance_id)]
    for bf in state.battlefields:
        candidates += [(u.instance_id,) for u in sorted(bf.units, key=lambda u: u.instance_id)]
    return candidates


# --- [Reaction] spells ----------------------------------------------------
#
# A Reaction is playable "any time, even before spells and abilities
# resolve". In this engine the observable consequence is narrow: since the
# opponent never acts, there is never an opposing effect to respond TO,
# and for a single actor "respond to my own spell" resolves in the same
# order as simply playing it first. So Reaction currently behaves like
# [Action] — playable during a showdown, where Slow cards are not. The one
# place the two genuinely differ is a window during trigger resolution,
# which deaths.py documents as a known gap.

FLURRY_OF_BLADES = "ogn-133-298"  # "Deal 1 to all units at battlefields."
GUST = "ogn-169-298"  # "Return a unit at a battlefield with 3 Might or less to its owner's hand."
SMOKE_SCREEN = "ogn-093-298"  # "Give a unit -4 Might this turn, to a minimum of 1 Might."


def _flurry_is_legal(state: GameState, action: PlaySpell) -> bool:
    return action.params == ()


def _flurry_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    """"All units at battlefields" — both players', both battlefields, and
    Base is untouched. Routed through combat.deal_damage_to_all_at so the
    deaths it causes fire their own [Deathknell]s."""
    for bf in state.battlefields:
        state = combat.deal_damage_to_all_at(state, bf.battlefield_id, 1)
    return [state]


def _flurry_candidates(state: GameState) -> list[tuple]:
    return [()]


def _gust_is_legal(state: GameState, action: PlaySpell) -> bool:
    """params = (target_instance_id,). "3 Might or less" is measured on
    EFFECTIVE Might — a 3-Might unit standing on Trifarian War Camp is a
    4-Might unit and out of range. designation=None: this is not combat,
    so Assault and Shield don't apply."""
    if len(action.params) != 1:
        return False
    located = find_unit_at_any_battlefield(state, action.params[0])
    if located is None:
        return False
    unit, zone = located
    return traits.effective_might(state, unit, zone, None) <= 3


def _gust_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    _, bf_id = find_unit_at_any_battlefield(state, action.params[0])
    return [return_unit_to_hand(state, bf_id, action.params[0])]


def _gust_candidates(state: GameState) -> list[tuple]:
    return [(u.instance_id,) for bf in state.battlefields
            for u in sorted(bf.units, key=lambda u: u.instance_id)]


def _smoke_screen_is_legal(state: GameState, action: PlaySpell) -> bool:
    """"A unit" — either player's, anywhere, same as Primal Strength."""
    if len(action.params) != 1:
        return False
    return find_unit_anywhere(state, action.params[0]) is not None


def _smoke_screen_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    """-4 Might with a floor of 1. The floor is on the card, not a
    modelling convenience: a unit reduced to 0 would die to any damage at
    all, and "to a minimum of 1" exists precisely to stop that."""
    located = find_unit_anywhere(state, action.params[0])
    unit, _ = located
    reduction = min(4, max(0, unit.might - 1))
    return [_grant_might(state, action.params[0], -reduction)]


def _smoke_screen_candidates(state: GameState) -> list[tuple]:
    candidates = []
    for player in state.players:
        candidates += [(u.instance_id,) for u in sorted(player.base_units, key=lambda u: u.instance_id)]
    for bf in state.battlefields:
        candidates += [(u.instance_id,) for u in sorted(bf.units, key=lambda u: u.instance_id)]
    return candidates


# --- Direct-damage and removal spells -------------------------------------
#
# All of these are the same two shapes with different numbers, so they
# share candidate generators rather than repeating them per card.

HEXTECH_RAY = "ogn-009-298"  # [Action] "Deal 3 to a unit at a battlefield."
FALLING_COMET = "ogn-085-298"  # [Action] "Deal 6 to a unit at a battlefield."
FALLING_STAR = "ogn-029-298"  # "Deal 3 to a unit. Deal 3 to a unit."
REBUKE = "ogn-172-298"  # [Action] "Return a unit at a battlefield to its owner's hand."
GRAND_STRATEGEM = "ogn-233-298"  # [Action] "Give friendly units +5 Might this turn."

# card_id -> damage dealt to a single unit at a battlefield.
FLAT_DAMAGE_SPELLS: dict[str, int] = {HEXTECH_RAY: 3, FALLING_COMET: 6}


def _units_at_battlefields(state: GameState) -> list[tuple]:
    return [(u.instance_id,) for bf in state.battlefields
            for u in sorted(bf.units, key=lambda u: u.instance_id)]


def _single_battlefield_target_is_legal(state: GameState, action: PlaySpell) -> bool:
    return (len(action.params) == 1
            and find_unit_at_any_battlefield(state, action.params[0]) is not None)


def _flat_damage_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    """Effect damage, not combat damage — designation is None inside
    deal_damage_to_unit, so Shield and Assault don't soften it, and any
    death it causes fires that unit's [Deathknell]."""
    amount = FLAT_DAMAGE_SPELLS[action.card_id]
    _, bf_id = find_unit_at_any_battlefield(state, action.params[0])
    return [combat.deal_damage_to_unit(state, bf_id, action.params[0], amount)]


def _falling_star_is_legal(state: GameState, action: PlaySpell) -> bool:
    """params = (first_target, second_target). "Deal 3 to a unit. Deal 3 to
    a unit." is two separate instances, so the same unit may legally be
    chosen twice — that is how the card kills a 6-Might body."""
    if len(action.params) != 2:
        return False
    return all(find_unit_anywhere(state, target) is not None for target in action.params)


def _falling_star_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    """Resolved one instance at a time: the first 3 can kill the target,
    in which case the second instance simply finds nothing there. Aiming
    both at one unit is a real choice, so it must not be collapsed into a
    single 6."""
    for target in action.params:
        located = find_unit_at_any_battlefield(state, target)
        if located is None:
            continue  # already dead, or at Base where this can still be aimed
        state = combat.deal_damage_to_unit(state, located[1], target, 3)
    return [state]


def _falling_star_candidates(state: GameState) -> list[tuple]:
    ids = [u.instance_id for bf in state.battlefields
           for u in sorted(bf.units, key=lambda u: u.instance_id)]
    return [(a, b) for a in ids for b in ids]


def _rebuke_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    """"A unit" — either player's. Bouncing our own is occasionally right,
    so it isn't restricted to enemies."""
    _, bf_id = find_unit_at_any_battlefield(state, action.params[0])
    return [return_unit_to_hand(state, bf_id, action.params[0])]


def _grand_strategem_is_legal(state: GameState, action: PlaySpell) -> bool:
    return action.params == ()


def _grand_strategem_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    """"Friendly units" — ours everywhere, Base included, with no target
    choice at all."""
    for player_index, player in enumerate(state.players):
        if player_index != state.turn_player:
            continue
        for unit in sorted(player.base_units, key=lambda u: u.instance_id):
            state = _grant_might(state, unit.instance_id, 5)
    for bf in state.battlefields:
        for unit in sorted(bf.units, key=lambda u: u.instance_id):
            if unit.controller == state.turn_player:
                state = _grant_might(state, unit.instance_id, 5)
    return [state]



CLEAVE = "ogn-004-298"  # [Action] "Give a unit [Assault 3] this turn."
SINGULARITY = "ogn-105-298"  # "Deal 6 to each of up to two units."
BACK_TO_BACK = "ogn-206-298"  # [Reaction] "Give two friendly units each +2 Might this turn."


def _cleave_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    """[Assault 3] is a trait, not flat Might: it only counts while the
    unit is attacking, which is why it goes through grant_trait rather
    than being added to Might directly."""
    return [grant_trait(state, action.params[0], "Assault 3")]


def _any_unit_is_legal(state: GameState, action: PlaySpell) -> bool:
    return len(action.params) == 1 and find_unit_anywhere(state, action.params[0]) is not None


def _any_unit_candidates(state: GameState) -> list[tuple]:
    out = []
    for player in state.players:
        out += [(u.instance_id,) for u in sorted(player.base_units, key=lambda u: u.instance_id)]
    for bf in state.battlefields:
        out += [(u.instance_id,) for u in sorted(bf.units, key=lambda u: u.instance_id)]
    return out


def _singularity_is_legal(state: GameState, action: PlaySpell) -> bool:
    """"Up to two units" — zero, one or two, and they must be distinct,
    unlike Falling Star's two separate instances."""
    if len(action.params) > 2 or len(set(action.params)) != len(action.params):
        return False
    return all(find_unit_anywhere(state, t) is not None for t in action.params)


def _singularity_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    for target in action.params:
        located = find_unit_at_any_battlefield(state, target)
        if located is not None:
            state = combat.deal_damage_to_unit(state, located[1], target, 6)
    return [state]


def _singularity_candidates(state: GameState) -> list[tuple]:
    ids = [u.instance_id for bf in state.battlefields
           for u in sorted(bf.units, key=lambda u: u.instance_id)]
    out: list[tuple] = [()]
    out += [(a,) for a in ids]
    out += [(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]]
    return out


def _back_to_back_is_legal(state: GameState, action: PlaySpell) -> bool:
    """"Two friendly units" — two distinct ones, both ours."""
    if len(action.params) != 2 or action.params[0] == action.params[1]:
        return False
    for target in action.params:
        located = find_unit_anywhere(state, target)
        if located is None or located[0].controller != state.turn_player:
            return False
    return True


def _back_to_back_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    for target in action.params:
        state = _grant_might(state, target, 2)
    return [state]


def _back_to_back_candidates(state: GameState) -> list[tuple]:
    ours = [u.instance_id for u in sorted(state.players[state.turn_player].base_units,
                                           key=lambda u: u.instance_id)]
    ours += [u.instance_id for bf in state.battlefields
             for u in sorted(bf.units, key=lambda u: u.instance_id)
             if u.controller == state.turn_player]
    return [(a, b) for i, a in enumerate(ours) for b in ours[i + 1:]]


LAST_STAND = "ogn-069-298"  # [Action] "Double a friendly unit's Might this turn. Give it [Temporary]."
UNCHECKED_POWER = "ogn-123-298"  # "Exhaust all friendly units, then deal 12 to ALL units at battlefields."
CHALLENGE = "ogn-128-298"  # [Action] "Choose a friendly unit and an enemy unit. They deal damage equal to their Mights to each other."


def _friendly_unit_is_legal(state: GameState, action: PlaySpell) -> bool:
    if len(action.params) != 1:
        return False
    located = find_unit_anywhere(state, action.params[0])
    return located is not None and located[0].controller == state.turn_player


def _friendly_unit_candidates(state: GameState) -> list[tuple]:
    out = [(u.instance_id,) for u in sorted(state.players[state.turn_player].base_units,
                                             key=lambda u: u.instance_id)]
    out += [(u.instance_id,) for bf in state.battlefields
            for u in sorted(bf.units, key=lambda u: u.instance_id)
            if u.controller == state.turn_player]
    return out


def _last_stand_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    """Doubling is computed off PRINTED Might, not effective Might: the
    conditional and positional parts of effective Might (Shield, a
    battlefield's bonus) aren't part of the unit's own Might to double.

    [Temporary] is granted for fidelity even though it is inert here — it
    kills at the start of a Beginning Phase a single turn never reaches.
    Granting it is free and keeps the card honest if that ever changes."""
    located = find_unit_anywhere(state, action.params[0])
    unit, _ = located
    state = _grant_might(state, action.params[0], unit.might)
    return [grant_trait(state, action.params[0], "Temporary")]


def _unchecked_power_is_legal(state: GameState, action: PlaySpell) -> bool:
    return action.params == ()


def _unchecked_power_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    """Exhausting our own units first is a real cost: it strips their
    ability to move or fight afterwards, which can be what stops the line
    the 12 damage opens up."""
    for player_index, player in enumerate(state.players):
        if player_index != state.turn_player:
            continue
        for unit in sorted(player.base_units, key=lambda u: u.instance_id):
            state = _replace_unit(state, unit, "base", dataclasses.replace(unit, exhausted=True))
    for bf in state.battlefields:
        for unit in sorted(bf.units, key=lambda u: u.instance_id):
            if unit.controller == state.turn_player:
                current = find_unit_anywhere(state, unit.instance_id)
                state = _replace_unit(state, current[0], current[1],
                                      dataclasses.replace(current[0], exhausted=True))
    for bf in state.battlefields:
        state = combat.deal_damage_to_all_at(state, bf.battlefield_id, 12)
    return [state]


def _mutual_damage(state: GameState, first_id: int, second_id: int) -> GameState:
    """Two units deal damage equal to their Mights to each other,
    SIMULTANEOUSLY — both amounts are read before either is applied, so a
    unit that dies still deals its damage. Reading them one at a time
    would let the first kill silence the second."""
    first = find_unit_anywhere(state, first_id)
    second = find_unit_anywhere(state, second_id)
    if first is None or second is None:
        return state
    first_might = traits.effective_might(state, first[0], first[1], None)
    second_might = traits.effective_might(state, second[0], second[1], None)
    for target_id, amount in ((first_id, second_might), (second_id, first_might)):
        located = find_unit_at_any_battlefield(state, target_id)
        if located is not None:
            state = combat.deal_damage_to_unit(state, located[1], target_id, amount)
    return state


def _challenge_is_legal(state: GameState, action: PlaySpell) -> bool:
    """params = (friendly_id, enemy_id), both at battlefields — damage
    outside a battlefield has nowhere to resolve in this engine."""
    if len(action.params) != 2:
        return False
    ours = find_unit_at_any_battlefield(state, action.params[0])
    theirs = find_unit_at_any_battlefield(state, action.params[1])
    return (ours is not None and theirs is not None
            and ours[0].controller == state.turn_player
            and theirs[0].controller != state.turn_player)


def _challenge_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    return [_mutual_damage(state, action.params[0], action.params[1])]


def _challenge_candidates(state: GameState) -> list[tuple]:
    ours = [u.instance_id for bf in state.battlefields
            for u in sorted(bf.units, key=lambda u: u.instance_id)
            if u.controller == state.turn_player]
    theirs = [u.instance_id for bf in state.battlefields
              for u in sorted(bf.units, key=lambda u: u.instance_id)
              if u.controller != state.turn_player]
    return [(a, b) for a in ours for b in theirs]


EN_GARDE = "ogn-046-298"  # [Reaction] "+1 Might, then an additional +1 if it is the only unit you control there."


def _en_garde_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    """"The only unit you control THERE" — counted per zone, and counted
    BEFORE the buff lands (the buff changes no unit's location). A unit at
    Base counts the Base crowd; nothing about this is battlefield-only."""
    target_id = action.params[0]
    unit, zone = find_unit_anywhere(state, target_id)
    if zone == "base":
        companions = state.players[unit.controller].base_units
    else:
        companions = next(b for b in state.battlefields if b.battlefield_id == zone).units
    alone = sum(1 for u in companions if u.controller == unit.controller) == 1
    return [_grant_might(state, target_id, 2 if alone else 1)]


CARNIVOROUS_SNAPVINE = "ogn-149-298"  # "When you play me, choose an enemy unit at a battlefield. We deal damage equal to our Mights to each other."


def _snapvine_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    """Same simultaneous exchange as Challenge, with the Snapvine itself as
    one side — so it can trade itself for a bigger body."""
    me = _played_unit(state_after_play, action)
    return [_mutual_damage(state_after_play, me.instance_id, action.trigger_params[0])]


CHARM = "ogn-043-298"  # 1 Energy, 1 Calm Power: "Move an enemy unit." (Slow speed —
# can't be played during a showdown; the engine has no showdown/priority-
# window concept yet, so nothing currently in the action space could even
# attempt this at the wrong time — nothing to enforce until showdowns exist.)


def _move_enemy_unit_no_combat(state: GameState, unit, from_zone: str, to_zone: str) -> GameState:
    """Relocates a unit NOT controlled by turn_player between two
    battlefields when no combat is triggered (destination is empty, or
    already held only by the SAME controller as `unit`) — relocate_unit
    can't be reused here since it hardcodes turn_player as "whose board
    this is" (see its docstring), which is wrong for an enemy-controlled
    mover; reusing it would silently touch the wrong player's Base and
    misjudge the destination's combat check."""
    moved_unit = dataclasses.replace(unit, moved_this_turn=unit.moved_this_turn + 1)
    from_bf = next(b for b in state.battlefields if b.battlefield_id == from_zone)
    remaining = from_bf.units - {unit}
    from_controller = from_bf.controller if remaining else None
    state = replace_battlefield(state, dataclasses.replace(from_bf, units=remaining, controller=from_controller))

    to_bf = next(b for b in state.battlefields if b.battlefield_id == to_zone)
    new_units = to_bf.units | {moved_unit}
    controllers = {u.controller for u in new_units}
    new_controller = next(iter(controllers)) if len(controllers) == 1 else None
    return replace_battlefield(state, dataclasses.replace(to_bf, units=new_units, controller=new_controller))


def _charm_is_legal(state: GameState, action: PlaySpell) -> bool:
    """params = (enemy_instance_id, destination_battlefield_id), or with
    a third `our_assignment` element if the redirect causes combat — we
    become the Defender (the ENEMY's own unit's move caused the
    Contested status, design/09-combat-resolution.md's "not always the
    Attacker" case, same shape as Blitzcrank's redirect but reachable
    any turn via a spell instead of tied to playing a specific unit).
    Scoped to battlefield<->battlefield only: an enemy unit's own Base
    isn't representable in this engine's zone model (Zone can't
    disambiguate whose Base without a controller-aware from/to)."""
    if len(action.params) not in (2, 3):
        return False
    enemy_id, destination = action.params[0], action.params[1]
    located = find_unit_at_any_battlefield(state, enemy_id)
    if located is None:
        return False
    unit, from_zone = located
    if unit.controller == state.turn_player or from_zone == destination:
        return False
    if not any(bf.battlefield_id == destination for bf in state.battlefields):
        return False
    if combat.is_combat_triggered(state, unit, destination):
        if len(action.params) != 3:
            return False
        return action.params[2] in combat.our_assignment_options(state, unit, destination)
    return len(action.params) == 2


def _charm_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    enemy_id, destination = action.params[0], action.params[1]
    unit, from_zone = find_unit_at_any_battlefield(state, enemy_id)

    if combat.is_combat_triggered(state, unit, destination):
        our_assignment = action.params[2]
        # Charm's text grants a move without exhausting, so the redirected
        # unit keeps its existing exhaustion into the fight.
        outcomes = combat.enumerate_combat_outcomes(state, unit, from_zone, destination,
                                                     our_assignment, exhausted_after=unit.exhausted)
        outcomes = [scoring.resolve_control_change(state, o, destination) for o in outcomes]
        return [apply_move_triggers(o, enemy_id) for o in outcomes]

    moved_state = _move_enemy_unit_no_combat(state, unit, from_zone, destination)
    moved_state = scoring.resolve_control_change(state, moved_state, destination)
    return [apply_move_triggers(moved_state, enemy_id)]


def _charm_candidates(state: GameState) -> list[tuple]:
    """One candidate per enemy unit at a battlefield, times every OTHER
    battlefield as a destination, further split by our damage-assignment
    choice if the redirect causes combat."""
    candidates: list[tuple] = []
    for bf in state.battlefields:
        for unit in sorted(bf.units, key=lambda u: u.instance_id):
            if unit.controller == state.turn_player:
                continue
            for destination_bf in state.battlefields:
                if destination_bf.battlefield_id == bf.battlefield_id:
                    continue
                destination = destination_bf.battlefield_id
                if combat.is_combat_triggered(state, unit, destination):
                    for our_assignment in combat.our_assignment_options(state, unit, destination):
                        candidates.append((unit.instance_id, destination, our_assignment))
                else:
                    candidates.append((unit.instance_id, destination))
    return candidates


OVERT_OPERATION = "ogn-153-298"  # [Action] "For each friendly unit, you may spend its buff to ready it. Then buff all friendly units."


def _friendly_units_anywhere(state: GameState) -> list:
    out = list(state.players[state.turn_player].base_units)
    out += [u for bf in state.battlefields for u in bf.units if u.controller == state.turn_player]
    return out


def _overt_operation_is_legal(state: GameState, action: PlaySpell) -> bool:
    """params = a subset (no repeats) of friendly units to spend-and-ready
    — each must currently carry a buff, since "spend its buff" has nothing
    to spend otherwise. The trailing "buff all friendly units" chooses
    nothing of its own, so it isn't part of params at all."""
    if len(set(action.params)) != len(action.params):
        return False
    buffed_ids = {u.instance_id for u in _friendly_units_anywhere(state) if u.buffed}
    return all(target in buffed_ids for target in action.params)


def _overt_operation_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    for target in action.params:
        state = ready_unit(spend_buff(state, target), target)
    for unit in _friendly_units_anywhere(state):
        state = apply_buff(state, unit.instance_id)
    return [state]


def _overt_operation_candidates(state: GameState) -> list[tuple]:
    """Every subset of currently-buffed friendly units — "for each
    friendly unit" offers the spend-to-ready choice independently, so N
    buffed units give 2**N legal choices, not just N+1 (contrast Kinkou
    Monk's capped "up to two")."""
    ids = [u.instance_id for u in sorted(_friendly_units_anywhere(state), key=lambda u: u.instance_id)
           if u.buffed]
    out: list[tuple] = []
    for size in range(len(ids) + 1):
        out.extend(itertools.combinations(ids, size))
    return out


# Showstopper (ogn-270-298), "Buff a friendly unit in your base, then move
# it to a battlefield," is NOT registered here — not a text problem but a
# data one. Its Power cost lists TWO domains (Body, Order) with no way to
# tell which one pays; card_data.py refuses this on purpose rather than
# guess (see its "REFUSES RATHER THAN GUESSES" docstring), so card_def()
# returns None for it and it can never carry stats. Clearing it as HANDLED
# would fail test_every_handled_card_has_stats_available, and hand-picking
# a domain would be exactly the hand-transcription this project keeps
# getting burned by. Stays BLOCKING until a canonical source settles which
# domain is real.


# --- Trash zone: return-to-hand and recycle-as-cost cards -----------------
#
# state.py's trash is a plain tuple of card_ids — "removing" one from it
# for either mechanic below means dropping ONE matching occurrence, not
# deduplicating, since two dead copies of the same card are two separate
# entries.

def _units_in_trash(state: GameState, controller: int) -> list[str]:
    """Distinct card_ids in `controller`'s trash that are actually Unit
    printings — "return a unit from your trash" can't target a spell that
    landed there. Deferred import: card_pool.py imports this module."""
    from .card_pool import card_def
    return sorted({card_id for card_id in state.players[controller].trash
                   if (d := card_def(card_id)) is not None and d.card_type == "Unit"})


def _remove_one_from_trash(state: GameState, controller: int, card_id: str) -> GameState:
    player = state.players[controller]
    trash = list(player.trash)
    trash.remove(card_id)
    return replace_player(state, controller, dataclasses.replace(player, trash=tuple(trash)))


def _return_unit_from_trash_to_hand(state: GameState, controller: int, card_id: str) -> GameState:
    state = _remove_one_from_trash(state, controller, card_id)
    player = state.players[controller]
    return replace_player(state, controller,
                          dataclasses.replace(player, hand=player.hand + (card_id,)))


CEMETERY_ATTENDANT = "ogn-165-298"  # "When you play me, return a unit from your trash to your hand."
MORBID_RETURN = "ogn-170-298"  # [Action] "Return a unit from your trash to your hand."


def _cemetery_attendant_is_legal(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    """Mandatory, but only reachable when a target exists — same
    "no legal target means the triggered form can't be offered" shape as
    Harnessed Dragon/Riptide Rex against an empty board."""
    if len(action.trigger_params) != 1:
        return False
    state_after_play = apply_play_unit(state, dataclasses.replace(
        action, trigger_params=(), trigger_payment=None), card)
    return action.trigger_params[0] in _units_in_trash(state_after_play, state.turn_player)


def _cemetery_attendant_candidates(state: GameState, base_action: PlayUnit, card: CardDef) -> list[tuple]:
    state_after_play = apply_play_unit(state, base_action, card)
    return [(card_id,) for card_id in _units_in_trash(state_after_play, state.turn_player)]


def _cemetery_attendant_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    return [_return_unit_from_trash_to_hand(state_after_play, state_after_play.turn_player,
                                             action.trigger_params[0])]


def _morbid_return_is_legal(state: GameState, action: PlaySpell) -> bool:
    if len(action.params) != 1:
        return False
    return action.params[0] in _units_in_trash(state, state.turn_player)


def _morbid_return_candidates(state: GameState) -> list[tuple]:
    return [(card_id,) for card_id in _units_in_trash(state, state.turn_player)]


def _morbid_return_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    return [_return_unit_from_trash_to_hand(state, state.turn_player, action.params[0])]


VI_DESTRUCTIVE = "ogn-036-298"  # [Ganking] "Recycle 1 from your trash: Give me +1 Might this turn."


def _vi_destructive_is_legal(state: GameState, action: ActivateAbility) -> bool:
    """params = (card_id,) — the trash entry recycled to pay the cost. No
    rune cost printed; the recycled card IS the cost, same shape as Sett
    Brawler's "spend my buff" ability."""
    if len(action.params) != 1:
        return False
    located = find_unit_anywhere(state, action.source_id)
    if located is None:
        return False
    source, _ = located
    if source.controller != state.turn_player:
        return False
    if action.rune_payment is not None:
        return False
    return action.params[0] in state.players[state.turn_player].trash


def _vi_destructive_effect(state: GameState, action: ActivateAbility) -> GameState:
    state = _remove_one_from_trash(state, state.turn_player, action.params[0])
    return _grant_might(state, action.source_id, 1)


def _vi_destructive_candidates(state: GameState) -> list[tuple]:
    return [(card_id,) for card_id in sorted(set(state.players[state.turn_player].trash))]


# "Play a unit from your trash, ignoring its Energy cost. (You must still
# pay its Power cost.)" — Soulgorger (a play trigger) and The Harrowing (a
# spell) share the exact same effect body. Restricted to trash units with
# NO registered UNIT_PLAY_TRIGGERS entry — see play_unit_from_trash's
# docstring for why: this path never dispatches the replayed unit's own
# "when you play me" text, so a board where that would matter stays
# refused on THIS card's clause rather than silently dropping a real
# effect. Restrictive, not permissive — the same direction as
# conquer.py's "who conquered" narrowing.
SOULGORGER = "ogn-196-298"
THE_HARROWING = "ogn-198-298"


def _trash_replay_candidate_zones(state: GameState, controller: int) -> list[str]:
    """Base, or a battlefield ALREADY controlled by `controller` — neither
    card can play to an OPEN battlefield, so this never establishes
    control (play_unit_from_trash relies on that)."""
    return ["base"] + [bf.battlefield_id for bf in state.battlefields if bf.controller == controller]


def _trash_replay_candidates(state: GameState, controller: int) -> list[tuple]:
    """(card_id, zone, power_payment) triples — cost is Power only,
    Energy waived by the printed effect."""
    from .card_pool import card_def
    out = []
    for card_id in _units_in_trash(state, controller):
        if card_id in UNIT_PLAY_TRIGGERS:
            continue
        card = card_def(card_id)
        for zone in _trash_replay_candidate_zones(state, controller):
            for payment in generate_rune_payments(state.players[controller].runes, 0,
                                                    card.power_cost, card.power_domain):
                out.append((card_id, zone, payment))
    return out


def _morbid_return_style_is_legal(state: GameState, controller: int, params: tuple) -> bool:
    if len(params) != 3:
        return False
    card_id, zone, payment = params
    if card_id in UNIT_PLAY_TRIGGERS:
        return False
    if card_id not in _units_in_trash(state, controller):
        return False
    if zone not in _trash_replay_candidate_zones(state, controller):
        return False
    from .card_pool import card_def
    card = card_def(card_id)
    if len(payment.energy_runes) != 0 or len(payment.power_runes) != card.power_cost:
        return False
    if card.power_cost and any(d != card.power_domain for d in payment.power_runes):
        return False
    return payment_is_affordable(state.players[controller].runes, payment)


def _trash_replay_effect(state: GameState, card_id: str, zone: str, payment: RunePayment) -> GameState:
    from .card_pool import card_def
    return play_unit_from_trash(state, card_def(card_id), state.turn_player, zone, payment)


def _soulgorger_is_legal(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    """Optional ("you may") — trigger_params == () is a legitimate
    decline, same as Blitzcrank/Zaunite Bouncer."""
    if action.trigger_params == ():
        return True
    state_after_play = apply_play_unit(state, dataclasses.replace(
        action, trigger_params=(), trigger_payment=None), card)
    return _morbid_return_style_is_legal(state_after_play, state.turn_player, action.trigger_params)


def _soulgorger_candidates(state: GameState, base_action: PlayUnit, card: CardDef) -> list[tuple]:
    state_after_play = apply_play_unit(state, base_action, card)
    return _trash_replay_candidates(state_after_play, state.turn_player)


def _soulgorger_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    if not action.trigger_params:
        return [state_after_play]
    card_id, zone, payment = action.trigger_params
    return [_trash_replay_effect(state_after_play, card_id, zone, payment)]


def _the_harrowing_is_legal(state: GameState, action: PlaySpell) -> bool:
    """The trash-unit's Power payment must come from what THE HARROWING's
    OWN cost (action.rune_payment) leaves behind — same "pay from what's
    left" shape as [Deflect]'s trigger tax (trigger_deflect_tax)."""
    player = state.players[state.turn_player]
    remaining = replace_player(state, state.turn_player,
                               dataclasses.replace(player, runes=consume_runes(
                                   player.runes, action.rune_payment)))
    return _morbid_return_style_is_legal(remaining, state.turn_player, action.params)


def _the_harrowing_candidates(state: GameState) -> list[tuple]:
    return _trash_replay_candidates(state, state.turn_player)


def _the_harrowing_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    card_id, zone, payment = action.params
    return [_trash_replay_effect(state, card_id, zone, payment)]


# Salvage: "[Action] You may kill a gear. Draw 1." "A gear" is unqualified
# — no "friendly" or "enemy" — same convention as Orb of Regret's "give a
# unit -1 Might", which the gear.py module docstring already establishes
# reads as either player's. "Draw 1" is a no-op (no Main Deck; HANDOFF's
# Position model, same reading as every other draw-N card in the pool),
# so only the kill half does anything, and it's optional.
SALVAGE = "ogn-224-298"


def _salvage_candidates(state: GameState) -> list[tuple]:
    """Declining (the empty tuple, leaving only the no-op draw) is always
    legal. Gear with its own unbuilt on-death reaction is excluded from
    the kill target list — see gear.GEAR_DEATH_REACTIONS — rather than
    silently dropping that reaction on the floor."""
    out: list[tuple] = [()]
    for player in state.players:
        for piece in sorted(player.gear, key=lambda g: g.instance_id):
            if piece.card_id not in gear.GEAR_DEATH_REACTIONS:
                out.append((piece.instance_id,))
    return out


def _salvage_is_legal(state: GameState, action: PlaySpell) -> bool:
    if action.params == ():
        return True
    if len(action.params) != 1:
        return False
    located = find_gear(state, action.params[0])
    if located is None:
        return False
    piece, _ = located
    return piece.card_id not in gear.GEAR_DEATH_REACTIONS


def _salvage_effect(state: GameState, action: PlaySpell) -> list[GameState]:
    if not action.params:
        return [state]
    piece, controller = find_gear(state, action.params[0])
    return [kill_gear(state, controller, piece)]


# Spectral Matron: "play a unit costing no more than 3 Energy and no more
# than [rainbow, bare] from your trash, ignoring its cost" — a bare
# rainbow icon reads as 1 Power of any domain (project owner,
# 2026-09-18), matching [Deflect]'s rainbow-rune notation elsewhere.
# Distinct from Soulgorger/The Harrowing: the WHOLE cost is waived here,
# not just Energy, so play_unit_from_trash is called with an EMPTY
# payment (consume_runes is a no-op against it) rather than a real one —
# same helper, no new mechanism, just a different call.
SPECTRAL_MATRON = "ogn-226-298"


def _spectral_matron_eligible(card: CardDef) -> bool:
    return card.energy_cost <= 3 and card.power_cost <= 1


def _spectral_matron_candidates(state: GameState, base_action: PlayUnit, card: CardDef) -> list[tuple]:
    from .card_pool import card_def
    state_after_play = apply_play_unit(state, base_action, card)
    controller = state.turn_player
    out = []
    for card_id in _units_in_trash(state_after_play, controller):
        if card_id in UNIT_PLAY_TRIGGERS:
            continue
        if not _spectral_matron_eligible(card_def(card_id)):
            continue
        for zone in _trash_replay_candidate_zones(state_after_play, controller):
            out.append((card_id, zone))
    return out


def _spectral_matron_is_legal(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    """Optional ("you may")."""
    if action.trigger_params == ():
        return True
    if len(action.trigger_params) != 2:
        return False
    from .card_pool import card_def
    state_after_play = apply_play_unit(state, dataclasses.replace(
        action, trigger_params=(), trigger_payment=None), card)
    card_id, zone = action.trigger_params
    controller = state.turn_player
    if card_id in UNIT_PLAY_TRIGGERS or card_id not in _units_in_trash(state_after_play, controller):
        return False
    if not _spectral_matron_eligible(card_def(card_id)):
        return False
    return zone in _trash_replay_candidate_zones(state_after_play, controller)


def _spectral_matron_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    if not action.trigger_params:
        return [state_after_play]
    from .card_pool import card_def
    card_id, zone = action.trigger_params
    return [play_unit_from_trash(state_after_play, card_def(card_id), state_after_play.turn_player,
                                  zone, RunePayment(energy_runes=(), power_runes=()))]


# --- Spell-kill reactions: "when you kill a unit with a spell" -----------
#
# A watcher's optional reaction to a kill that a SPELL just caused —
# generic across every spell, since damage from many different spells
# (Hextech Ray, Falling Comet, Vengeance's outright kill, ...) can be the
# lethal blow. Detected as a diff (deaths.units_killed_between) rather
# than per-spell bookkeeping, the same shape as conquer.py's "who
# conquered." Restricted to spells whose OWN resolve_spell_outcomes
# returns exactly one state — restrictive, not permissive, same direction
# as everywhere else this session: a spell that could ALSO cause
# adversarial combat (none currently registered do) would need its own
# extension to this, not a silent overclaim.
IMMORTAL_PHOENIX = "ogn-037-298"  # "[Assault 2] When you kill a unit with a spell, you
# may pay 1 Energy, 1 Fury to play me from your trash." A fixed alternate
# cost, NOT her printed 3E/1Fury — text-specific, like [Accelerate]'s.

# watcher_card_id -> (energy_cost, power_cost, power_domain) for the
# reaction's OWN fixed cost (distinct from the watcher's printed cost).
SPELL_KILL_REACTION_COST: dict[str, tuple[int, int, Optional[str]]] = {
    IMMORTAL_PHOENIX: (1, 1, "Fury"),
}

def _immortal_phoenix_reaction_effect(state: GameState, zone: str, payment: RunePayment) -> GameState:
    from .card_pool import card_def
    return play_unit_from_trash(state, card_def(IMMORTAL_PHOENIX), state.turn_player, zone, payment)


# watcher_card_id -> effect(state, zone, payment) -> GameState. Kept
# separate from PlayUnit/PlaySpell effect signatures since a reaction's
# payment is always its own fixed cost, never the watched spell's.
SPELL_KILL_REACTIONS: dict[str, Callable[[GameState, str, RunePayment], GameState]] = {
    IMMORTAL_PHOENIX: _immortal_phoenix_reaction_effect,
}


def _spell_single_outcome(state: GameState, action: PlaySpell, card: CardDef) -> Optional[GameState]:
    """The base spell's own resolution, iff it's deterministic (exactly
    one outcome) — see module comment above for why this stays narrow."""
    try:
        outcomes = resolve_spell_outcomes(state, action, card)
    except NotImplementedError:
        return None
    if len(outcomes) != 1:
        return None
    return outcomes[0]


def spell_kill_reaction_candidates(state: GameState, action: PlaySpell, card: CardDef) -> list[tuple]:
    """(watcher_card_id, zone, reaction_payment) tuples for every
    registered watcher in `state.turn_player`'s trash, IF resolving
    `action` (with its OWN rune_payment already fixed) would kill at
    least one unit. Payment is drawn from what `action.rune_payment`
    leaves behind, same "pay from what's left" shape as [Deflect]'s
    trigger tax. Zone options are read off the board AFTER the spell
    resolves (base, or a battlefield the reaction wouldn't need to
    conquer — no watcher here can play to an open one). Bails before the
    (re-simulate the spell) cost check if trash has no registered watcher
    at all — the common case, and otherwise this would re-run every
    spell's effect speculatively on every node just to find out."""
    player = state.players[state.turn_player]
    if not any(c in SPELL_KILL_REACTION_COST for c in player.trash):
        return []
    base_outcome = _spell_single_outcome(state, action, card)
    if base_outcome is None or not deaths.units_killed_between(state, base_outcome):
        return []
    remaining = consume_runes(player.runes, action.rune_payment)
    zones = _trash_replay_candidate_zones(base_outcome, state.turn_player)
    out = []
    for watcher in sorted(set(player.trash)):
        cost = SPELL_KILL_REACTION_COST.get(watcher)
        if cost is None:
            continue
        energy_cost, power_cost, power_domain = cost
        for zone in zones:
            for payment in generate_rune_payments(remaining, energy_cost, power_cost, power_domain):
                out.append((watcher, zone, payment))
    return out


def is_legal_spell_kill_reaction(state: GameState, action: PlaySpell, card: CardDef) -> bool:
    if len(action.reaction_params) != 3:
        return False
    watcher, zone, payment = action.reaction_params
    if watcher not in state.players[state.turn_player].trash:
        return False
    cost = SPELL_KILL_REACTION_COST.get(watcher)
    if cost is None:
        return False
    base_outcome = _spell_single_outcome(state, action, card)
    if base_outcome is None or not deaths.units_killed_between(state, base_outcome):
        return False
    if zone not in _trash_replay_candidate_zones(base_outcome, state.turn_player):
        return False
    energy_cost, power_cost, power_domain = cost
    if len(payment.energy_runes) != energy_cost or len(payment.power_runes) != power_cost:
        return False
    if power_cost and any(d != power_domain for d in payment.power_runes):
        return False
    remaining = consume_runes(state.players[state.turn_player].runes, action.rune_payment)
    return payment_is_affordable(remaining, payment)


def resolve_spell_outcomes_with_reaction(state: GameState, action: PlaySpell, card: CardDef) -> list[GameState]:
    """Resolves the base spell (exactly one outcome — reaction_params is
    only ever offered when that held true at candidate-generation time),
    then applies the reaction on top if one was chosen."""
    [base_outcome] = resolve_spell_outcomes(state, action, card)
    if not action.reaction_params:
        return [base_outcome]
    watcher, zone, payment = action.reaction_params
    return [SPELL_KILL_REACTIONS[watcher](base_outcome, zone, payment)]


# card_id -> (is_legal(state, action), effect(state, action) -> list[GameState],
#             generate_candidate_params(state))
SPELL_EFFECTS: dict[str, tuple[
    Callable[[GameState, PlaySpell], bool],
    Callable[[GameState, PlaySpell], list[GameState]],
    Callable[[GameState], list[tuple]],
]] = {
    RIDE_THE_WIND: (_ride_the_wind_is_legal, _ride_the_wind_effect, _ride_the_wind_candidates),
    VENGEANCE: (_vengeance_is_legal, _vengeance_effect, _vengeance_candidates),
    CHARM: (_charm_is_legal, _charm_effect, _charm_candidates),
    PRIMAL_STRENGTH: (_primal_strength_is_legal, _primal_strength_effect, _primal_strength_candidates),
    FLURRY_OF_BLADES: (_flurry_is_legal, _flurry_effect, _flurry_candidates),
    GUST: (_gust_is_legal, _gust_effect, _gust_candidates),
    SMOKE_SCREEN: (_smoke_screen_is_legal, _smoke_screen_effect, _smoke_screen_candidates),
    HEXTECH_RAY: (_single_battlefield_target_is_legal, _flat_damage_effect, _units_at_battlefields),
    FALLING_COMET: (_single_battlefield_target_is_legal, _flat_damage_effect, _units_at_battlefields),
    FALLING_STAR: (_falling_star_is_legal, _falling_star_effect, _falling_star_candidates),
    REBUKE: (_single_battlefield_target_is_legal, _rebuke_effect, _units_at_battlefields),
    GRAND_STRATEGEM: (_grand_strategem_is_legal, _grand_strategem_effect, lambda state: [()]),
    CLEAVE: (_any_unit_is_legal, _cleave_effect, _any_unit_candidates),
    SINGULARITY: (_singularity_is_legal, _singularity_effect, _singularity_candidates),
    BACK_TO_BACK: (_back_to_back_is_legal, _back_to_back_effect, _back_to_back_candidates),
    LAST_STAND: (_friendly_unit_is_legal, _last_stand_effect, _friendly_unit_candidates),
    UNCHECKED_POWER: (_unchecked_power_is_legal, _unchecked_power_effect, lambda state: [()]),
    CHALLENGE: (_challenge_is_legal, _challenge_effect, _challenge_candidates),
    EN_GARDE: (_friendly_unit_is_legal, _en_garde_effect, _friendly_unit_candidates),
    OVERT_OPERATION: (_overt_operation_is_legal, _overt_operation_effect, _overt_operation_candidates),
    MORBID_RETURN: (_morbid_return_is_legal, _morbid_return_effect, _morbid_return_candidates),
    THE_HARROWING: (_the_harrowing_is_legal, _the_harrowing_effect, _the_harrowing_candidates),
    SALVAGE: (_salvage_is_legal, _salvage_effect, _salvage_candidates),
}


def _caitlyn_is_legal(state: GameState, action: ActivateAbility) -> bool:
    """params = (target_instance_id,). "Exhaust: Deal damage equal to my
    Might to a unit at a battlefield. Use this ability only while I'm at
    a battlefield." No rune cost — just exhausting Caitlyn herself."""
    if len(action.params) != 1:
        return False
    located = find_unit_at_any_battlefield(state, action.source_id)
    if located is None:
        return False  # "only while I'm at a battlefield" — not usable from Base
    source, _ = located
    if source.controller != state.turn_player or source.exhausted:
        return False
    target_located = find_unit_at_any_battlefield(state, action.params[0])
    if target_located is None:
        return False
    # She prints no rune cost, but [Deflect] taxes any ability that
    # CHOOSES a unit — so against a Deflect target her payment goes from
    # None to exactly the owed runes, and an empty pool makes the ability
    # unusable on that target.
    tax = deflect_tax_for(state, CAITLYN_PATROLLING, action.params, state.turn_player)
    if _paid_rainbow(action.rune_payment) != tax:
        return False
    if action.rune_payment is not None:
        if action.rune_payment.energy_runes or action.rune_payment.power_runes:
            return False  # nothing but the tax is ever owed here
        if not payment_is_affordable(state.players[state.turn_player].runes, action.rune_payment):
            return False
    return True


def _caitlyn_effect(state: GameState, action: ActivateAbility) -> GameState:
    if action.rune_payment is not None:
        player = state.players[state.turn_player]
        state = replace_player(state, state.turn_player, dataclasses.replace(
            player, runes=consume_runes(player.runes, action.rune_payment)))
    source, source_bf_id = find_unit_at_any_battlefield(state, action.source_id)
    exhausted_source = dataclasses.replace(source, exhausted=True)
    bf = next(b for b in state.battlefields if b.battlefield_id == source_bf_id)
    state = replace_battlefield(state, dataclasses.replace(bf, units=(bf.units - {source}) | {exhausted_source}))

    target_id = action.params[0]
    _, target_bf_id = find_unit_at_any_battlefield(state, target_id)
    return combat.deal_damage_to_unit(state, target_bf_id, target_id, source.might)


def _caitlyn_candidates(state: GameState) -> list[tuple[int]]:
    """One candidate per unit present at any battlefield — Caitlyn's text
    doesn't restrict the target to enemies."""
    return [(u.instance_id,) for bf in state.battlefields
            for u in sorted(bf.units, key=lambda u: u.instance_id)]


def _sett_spend_buff_is_legal(state: GameState, action: ActivateAbility) -> bool:
    """params = (). "Spend my buff: Give me +4 Might this turn" — no
    target, no rune cost printed, and the cost IS the precondition: no
    buff to spend means the ability isn't there to activate."""
    if action.params != ():
        return False
    located = find_unit_anywhere(state, action.source_id)
    if located is None:
        return False
    source, _ = located
    if source.controller != state.turn_player or not source.buffed:
        return False
    return action.rune_payment is None  # nothing but the buff is ever owed


def _sett_spend_buff_effect(state: GameState, action: ActivateAbility) -> GameState:
    state = spend_buff(state, action.source_id)
    return _grant_might(state, action.source_id, 4)


def _sett_spend_buff_candidates(state: GameState) -> list[tuple]:
    return [()]


UDYR_WILDMAN = "ogn-157-298"  # "Spend my buff: Choose one you've not chosen this turn — [4 modes]."

# The four modes, exactly as printed, keyed by a short name that becomes
# params[0] and the entry recorded in UnitInstance.modes_chosen_this_turn.
UDYR_DEAL_2 = "deal2"       # "Deal 2 to a unit at a battlefield."
UDYR_STUN = "stun"          # "Stun a unit at a battlefield."
UDYR_READY = "ready"        # "Ready me."
UDYR_GANKING = "ganking"    # "Give me [Ganking] this turn."
UDYR_MODES = frozenset({UDYR_DEAL_2, UDYR_STUN, UDYR_READY, UDYR_GANKING})


def _record_mode_chosen(state: GameState, instance_id: int, mode: str) -> GameState:
    """Marks `mode` as picked this turn on Udyr — the bookkeeping his
    "not chosen this turn" restriction reads. A no-op if the unit no
    longer exists (its own "Deal 2" mode CAN target itself and, in a
    contrived case, kill it) — nothing is left to track on a dead unit,
    and there's no next activation for the restriction to matter to."""
    located = find_unit_anywhere(state, instance_id)
    if located is None:
        return state
    unit, zone = located
    if mode in unit.modes_chosen_this_turn:
        return state
    updated = dataclasses.replace(
        unit, modes_chosen_this_turn=unit.modes_chosen_this_turn | {mode})
    return _replace_unit(state, unit, zone, updated)


def _udyr_is_legal(state: GameState, action: ActivateAbility) -> bool:
    """params = (mode,) for Ready/Ganking, (mode, target_instance_id) for
    Deal 2/Stun, or (UDYR_STUN, target_instance_id, buff_target_id) when
    _stun_buff_choice_active holds for that target (Radiant Dawn present
    and the stunned unit is actually an enemy — Udyr's "a unit" is
    unrestricted-controller, unlike Leona's "an enemy unit," so this has
    to be checked per chosen target rather than assumed). The cost IS
    "spend my buff" (no rune cost printed, same precondition-as-cost
    shape as Sett's ability) — no buff, nothing to activate. "Choose one
    you've not chosen this turn" is enforced against this SPECIFIC Udyr's
    own modes_chosen_this_turn, since another Udyr (or this one re-buffed
    later) tracks its own set independently."""
    if action.rune_payment is not None or not action.params:
        return False
    mode = action.params[0]
    if mode not in UDYR_MODES:
        return False
    located = find_unit_anywhere(state, action.source_id)
    if located is None:
        return False
    source, _ = located
    if source.controller != state.turn_player or not source.buffed:
        return False
    if mode in source.modes_chosen_this_turn:
        return False
    if mode == UDYR_DEAL_2:
        if len(action.params) != 2:
            return False
        # "a unit at a battlefield" — not Base, not restricted to enemies
        # (same reading as Iron Ballista's identical "Deal 2" wording).
        return find_unit_at_any_battlefield(state, action.params[1]) is not None
    if mode == UDYR_STUN:
        if len(action.params) not in (2, 3):
            return False
        target_id = action.params[1]
        if find_unit_at_any_battlefield(state, target_id) is None:
            return False
        buff_active = _stun_buff_choice_active(state, source.controller, target_id)
        if len(action.params) != (3 if buff_active else 2):
            return False
        if buff_active:
            friendlies = _units_controlled_by(state, source.controller)
            if not any(u.instance_id == action.params[2] for u in friendlies):
                return False
        return True
    return len(action.params) == 1  # Ready / Ganking — no target


def _udyr_effect(state: GameState, action: ActivateAbility) -> GameState:
    mode = action.params[0]
    state = spend_buff(state, action.source_id)
    if mode == UDYR_DEAL_2:
        target_id = action.params[1]
        _, bf_id = find_unit_at_any_battlefield(state, target_id)
        state = combat.deal_damage_to_unit(state, bf_id, target_id, 2)
    elif mode == UDYR_STUN:
        state = stun_unit(state, action.params[1])
        if len(action.params) == 3:  # Radiant Dawn's mandatory buff choice
            state = apply_buff(state, action.params[2])
    elif mode == UDYR_READY:
        state = ready_unit(state, action.source_id)
    else:  # UDYR_GANKING
        state = grant_trait(state, action.source_id, "Ganking")
    return _record_mode_chosen(state, action.source_id, mode)


def _udyr_candidates(state: GameState) -> list[tuple]:
    """Instance-agnostic, like Caitlyn's/Iron Ballista's own candidate
    generators — the full universe of (mode[, target[, buff_target]])
    tuples regardless of which specific Udyr (or how much of his own
    state) will end up legal; is_legal filters per-instance from
    action.source_id, the same division search.legal_actions already
    relies on for every other unit ability. The controller for the
    Radiant Dawn check is state.turn_player: unlike an ATTACK_TRIGGERS
    entry, a unit's own ActivateAbility is only ever generated for units
    state.turn_player controls (search.legal_actions' `all_units` filter),
    so there's no Charm-redirect ambiguity here."""
    targets = [u.instance_id for bf in state.battlefields for u in sorted(bf.units, key=lambda u: u.instance_id)]
    controller = state.turn_player
    out = [(UDYR_DEAL_2, t) for t in targets]
    for t in targets:
        if _stun_buff_choice_active(state, controller, t):
            friendlies = sorted(_units_controlled_by(state, controller), key=lambda u: u.instance_id)
            out += [(UDYR_STUN, t, f.instance_id) for f in friendlies]
        else:
            out.append((UDYR_STUN, t))
    out += [(UDYR_READY,), (UDYR_GANKING,)]
    return out


# card_id -> (is_legal(state, action), effect(state, action), generate_candidate_params(state))
ABILITY_EFFECTS: dict[str, tuple[
    Callable[[GameState, ActivateAbility], bool],
    Callable[[GameState, ActivateAbility], GameState],
    Callable[[GameState], list[tuple]],
]] = {
    CAITLYN_PATROLLING: (_caitlyn_is_legal, _caitlyn_effect, _caitlyn_candidates),
    SETT_BRAWLER: (_sett_spend_buff_is_legal, _sett_spend_buff_effect, _sett_spend_buff_candidates),
    SETT_BRAWLER_ALT: (_sett_spend_buff_is_legal, _sett_spend_buff_effect, _sett_spend_buff_candidates),
    VI_DESTRUCTIVE: (_vi_destructive_is_legal, _vi_destructive_effect, _vi_destructive_candidates),
    UDYR_WILDMAN: (_udyr_is_legal, _udyr_effect, _udyr_candidates),
}


def is_legal_activate_ability(state: GameState, action: ActivateAbility) -> bool:
    entry = ABILITY_EFFECTS.get(action.ability_id)
    if entry is None:
        return False
    is_legal_effect, _, _ = entry
    return is_legal_effect(state, action)


def apply_ability(state: GameState, action: ActivateAbility) -> GameState:
    _, effect, _ = ABILITY_EFFECTS[action.ability_id]
    return effect(state, action)


def is_legal_play_spell(state: GameState, action: PlaySpell, card: CardDef) -> bool:
    if not is_legal_play_spell_cost(state, action, card):
        return False
    # The [Deflect] tax for whatever this spell chooses must be paid
    # exactly — is_legal_play_spell_cost already confirmed the runes are
    # affordable, but only the per-card registry knows what's targeted.
    if _paid_rainbow(action.rune_payment) != deflect_tax_for(
            state, action.card_id, action.params, state.turn_player):
        return False
    entry = SPELL_EFFECTS.get(action.card_id)
    if entry is None:
        return False  # unregistered spell — can't validate or apply its effect
    is_legal_effect, _, _ = entry
    return is_legal_effect(state, action)


def resolve_spell_outcomes(state: GameState, action: PlaySpell, card: CardDef) -> list[GameState]:
    """All possible resulting states for `action` — a single-element list
    for a deterministic spell (Ride The Wind, Vengeance), multiple for one
    whose effect can cause combat (Charm) — same shape as
    resolve_unit_play_trigger_outcomes below, and for the same reason."""
    state_after_cost = apply_play_spell_cost(state, action)
    _, effect, _ = SPELL_EFFECTS[action.card_id]
    return effect(state_after_cost, action)


# --- Unit "when you play me" triggers -----------------------------------
#
# Registered per card_id, same shape as SPELL_EFFECTS/ABILITY_EFFECTS but
# the effect can return MULTIPLE outcomes (a list[GameState]) since a
# trigger that moves an enemy unit onto ground we hold causes combat with
# US as Defender — the one case design/09-combat-resolution.md flagged as
# written generically but not reachable through real action generation
# yet. This is what makes it reachable: many "when played" cards will
# follow this same shape.


def _blitzcrank_is_legal(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    """trigger_params = () to decline, or (enemy_instance_id,) /
    (enemy_instance_id, our_assignment) if moving that unit in causes
    combat (checked against the board as it will be AFTER Blitzcrank is
    placed — he's always one of the units at target_zone by then, so
    introducing any enemy unit there always triggers combat in practice,
    but this is written to only assume that when it's actually true).
    Needs the real `card` (not a stub) since Blitzcrank's own Might
    contributes to the defending side's pool once he's placed.
    """
    if not action.trigger_params:
        return True
    if action.target_zone == "base":
        return False  # "When you play me to a BATTLEFIELD" — no trigger from a Base play
    enemy_id = action.trigger_params[0]
    located = find_unit_at_any_battlefield(state, enemy_id)
    if located is None:
        return False
    unit, zone = located
    if unit.controller == state.turn_player or zone == action.target_zone:
        return False
    state_after_play = apply_play_unit(state, dataclasses.replace(action, trigger_params=()), card)
    if combat.is_combat_triggered(state_after_play, unit, action.target_zone):
        if len(action.trigger_params) != 2:
            return False
        our_assignment = action.trigger_params[1]
        return our_assignment in combat.our_assignment_options(state_after_play, unit, action.target_zone)
    return len(action.trigger_params) == 1


def _blitzcrank_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    if not action.trigger_params:
        return [state_after_play]
    enemy_id = action.trigger_params[0]
    unit, from_zone = find_unit_at_any_battlefield(state_after_play, enemy_id)
    to_zone = action.target_zone

    # An effect-granted move doesn't exhaust the unit unless the card says
    # so, and Blitzcrank's text doesn't — so the redirected unit keeps
    # whatever exhaustion state it already had (this previously forced
    # exhausted=True, which was wrong).
    if combat.is_combat_triggered(state_after_play, unit, to_zone):
        our_assignment = action.trigger_params[1]
        outcomes = combat.enumerate_combat_outcomes(state_after_play, unit, from_zone, to_zone,
                                                     our_assignment, exhausted_after=unit.exhausted)
        outcomes = [scoring.resolve_control_change(state_after_play, o, to_zone) for o in outcomes]
        return [apply_move_triggers(o, enemy_id) for o in outcomes]

    moved = relocate_unit(state_after_play, enemy_id, from_zone, to_zone, exhausted_after=unit.exhausted)
    moved = scoring.resolve_control_change(state_after_play, moved, to_zone)
    return [apply_move_triggers(moved, enemy_id)]


def _blitzcrank_candidates(state: GameState, base_action: PlayUnit, card: CardDef) -> list[tuple]:
    """base_action is the plain (trigger_params=()) PlayUnit already
    generated for Blitzcrank; this adds the "use the trigger" variants —
    one per enemy unit elsewhere on the board, further split by our
    assignment choice if redirecting it in causes combat (it always does
    in practice, since Blitzcrank himself is at target_zone by then)."""
    if base_action.target_zone == "base":
        return []  # "When you play me to a BATTLEFIELD" — doesn't trigger when played to Base
    state_after_play = apply_play_unit(state, base_action, card)
    candidates: list[tuple] = []
    for bf in state.battlefields:
        if bf.battlefield_id == base_action.target_zone:
            continue
        for unit in sorted(bf.units, key=lambda u: u.instance_id):
            if unit.controller == state.turn_player:
                continue
            if combat.is_combat_triggered(state_after_play, unit, base_action.target_zone):
                for our_assignment in combat.our_assignment_options(state_after_play, unit, base_action.target_zone):
                    candidates.append((unit.instance_id, our_assignment))
            else:
                candidates.append((unit.instance_id,))
    return candidates


FAITHFUL_MANUFACTOR = "ogn-211-298"  # When you play me, play a 1 Might Recruit unit token here.
VANGUARD_CAPTAIN = "ogn-218-298"  # [Legion] When you play me, play two 1 Might Recruit unit tokens
# here. (Get the effect if you've played another card this turn.)
WHITEFLAME_PROTECTOR = "ogn-082-298"  # "When you play me, give a unit +8 Might this turn."
DANGEROUS_DUO = "ogn-016-298"  # [Legion] "When you play me, give a unit +2 Might this turn."
FIRST_MATE = "ogn-132-298"  # "When you play me, ready another unit."
KINKOU_MONK = "ogn-141-298"  # "When you play me, buff up to two other friendly units."
MADDENED_MARAUDER = "ogn-191-298"  # [Tank] "When you play me, move a unit from a battlefield to its base."
RIPTIDE_REX = "ogn-092-298"  # "When you play me, deal 6 to an enemy unit at a battlefield."
HARNESSED_DRAGON = "ogn-234-298"  # "When you play me, kill an enemy unit."
PIT_ROOKIE = "ogn-136-298"  # "When you play me, buff another friendly unit."
TRIFARIAN_GLORYSEEKER = "ogn-217-298"  # [Legion] "When you play me, buff me."
PEAK_GUARDIAN = "ogn-223-298"  # "When you play me, buff me. Then, if I am at a battlefield, buff all other friendly units there."
RECRUIT_TOKEN = "ogn-271-298"  # one of three same-stat printings (see card_pool.py); this one
# picked as the canonical id for tokens minted by card effects.
RECRUIT_TOKEN_CARD = CardDef(card_id=RECRUIT_TOKEN, card_type="Unit", energy_cost=0,
                              power_cost=0, might=1, keywords=frozenset())

# card_ids whose "when you play me" trigger has NO decision to make — no
# target, no "you may." legal_actions() (search.py) withholds the bare
# trigger_params=() PlayUnit for these: offering "play it WITHOUT minting
# the token" as a separate legal move would be wrong, since the card's own
# text isn't optional. Contrast with Blitzcrank/Zaunite Bouncer, where
# trigger_params=() legitimately means "decline."
MANDATORY_PLAY_TRIGGERS = frozenset({FAITHFUL_MANUFACTOR, VANGUARD_CAPTAIN, WHITEFLAME_PROTECTOR,
                                     PIT_ROOKIE, TRIFARIAN_GLORYSEEKER, PEAK_GUARDIAN,
                                     RIPTIDE_REX, HARNESSED_DRAGON, DANGEROUS_DUO,
                                     FIRST_MATE, KINKOU_MONK, CARNIVOROUS_SNAPVINE,
                                     SETT_BRAWLER, SETT_BRAWLER_ALT, CEMETERY_ATTENDANT})


def _charm_deflect_targets(state: GameState, params: tuple) -> list[tuple]:
    located = find_unit_at_any_battlefield(state, params[0]) if params else None
    return [located] if located else []


def _single_target_anywhere(state: GameState, params: tuple) -> list[tuple]:
    located = find_unit_anywhere(state, params[0]) if params else None
    return [located] if located else []


def _single_target_at_battlefield(state: GameState, params: tuple) -> list[tuple]:
    located = find_unit_at_any_battlefield(state, params[0]) if params else None
    return [located] if located else []


def deflect_tax_for(state: GameState, card_id: str, params: tuple, chooser: int) -> int:
    """Total [Deflect] tax `chooser` owes to take the action described by
    `card_id`/`params` against the board in `state`. Zero for anything
    with no registered targets, and for targets the chooser controls."""
    finder = DEFLECT_TARGETS.get(card_id)
    if finder is None:
        return 0
    return sum(traits.deflect_tax(state, unit, zone, chooser)
               for unit, zone in finder(state, params))


def _paid_rainbow(payment) -> int:
    return len(payment.rainbow_runes) if payment is not None else 0


def legion_condition_met(state_after_play: GameState) -> bool:
    """[Legion] — "Get the effect if you've played another card this turn."
    Shared by every Legion card; only the gate is shared, since the
    printed effects differ (tokens, a Might buff, a cost reduction).

    Call this from a "when you play me" EFFECT, i.e. after
    apply_play_unit has already counted the Legion card's own play — so
    "another card" means a count of at least 2, not at least 1. A
    cost-time Legion (Noxus Hopeful's "I cost 2 less") is evaluated
    BEFORE that increment and would need the > 0 threshold instead; no
    such card is in the pool, and this helper is not it.
    """
    return state_after_play.cards_played_this_turn > 1


def _mint_recruit_tokens(state: GameState, zone: str, controller: int, count: int) -> GameState:
    for _ in range(count):
        state = mint_token_unit(state, RECRUIT_TOKEN_CARD, controller, zone)
    return state


def _faithful_manufactor_is_legal(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    """No target/choice — trigger_params is a fixed sentinel marking "the
    (only) triggered form," never empty (see MANDATORY_PLAY_TRIGGERS)."""
    return action.trigger_params == ("mint",)


def _faithful_manufactor_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    return [_mint_recruit_tokens(state_after_play, action.target_zone, state_after_play.turn_player, 1)]


def _faithful_manufactor_candidates(state: GameState, base_action: PlayUnit, card: CardDef) -> list[tuple]:
    return [("mint",)]


def _vanguard_captain_is_legal(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    return action.trigger_params == ("mint",)


def _vanguard_captain_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    """No tokens at all if Legion's condition fails — it isn't "one token
    instead of two," it's the whole effect being conditional. See
    legion_condition_met for the off-by-one the shared gate handles."""
    count = 2 if legion_condition_met(state_after_play) else 0
    return [_mint_recruit_tokens(state_after_play, action.target_zone, state_after_play.turn_player, count)]


def _vanguard_captain_candidates(state: GameState, base_action: PlayUnit, card: CardDef) -> list[tuple]:
    return [("mint",)]


def _whiteflame_is_legal(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    """trigger_params = (target_instance_id,). Mandatory — no "you may" —
    but unlike Faithful Manufactor it still CHOOSES, so it can't use the
    parameterless sentinel. "A unit" is unrestricted: either player's,
    anywhere, same as Primal Strength's identical wording.

    The target has to be resolved against the board as it will be AFTER
    this card is placed, since Whiteflame itself is a legal target for its
    own buff."""
    if len(action.trigger_params) != 1:
        return False
    state_after_play = apply_play_unit(state, dataclasses.replace(
        action, trigger_params=(), trigger_payment=None), card)
    return find_unit_anywhere(state_after_play, action.trigger_params[0]) is not None


def _whiteflame_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    return [_grant_might(state_after_play, action.trigger_params[0], 8)]


def _whiteflame_candidates(state: GameState, base_action: PlayUnit, card: CardDef) -> list[tuple]:
    state_after_play = apply_play_unit(state, base_action, card)
    candidates = []
    for player in state_after_play.players:
        candidates += [(u.instance_id,) for u in sorted(player.base_units, key=lambda u: u.instance_id)]
    for bf in state_after_play.battlefields:
        candidates += [(u.instance_id,) for u in sorted(bf.units, key=lambda u: u.instance_id)]
    return candidates


# --- Buff-on-play triggers ------------------------------------------------
#
# All three are mandatory. Only Pit Rookie chooses; the other two name
# their own target, so they take the parameterless ("buff",) sentinel for
# the same reason the token minters do — the dispatch in search._dfs keys
# off trigger_params being non-empty, so a genuinely choiceless mandatory
# trigger still needs SOMETHING there to be routed at all.


def _played_unit(state_after_play: GameState, action: PlayUnit):
    """The unit this PlayUnit just created — the highest instance_id, since
    next_instance_id hands them out in order."""
    candidates = [u for p in state_after_play.players for u in p.base_units]
    candidates += [u for bf in state_after_play.battlefields for u in bf.units]
    return max(candidates, key=lambda u: u.instance_id)


def _pit_rookie_is_legal(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    """trigger_params = (target_instance_id,). "Another friendly unit" —
    ours, and not itself."""
    if len(action.trigger_params) != 1:
        return False
    state_after_play = apply_play_unit(state, dataclasses.replace(
        action, trigger_params=(), trigger_payment=None), card)
    if action.trigger_params[0] == _played_unit(state_after_play, action).instance_id:
        return False  # "another"
    located = find_unit_anywhere(state_after_play, action.trigger_params[0])
    return located is not None and located[0].controller == state.turn_player


def _pit_rookie_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    return [apply_buff(state_after_play, action.trigger_params[0])]


def _pit_rookie_candidates(state: GameState, base_action: PlayUnit, card: CardDef) -> list[tuple]:
    state_after_play = apply_play_unit(state, base_action, card)
    played = _played_unit(state_after_play, base_action).instance_id
    ours = [u for u in state_after_play.players[state.turn_player].base_units]
    ours += [u for bf in state_after_play.battlefields for u in bf.units
             if u.controller == state.turn_player]
    return [(u.instance_id,) for u in sorted(ours, key=lambda u: u.instance_id)
            if u.instance_id != played]


def _self_buff_is_legal(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    return action.trigger_params == ("buff",)


def _self_buff_candidates(state: GameState, base_action: PlayUnit, card: CardDef) -> list[tuple]:
    return [("buff",)]


def _gloryseeker_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    """[Legion] gates the whole effect — no buff at all when the condition
    fails, rather than a smaller one."""
    if not legion_condition_met(state_after_play):
        return [state_after_play]
    return [apply_buff(state_after_play, _played_unit(state_after_play, action).instance_id)]


def _peak_guardian_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    """"Buff me. Then, if I am at a battlefield, buff all other friendly
    units there." The second half is conditional on where it landed, so a
    Peak Guardian played to Base buffs only itself."""
    me = _played_unit(state_after_play, action)
    state = apply_buff(state_after_play, me.instance_id)
    if action.target_zone != "base":
        bf = next(b for b in state.battlefields if b.battlefield_id == action.target_zone)
        for unit in sorted(bf.units, key=lambda u: u.instance_id):
            if unit.controller == me.controller and unit.instance_id != me.instance_id:
                state = apply_buff(state, unit.instance_id)
    return [state]


def _sett_played_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    """"When I'm played... buff me" — unconditional, unlike Gloryseeker's
    [Legion]-gated version of the same shape. The "when I conquer" half of
    Sett's text is a different trigger entirely (engine/conquer.py), fired
    from scoring.resolve_control_change rather than from here."""
    return [apply_buff(state_after_play, _played_unit(state_after_play, action).instance_id)]


def _enemy_at_battlefield_is_legal(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    """Shared by both: a mandatory trigger choosing one ENEMY unit at a
    battlefield, resolved against the board as it will be after this card
    lands."""
    if len(action.trigger_params) != 1:
        return False
    state_after_play = apply_play_unit(state, dataclasses.replace(
        action, trigger_params=(), trigger_payment=None), card)
    located = find_unit_at_any_battlefield(state_after_play, action.trigger_params[0])
    return located is not None and located[0].controller != state.turn_player


def _enemy_at_battlefield_candidates(state: GameState, base_action: PlayUnit, card: CardDef) -> list[tuple]:
    state_after_play = apply_play_unit(state, base_action, card)
    return [(u.instance_id,) for bf in state_after_play.battlefields
            for u in sorted(bf.units, key=lambda u: u.instance_id)
            if u.controller != state.turn_player]


def _riptide_rex_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    _, bf_id = find_unit_at_any_battlefield(state_after_play, action.trigger_params[0])
    return [combat.deal_damage_to_unit(state_after_play, bf_id, action.trigger_params[0], 6)]


def _harnessed_dragon_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    return [kill_unit(state_after_play, action.trigger_params[0])]


def _dangerous_duo_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    """[Legion] gates the whole effect, so with no prior card this turn the
    Duo is a plain body."""
    if not legion_condition_met(state_after_play):
        return [state_after_play]
    return [_grant_might(state_after_play, action.trigger_params[0], 2)]


def _first_mate_is_legal(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    """"Another unit" — any unit but itself, either player's. Readying an
    ENEMY unit is legal and merely unwise, so it isn't restricted."""
    if len(action.trigger_params) != 1:
        return False
    state_after_play = apply_play_unit(state, dataclasses.replace(
        action, trigger_params=(), trigger_payment=None), card)
    if action.trigger_params[0] == _played_unit(state_after_play, action).instance_id:
        return False
    return find_unit_anywhere(state_after_play, action.trigger_params[0]) is not None


def _first_mate_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    return [ready_unit(state_after_play, action.trigger_params[0])]


def _other_unit_candidates(state: GameState, base_action: PlayUnit, card: CardDef) -> list[tuple]:
    state_after_play = apply_play_unit(state, base_action, card)
    played = _played_unit(state_after_play, base_action).instance_id
    out = []
    for player in state_after_play.players:
        out += [(u.instance_id,) for u in sorted(player.base_units, key=lambda u: u.instance_id)]
    for bf in state_after_play.battlefields:
        out += [(u.instance_id,) for u in sorted(bf.units, key=lambda u: u.instance_id)]
    return [t for t in out if t[0] != played]


def _kinkou_monk_is_legal(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    """"Up to two OTHER FRIENDLY units" — zero, one or two, distinct, ours,
    never itself."""
    if len(action.trigger_params) > 2 or len(set(action.trigger_params)) != len(action.trigger_params):
        return False
    state_after_play = apply_play_unit(state, dataclasses.replace(
        action, trigger_params=(), trigger_payment=None), card)
    played = _played_unit(state_after_play, action).instance_id
    for target in action.trigger_params:
        if target == played:
            return False
        located = find_unit_anywhere(state_after_play, target)
        if located is None or located[0].controller != state.turn_player:
            return False
    return True


def _kinkou_monk_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    for target in action.trigger_params:
        state_after_play = apply_buff(state_after_play, target)
    return [state_after_play]


def _kinkou_monk_candidates(state: GameState, base_action: PlayUnit, card: CardDef) -> list[tuple]:
    state_after_play = apply_play_unit(state, base_action, card)
    played = _played_unit(state_after_play, base_action).instance_id
    ours = [u.instance_id for u in sorted(state_after_play.players[state.turn_player].base_units,
                                           key=lambda u: u.instance_id) if u.instance_id != played]
    ours += [u.instance_id for bf in state_after_play.battlefields
             for u in sorted(bf.units, key=lambda u: u.instance_id)
             if u.controller == state.turn_player and u.instance_id != played]
    out: list[tuple] = [()]
    out += [(a,) for a in ours]
    out += [(a, b) for i, a in enumerate(ours) for b in ours[i + 1:]]
    return out


WILDCLAW_SHAMAN = "ogn-147-298"  # "When you play me, you may spend a buff to buff me and ready me."


def _wildclaw_shaman_is_legal(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    """trigger_params = () to decline, or (buffed_instance_id,) naming the
    friendly unit whose buff is spent as the cost. Wildclaw Shaman itself
    can never be a legal choice: it has just entered and starts unbuffed,
    so "must currently be buffed" already rules out self-targeting without
    a separate check."""
    if not action.trigger_params:
        return True
    if len(action.trigger_params) != 1:
        return False
    state_after_play = apply_play_unit(state, dataclasses.replace(
        action, trigger_params=(), trigger_payment=None), card)
    located = find_unit_anywhere(state_after_play, action.trigger_params[0])
    return located is not None and located[0].controller == state.turn_player and located[0].buffed


def _wildclaw_shaman_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    if not action.trigger_params:
        return [state_after_play]
    spent = spend_buff(state_after_play, action.trigger_params[0])
    me = _played_unit(spent, action)
    return [ready_unit(apply_buff(spent, me.instance_id), me.instance_id)]


def _wildclaw_shaman_candidates(state: GameState, base_action: PlayUnit, card: CardDef) -> list[tuple]:
    state_after_play = apply_play_unit(state, base_action, card)
    ours = [u.instance_id for u in sorted(state_after_play.players[state.turn_player].base_units,
                                           key=lambda u: u.instance_id) if u.buffed]
    ours += [u.instance_id for bf in state_after_play.battlefields
             for u in sorted(bf.units, key=lambda u: u.instance_id)
             if u.controller == state.turn_player and u.buffed]
    return [()] + [(a,) for a in ours]


# NOT REGISTERED — blocked on the zone model, see engine/coverage.py.
# "Move a unit from a battlefield to its base" is fine for our own units
# but unrepresentable for an enemy's: Zone is "base" or a battlefield id,
# with no way to say WHOSE base, so an enemy unit has nowhere to go. Kept
# here rather than deleted because everything except the destination is
# correct and will be reusable the day Zone distinguishes the two bases.
def _marauder_is_legal(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    """"Move A UNIT from a battlefield to its base" — either player's, and
    its OWN base, which for an enemy unit means off our board entirely."""
    if len(action.trigger_params) != 1:
        return False
    state_after_play = apply_play_unit(state, dataclasses.replace(
        action, trigger_params=(), trigger_payment=None), card)
    return find_unit_at_any_battlefield(state_after_play, action.trigger_params[0]) is not None


def _marauder_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    target = action.trigger_params[0]
    unit, from_zone = find_unit_at_any_battlefield(state_after_play, target)
    moved = _move_enemy_unit_no_combat(state_after_play, unit, from_zone, "base")         if unit.controller != state_after_play.turn_player         else relocate_unit(state_after_play, target, from_zone, "base",
                            exhausted_after=unit.exhausted)
    moved = scoring.resolve_control_change(state_after_play, moved, from_zone)
    return [apply_move_triggers(moved, target)]


def _marauder_candidates(state: GameState, base_action: PlayUnit, card: CardDef) -> list[tuple]:
    state_after_play = apply_play_unit(state, base_action, card)
    played = _played_unit(state_after_play, base_action).instance_id
    return [(u.instance_id,) for bf in state_after_play.battlefields
            for u in sorted(bf.units, key=lambda u: u.instance_id)
            if u.instance_id != played]


ZAUNITE_BOUNCER = "ogn-188-298"  # When you play me, return another unit at a battlefield to its owner's hand.


def _zaunite_bouncer_is_legal(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    """trigger_params = () to decline, or (target_instance_id,) — any
    OTHER unit at a battlefield (either controller's; not restricted to
    enemies, and not Base — "at a battlefield" only). Tank doesn't gate
    this (Tank only orders Combat Damage Step assignment). `state` is
    still pre-play here, so next_instance_id(state) predicts the id
    ZAUNITE_BOUNCER itself is about to get — used to rule out
    self-targeting without needing to re-locate "the unit just played"
    after the fact."""
    if not action.trigger_params:
        return True
    if len(action.trigger_params) != 1:
        return False
    target_id = action.trigger_params[0]
    if target_id == next_instance_id(state):
        return False  # "another unit" — not itself
    state_after_play = apply_play_unit(state, dataclasses.replace(action, trigger_params=()), card)
    return find_unit_at_any_battlefield(state_after_play, target_id) is not None


def _zaunite_bouncer_effect(state_after_play: GameState, action: PlayUnit) -> list[GameState]:
    if not action.trigger_params:
        return [state_after_play]
    target_id = action.trigger_params[0]
    _, bf_id = find_unit_at_any_battlefield(state_after_play, target_id)
    return [return_unit_to_hand(state_after_play, bf_id, target_id)]


def _zaunite_bouncer_candidates(state: GameState, base_action: PlayUnit, card: CardDef) -> list[tuple]:
    """One candidate per OTHER unit currently at any battlefield —
    ZAUNITE_BOUNCER's own placement doesn't restrict which battlefield
    counts, unlike Blitzcrank's "to a battlefield" text."""
    played_id = next_instance_id(state)
    state_after_play = apply_play_unit(state, base_action, card)
    candidates: list[tuple] = []
    for bf in state_after_play.battlefields:
        for unit in sorted(bf.units, key=lambda u: u.instance_id):
            if unit.instance_id == played_id:
                continue  # "another unit" — not itself
            candidates.append((unit.instance_id,))
    return candidates


# card_id -> (is_legal(state, action, card), effect(state_after_play, action) -> list[GameState],
#             generate_candidate_params(state, base_action, card))
UNIT_PLAY_TRIGGERS: dict[str, tuple[
    Callable[[GameState, PlayUnit, CardDef], bool],
    Callable[[GameState, PlayUnit], list[GameState]],
    Callable[[GameState, PlayUnit, CardDef], list[tuple]],
]] = {
    BLITZCRANK_IMPASSIVE: (_blitzcrank_is_legal, _blitzcrank_effect, _blitzcrank_candidates),
    ZAUNITE_BOUNCER: (_zaunite_bouncer_is_legal, _zaunite_bouncer_effect, _zaunite_bouncer_candidates),
    FAITHFUL_MANUFACTOR: (_faithful_manufactor_is_legal, _faithful_manufactor_effect,
                           _faithful_manufactor_candidates),
    VANGUARD_CAPTAIN: (_vanguard_captain_is_legal, _vanguard_captain_effect, _vanguard_captain_candidates),
    WHITEFLAME_PROTECTOR: (_whiteflame_is_legal, _whiteflame_effect, _whiteflame_candidates),
    PIT_ROOKIE: (_pit_rookie_is_legal, _pit_rookie_effect, _pit_rookie_candidates),
    TRIFARIAN_GLORYSEEKER: (_self_buff_is_legal, _gloryseeker_effect, _self_buff_candidates),
    PEAK_GUARDIAN: (_self_buff_is_legal, _peak_guardian_effect, _self_buff_candidates),
    RIPTIDE_REX: (_enemy_at_battlefield_is_legal, _riptide_rex_effect, _enemy_at_battlefield_candidates),
    HARNESSED_DRAGON: (_enemy_at_battlefield_is_legal, _harnessed_dragon_effect,
                        _enemy_at_battlefield_candidates),
    DANGEROUS_DUO: (_whiteflame_is_legal, _dangerous_duo_effect, _whiteflame_candidates),
    FIRST_MATE: (_first_mate_is_legal, _first_mate_effect, _other_unit_candidates),
    KINKOU_MONK: (_kinkou_monk_is_legal, _kinkou_monk_effect, _kinkou_monk_candidates),
    CARNIVOROUS_SNAPVINE: (_enemy_at_battlefield_is_legal, _snapvine_effect,
                            _enemy_at_battlefield_candidates),
    SETT_BRAWLER: (_self_buff_is_legal, _sett_played_effect, _self_buff_candidates),
    SETT_BRAWLER_ALT: (_self_buff_is_legal, _sett_played_effect, _self_buff_candidates),
    WILDCLAW_SHAMAN: (_wildclaw_shaman_is_legal, _wildclaw_shaman_effect, _wildclaw_shaman_candidates),
    CEMETERY_ATTENDANT: (_cemetery_attendant_is_legal, _cemetery_attendant_effect,
                          _cemetery_attendant_candidates),
    SOULGORGER: (_soulgorger_is_legal, _soulgorger_effect, _soulgorger_candidates),
    SPECTRAL_MATRON: (_spectral_matron_is_legal, _spectral_matron_effect, _spectral_matron_candidates),
}


# --- Gear "when you play this" triggers -----------------------------------
#
# Same shape as UNIT_PLAY_TRIGGERS, mirrored onto PlayGear (which gained
# its own trigger_params field for this). apply_play_gear's docstring
# already anticipated this split — board mechanics there, trigger effects
# here — the same way apply_play_unit leaves triggers to this module.

FORGE_OF_THE_FUTURE = "ogn-212-298"  # "When you play this, play a 1 Might Recruit unit token at your base."


def _forge_of_the_future_is_legal(state: GameState, action: PlayGear, card: CardDef) -> bool:
    """No target/choice — trigger_params is a fixed sentinel, never empty
    (see MANDATORY_GEAR_TRIGGERS)."""
    return action.trigger_params == ("mint",)


def _forge_of_the_future_effect(state_after_play: GameState, action: PlayGear) -> list[GameState]:
    return [_mint_recruit_tokens(state_after_play, "base", state_after_play.turn_player, 1)]


def _forge_of_the_future_candidates(state: GameState, base_action: PlayGear, card: CardDef) -> list[tuple]:
    return [("mint",)]


# card_ids whose "when you play this" Gear trigger has no decision to
# make — the PlayGear analogue of MANDATORY_PLAY_TRIGGERS. legal_actions()
# withholds the bare trigger_params=() form for these.
MANDATORY_GEAR_TRIGGERS = frozenset({FORGE_OF_THE_FUTURE})

# card_id -> (is_legal(state, action, card), effect(state_after_play, action) -> list[GameState],
#             generate_candidate_params(state, base_action, card))
GEAR_PLAY_TRIGGERS: dict[str, tuple[
    Callable[[GameState, PlayGear, CardDef], bool],
    Callable[[GameState, PlayGear], list[GameState]],
    Callable[[GameState, PlayGear, CardDef], list[tuple]],
]] = {
    FORGE_OF_THE_FUTURE: (_forge_of_the_future_is_legal, _forge_of_the_future_effect,
                           _forge_of_the_future_candidates),
}


def is_legal_gear_play_trigger(state: GameState, action: PlayGear, card: CardDef) -> bool:
    if not is_legal_play_gear(state, action, card):
        return False
    entry = GEAR_PLAY_TRIGGERS.get(action.card_id)
    if entry is None:
        return action.trigger_params == ()
    is_legal_trigger, _, _ = entry
    return is_legal_trigger(state, action, card)


def resolve_gear_play_trigger_outcomes(state: GameState, action: PlayGear, card: CardDef) -> list[GameState]:
    state_after_play = apply_play_gear(state, action, card)
    _, effect, _ = GEAR_PLAY_TRIGGERS[action.card_id]
    return effect(state_after_play, action)


# --- "When I attack" triggers ---------------------------------------------
#
# RULES ANSWER (project owner, 2026-09-17): if an attack trigger kills the
# defender before the Combat Damage Step, that defender is removed from
# combat entirely and deals no combat damage. Enumerating damage-assignment
# options against the pre-trigger defender list would be wrong — it could
# offer an assignment against a unit no longer there, or (worse) let a
# defender that should already be dead still contribute Might to a pool
# that kills the attacker back.
#
# The fix reuses the showdown mechanism rather than inventing a second one:
# a Standard Move whose mover has a registered entry here is forced through
# EnterShowdown (see search._board_actions_with_showdown_entries) with
# ShowdownState.attack_trigger_resolved=False. legal_actions() then offers
# ONLY this trigger's resolution — no spells, no ResolveShowdown — until it
# fires (search._showdown_actions). Once it does,
# combat.showdown_assignment_options reads the CURRENT board, which already
# reflects whatever the trigger killed: a removed defender simply isn't
# among "ours"/"theirs" any more, so it can neither be assigned to nor
# contribute to anyone's pool. No change to enumerate_assignments or
# resolve_showdown was needed — the restructuring is entirely about WHEN
# the trigger fires relative to assignment enumeration, not how damage
# assignment itself works.
#
# Every trigger registered here is MANDATORY (no printed "you may"), so
# unlike UNIT_PLAY_TRIGGERS there is no plain untriggered form to withhold —
# forcing the showdown IS withholding it, since the atomic ResolveCombat
# path (built from the pre-trigger board) is never offered at all for a
# mover with an entry here (search._board_actions_with_showdown_entries).
#
# None of the effects below can themselves cause a NEW combat (no move, no
# redirect), so each is deterministic — one resulting GameState, not a
# list — which is what lets apply_attack_trigger skip the AND-node
# machinery PlayUnit/PlaySpell triggers need.
ANIVIA_PRIMAL = "ogn-148-298"  # "When I attack, deal 3 to all enemy units here."
YASUO_REMORSEFUL = "ogn-076-298"  # "When I attack, deal damage equal to my Might to an enemy unit here."
YASUO_REMORSEFUL_ALT = "ogn-076a-298"  # same card, alternate art printing
CRACKSHOT_CORSAIR = "ogn-130-298"  # "When I attack, deal 1 to an enemy unit here."
DUNE_DRAKE = "ogn-131-298"  # "When I attack, give me +2 Might this turn if there is a ready enemy unit here."
LEONA_DETERMINED = "ogn-238-298"  # "[Shield] When I attack, stun an enemy unit here."
LEONA_DETERMINED_ALT = "ogn-238a-298"  # same card, alternate art printing

# Radiant Dawn (Legend): "When you stun one or more enemy units, buff a
# friendly unit." A passive observer keyed to a stun the Legend's OWN
# controller causes — same "you" convention as conquer.py/observers.py's
# own triggers (keyed to the acting unit's controller, not who the effect
# lands on). Checked by Legend identity rather than by which card did the
# stunning, so a second stunner card reuses this unchanged — the same
# "add a card, reuse the hook" shape those two modules already use.
RADIANT_DAWN = "ogn-261-298"
RADIANT_DAWN_NX = "ogn-306-298"  # same Legend, alternate printing
RADIANT_DAWN_STAR = "ogn-306-star-298"  # same Legend, alternate printing
STUN_OBSERVER_LEGENDS = frozenset({RADIANT_DAWN, RADIANT_DAWN_NX, RADIANT_DAWN_STAR})


def _stun_observer_present(state: GameState, controller: int) -> bool:
    legend = state.players[controller].legend
    return legend is not None and legend.card_id in STUN_OBSERVER_LEGENDS


def _units_controlled_by(state: GameState, controller: int) -> list:
    """Every unit `controller` has anywhere — Base plus every battlefield.
    Parametrized by controller rather than hardcoded to state.turn_player
    because an attack trigger's attacker isn't always us: Charm/
    Blitzcrank can redirect an ENEMY unit into combat, making THEM the
    Attacker for that trigger (combat.py's module docstring) — and it's
    the attacker's own controller whose Radiant Dawn (if any) would be
    watching, not necessarily state.turn_player's."""
    found = list(state.players[controller].base_units)
    for bf in state.battlefields:
        found.extend(u for u in bf.units if u.controller == controller)
    return found


def _stun_buff_choice_active(state: GameState, controller: int, stunned_target_id: int) -> bool:
    """Whether stunning `stunned_target_id` (as `controller`) should ALSO
    offer Radiant Dawn's mandatory buff choice: the observer must be
    present, the stunned unit must actually be an ENEMY of `controller`
    (Radiant Dawn's own text is "when you stun one or more ENEMY units" —
    Leona's target is always an enemy by her own text, but a future
    unrestricted-target stunner, e.g. Udyr's "stun A UNIT," is not), and a
    friendly unit must exist to receive it (unreachable otherwise, same
    "no fizzled no-op" convention as Harnessed Dragon against an empty
    board). The single shared gate every stunner's own is_legal/candidates
    calls, so Radiant Dawn's coverage doesn't quietly narrow the moment a
    second stunner exists."""
    if not _stun_observer_present(state, controller):
        return False
    target = find_unit_anywhere(state, stunned_target_id)
    if target is None or target[0].controller == controller:
        return False
    return bool(_units_controlled_by(state, controller))


def _attacker_and_battlefield(state: GameState, attacker_instance_id: int):
    """The attacking unit and the battlefield it's standing on, read off
    the open showdown rather than passed in — the trigger always resolves
    immediately after open_showdown, before anything else could have
    moved units in or out (see the registry's module comment)."""
    bf = next(b for b in state.battlefields if b.battlefield_id == state.showdown.battlefield_id)
    attacker = next(u for u in bf.units if u.instance_id == attacker_instance_id)
    return attacker, bf


def _enemy_units_here(attacker, bf) -> list:
    return [u for u in sorted(bf.units, key=lambda u: u.instance_id) if u.controller != attacker.controller]


def _anivia_is_legal(state: GameState, attacker_instance_id: int, trigger_params: tuple) -> bool:
    """No target, no choice — "all enemy units here" leaves nothing to
    parametrize, so trigger_params is the fixed sentinel used everywhere
    else in this codebase for a choiceless mandatory trigger."""
    return trigger_params == ("all",)


def _anivia_effect(state: GameState, attacker_instance_id: int, trigger_params: tuple) -> GameState:
    attacker, bf = _attacker_and_battlefield(state, attacker_instance_id)
    for enemy in _enemy_units_here(attacker, bf):
        # Each call re-fetches the battlefield fresh, so a unit an earlier
        # iteration already killed (or whose Deathknell removed something
        # else) is simply absent rather than double-hit.
        if find_unit_at_any_battlefield(state, enemy.instance_id) is not None:
            state = combat.deal_damage_to_unit(state, bf.battlefield_id, enemy.instance_id, 3)
    return state


def _anivia_candidates(state: GameState, attacker_instance_id: int) -> list[tuple]:
    return [("all",)]


def _single_enemy_here_is_legal(state: GameState, attacker_instance_id: int, trigger_params: tuple) -> bool:
    if len(trigger_params) != 1:
        return False
    attacker, bf = _attacker_and_battlefield(state, attacker_instance_id)
    target = next((u for u in bf.units if u.instance_id == trigger_params[0]), None)
    return target is not None and target.controller != attacker.controller


def _single_enemy_here_candidates(state: GameState, attacker_instance_id: int) -> list[tuple]:
    attacker, bf = _attacker_and_battlefield(state, attacker_instance_id)
    return [(u.instance_id,) for u in _enemy_units_here(attacker, bf)]


def _yasuo_remorseful_effect(state: GameState, attacker_instance_id: int, trigger_params: tuple) -> GameState:
    """Amount = the attacker's own EFFECTIVE Might (Assault included — it
    already applies to it as the attacker), read at the moment the
    trigger fires, which is before anything of this combat has changed
    it."""
    attacker, bf = _attacker_and_battlefield(state, attacker_instance_id)
    amount = traits.effective_might(state, attacker, bf.battlefield_id, "attacker")
    return combat.deal_damage_to_unit(state, bf.battlefield_id, trigger_params[0], amount)


# card_id -> flat damage dealt to the chosen enemy unit (Crackshot Corsair's
# own text is a fixed number, unlike Yasuo - Remorseful's dynamic one).
ATTACK_TRIGGER_FLAT_DAMAGE: dict[str, int] = {CRACKSHOT_CORSAIR: 1}


def _attack_trigger_flat_damage_effect(state: GameState, attacker_instance_id: int,
                                        trigger_params: tuple) -> GameState:
    attacker, bf = _attacker_and_battlefield(state, attacker_instance_id)
    amount = ATTACK_TRIGGER_FLAT_DAMAGE[attacker.card_id]
    return combat.deal_damage_to_unit(state, bf.battlefield_id, trigger_params[0], amount)


def _dune_drake_is_legal(state: GameState, attacker_instance_id: int, trigger_params: tuple) -> bool:
    return trigger_params == ("buff",)


def _dune_drake_candidates(state: GameState, attacker_instance_id: int) -> list[tuple]:
    return [("buff",)]


def _dune_drake_effect(state: GameState, attacker_instance_id: int, trigger_params: tuple) -> GameState:
    """"+2 Might this turn IF there is a ready enemy unit here" — the
    trigger always happens; whether it does anything is conditional. Read
    at the moment it fires, same as everything else here — an enemy that
    was ready when the attack began and gets exhausted afterwards (nothing
    in this cluster does that) wouldn't retroactively undo an already-
    granted buff, matching how every other "this turn" grant in this
    codebase works (see traits.py's module docstring)."""
    attacker, bf = _attacker_and_battlefield(state, attacker_instance_id)
    if any(u.controller != attacker.controller and not u.exhausted for u in bf.units):
        return _grant_might(state, attacker_instance_id, 2)
    return state


def _leona_is_legal(state: GameState, attacker_instance_id: int, trigger_params: tuple) -> bool:
    """params = (enemy_target_id,), or (enemy_target_id, buff_target_id)
    exactly when _stun_buff_choice_active holds for that target (Radiant
    Dawn present, with a friendly unit available to receive the buff).
    This engine has no resolution stack, so a compound MANDATORY trigger's
    whole choice has to live in one trigger_params tuple — same shape as
    every other multi-target mandatory trigger in this registry (e.g.
    Kinkou Monk's two-target buff). The buff isn't optional on Radiant
    Dawn's text, so when it's reachable the plain 1-tuple form stops being
    legal, same as MANDATORY_PLAY_TRIGGERS withholding the untriggered
    form elsewhere in this module."""
    if not trigger_params:
        return False
    attacker, bf = _attacker_and_battlefield(state, attacker_instance_id)
    target = next((u for u in bf.units if u.instance_id == trigger_params[0]), None)
    if target is None or target.controller == attacker.controller:
        return False
    buff_active = _stun_buff_choice_active(state, attacker.controller, trigger_params[0])
    if len(trigger_params) != (2 if buff_active else 1):
        return False
    if buff_active:
        friendlies = _units_controlled_by(state, attacker.controller)
        if not any(u.instance_id == trigger_params[1] for u in friendlies):
            return False
    return True


def _leona_candidates(state: GameState, attacker_instance_id: int) -> list[tuple]:
    attacker, bf = _attacker_and_battlefield(state, attacker_instance_id)
    out: list[tuple] = []
    for enemy_id in (u.instance_id for u in _enemy_units_here(attacker, bf)):
        if _stun_buff_choice_active(state, attacker.controller, enemy_id):
            friendlies = sorted(_units_controlled_by(state, attacker.controller), key=lambda u: u.instance_id)
            out += [(enemy_id, f.instance_id) for f in friendlies]
        else:
            out.append((enemy_id,))
    return out


def _leona_effect(state: GameState, attacker_instance_id: int, trigger_params: tuple) -> GameState:
    """"Stun an enemy unit here." "It doesn't deal combat damage this
    turn" IS the stun (see combat.side_damage_pool), not a separate
    clause to model. A second param, when present, is Radiant Dawn's
    mandatory buff choice — apply_buff already no-ops on an
    already-buffed target, matching its reminder text."""
    state = stun_unit(state, trigger_params[0])
    if len(trigger_params) == 2:
        state = apply_buff(state, trigger_params[1])
    return state


# card_id -> (is_legal(state, attacker_instance_id, trigger_params),
#             effect(state, attacker_instance_id, trigger_params) -> GameState,
#             generate_candidate_params(state, attacker_instance_id))
#
# Deliberately NOT wired into DEFLECT_TARGETS, following the existing
# precedent of Riptide Rex / Harnessed Dragon (both mandatory triggers that
# choose an enemy unit and are already HANDLED without one) — see
# coverage.py's Anivia/Yasuo/Crackshot Corsair entries for the caveat this
# carries forward rather than fixes.
ATTACK_TRIGGERS: dict[str, tuple[
    Callable[[GameState, int, tuple], bool],
    Callable[[GameState, int, tuple], GameState],
    Callable[[GameState, int], list[tuple]],
]] = {
    ANIVIA_PRIMAL: (_anivia_is_legal, _anivia_effect, _anivia_candidates),
    YASUO_REMORSEFUL: (_single_enemy_here_is_legal, _yasuo_remorseful_effect, _single_enemy_here_candidates),
    YASUO_REMORSEFUL_ALT: (_single_enemy_here_is_legal, _yasuo_remorseful_effect, _single_enemy_here_candidates),
    CRACKSHOT_CORSAIR: (_single_enemy_here_is_legal, _attack_trigger_flat_damage_effect,
                        _single_enemy_here_candidates),
    DUNE_DRAKE: (_dune_drake_is_legal, _dune_drake_effect, _dune_drake_candidates),
    LEONA_DETERMINED: (_leona_is_legal, _leona_effect, _leona_candidates),
    LEONA_DETERMINED_ALT: (_leona_is_legal, _leona_effect, _leona_candidates),
}


def is_legal_resolve_attack_trigger(state: GameState, action: ResolveAttackTrigger) -> bool:
    if state.showdown is None or state.showdown.attack_trigger_resolved:
        return False
    bf = next(b for b in state.battlefields if b.battlefield_id == state.showdown.battlefield_id)
    attacker = next((u for u in bf.units if u.instance_id == action.instance_id), None)
    if attacker is None or attacker.controller != state.showdown.attacker_controller:
        return False
    entry = ATTACK_TRIGGERS.get(attacker.card_id)
    if entry is None:
        return False
    is_legal, _, _ = entry
    return is_legal(state, action.instance_id, action.trigger_params)


def apply_attack_trigger(state: GameState, action: ResolveAttackTrigger) -> GameState:
    """Applies the registered effect, then marks the showdown's trigger
    resolved — the one piece of bookkeeping every entry in ATTACK_TRIGGERS
    shares, so it lives here once instead of at the end of every effect
    function."""
    bf = next(b for b in state.battlefields if b.battlefield_id == state.showdown.battlefield_id)
    attacker = next(u for u in bf.units if u.instance_id == action.instance_id)
    _, effect, _ = ATTACK_TRIGGERS[attacker.card_id]
    new_state = effect(state, action.instance_id, action.trigger_params)
    return dataclasses.replace(new_state, showdown=dataclasses.replace(
        new_state.showdown, attack_trigger_resolved=True))


# card_id -> chosen_targets(state, params) -> [(UnitInstance, zone), ...]
#
# "Choose" in [Deflect]'s sense: the units an effect singles out by
# instance_id, which is what the tax is charged on. Read with a spell's
# `params` or a unit trigger's `trigger_params` — both put the chosen
# unit's instance_id first.
#
# Only cards that can choose an ENEMY unit need an entry. Ride The Wind
# moves a FRIENDLY unit and deflect_tax is 0 against your own, so
# registering it would be dead weight; the mandatory token-mint triggers
# (Faithful Manufactor, Vanguard Captain) choose nothing at all.
#
# Kept as its own registry rather than a fourth element on
# SPELL_EFFECTS/ABILITY_EFFECTS/UNIT_PLAY_TRIGGERS because it cuts across
# all three and most cards in each don't need it.
DEFLECT_TARGETS: dict[str, Callable[[GameState, tuple], list[tuple]]] = {
    CHARM: _charm_deflect_targets,
    VENGEANCE: _single_target_anywhere,
    PRIMAL_STRENGTH: _single_target_anywhere,
    CAITLYN_PATROLLING: _single_target_at_battlefield,
    BLITZCRANK_IMPASSIVE: _single_target_at_battlefield,
    ZAUNITE_BOUNCER: _single_target_at_battlefield,
}


def trigger_deflect_tax(state: GameState, action: PlayUnit, card: CardDef) -> int:
    """[Deflect] owed by a "when you play me" trigger for the unit it
    chooses. Evaluated against the board AFTER the card itself is played,
    since that's when the trigger resolves — and the tax comes out of
    what's left once the card's own cost is paid."""
    if not action.trigger_params:
        return 0
    state_after_play = apply_play_unit(state, dataclasses.replace(
        action, trigger_params=(), trigger_payment=None), card)
    return deflect_tax_for(state_after_play, action.card_id, action.trigger_params,
                           state.turn_player)


def is_legal_unit_play_trigger(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    if not is_legal_play_unit(state, action, card):
        return False
    entry = UNIT_PLAY_TRIGGERS.get(action.card_id)
    if entry is None:
        return action.trigger_params == () and action.trigger_payment is None
    if _paid_rainbow(action.trigger_payment) != trigger_deflect_tax(state, action, card):
        return False
    if action.trigger_payment is not None:
        if action.trigger_payment.energy_runes or action.trigger_payment.power_runes:
            return False  # only the tax is ever owed by a trigger
        # Spendable out of what the card's OWN cost leaves behind.
        left = consume_runes(state.players[state.turn_player].runes, action.rune_payment)
        if not payment_is_affordable(left, action.trigger_payment):
            return False
    is_legal_trigger, _, _ = entry
    return is_legal_trigger(state, action, card)


def resolve_unit_play_trigger_outcomes(state: GameState, action: PlayUnit, card: CardDef) -> list[GameState]:
    state_after_play = apply_play_unit(state, action, card)
    if action.trigger_payment is not None:
        player = state_after_play.players[state_after_play.turn_player]
        state_after_play = replace_player(state_after_play, state_after_play.turn_player,
                                           dataclasses.replace(player, runes=consume_runes(
                                               player.runes, action.trigger_payment)))
    if action.target_zone != "base":
        state_after_play = scoring.resolve_control_change(state, state_after_play, action.target_zone)
    _, effect, _ = UNIT_PLAY_TRIGGERS[action.card_id]
    return effect(state_after_play, action)
