"""Per-card spell/gear effect registry. Added one card at a time as
puzzles need them — not a general effect engine (design/07-scope-and-cut-
list.md's "add mechanics on demand" policy). Each registered spell pairs a
target/params legality check with the actual game-effect function;
resolve_spell_outcomes() looks a card up here after actions.py's generic
cost/hand bookkeeping (apply_play_spell_cost) has already run.
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Optional

from . import combat, scoring
from .actions import (
    ActivateAbility,
    PlaySpell,
    PlayUnit,
    apply_play_spell_cost,
    apply_play_unit,
    find_unit,
    find_unit_anywhere,
    find_unit_at_any_battlefield,
    is_legal_ability_move_destination,
    is_legal_play_spell_cost,
    is_legal_play_unit,
    kill_unit,
    next_instance_id,
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


def _grant_might(state: GameState, instance_id: int, amount: int) -> GameState:
    """Adds `amount` to a unit's `might_bonus` wherever it stands. No
    expiry bookkeeping: a puzzle is a single turn, so "this turn" covers
    the rest of it (see UnitInstance.might_bonus)."""
    located = find_unit_anywhere(state, instance_id)
    assert located is not None
    unit, zone = located
    buffed = dataclasses.replace(unit, might_bonus=unit.might_bonus + amount)
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
    return target_located is not None


def _caitlyn_effect(state: GameState, action: ActivateAbility) -> GameState:
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


# card_id -> (is_legal(state, action), effect(state, action), generate_candidate_params(state))
ABILITY_EFFECTS: dict[str, tuple[
    Callable[[GameState, ActivateAbility], bool],
    Callable[[GameState, ActivateAbility], GameState],
    Callable[[GameState], list[tuple]],
]] = {
    CAITLYN_PATROLLING: (_caitlyn_is_legal, _caitlyn_effect, _caitlyn_candidates),
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
}


def is_legal_unit_play_trigger(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    if not is_legal_play_unit(state, action, card):
        return False
    entry = UNIT_PLAY_TRIGGERS.get(action.card_id)
    if entry is None:
        return action.trigger_params == ()
    is_legal_trigger, _, _ = entry
    return is_legal_trigger(state, action, card)


def resolve_unit_play_trigger_outcomes(state: GameState, action: PlayUnit, card: CardDef) -> list[GameState]:
    state_after_play = apply_play_unit(state, action, card)
    if action.target_zone != "base":
        state_after_play = scoring.resolve_control_change(state, state_after_play, action.target_zone)
    _, effect, _ = UNIT_PLAY_TRIGGERS[action.card_id]
    return effect(state_after_play, action)
