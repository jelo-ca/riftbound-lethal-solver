"""Per-card spell/gear effect registry. Added one card at a time as
puzzles need them — not a general effect engine (design/07-scope-and-cut-
list.md's "add mechanics on demand" policy). Each registered spell pairs a
target/params legality check with the actual game-effect function;
apply_spell() looks a card up here after actions.py's generic cost/hand
bookkeeping (apply_play_spell_cost) has already run.
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
    find_unit_at_any_battlefield,
    is_legal_ability_move_destination,
    is_legal_play_spell_cost,
    is_legal_play_unit,
    relocate_unit,
    replace_battlefield,
)
from .cards import CardDef
from .state import GameState

RIDE_THE_WIND = "ogn-173-298"  # 2 Energy, 1 Chaos Power: "Move a friendly unit and ready it."
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


def _ride_the_wind_effect(state: GameState, action: PlaySpell) -> GameState:
    instance_id, destination = action.params
    from_zone = _locate_unit(state, instance_id)
    assert from_zone is not None
    new_state = relocate_unit(state, instance_id, from_zone, destination, exhausted_after=False)
    if destination != "base":
        new_state = scoring.resolve_control_change(state, new_state, destination)
    return new_state


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
        for unit in units:
            if unit.controller != state.turn_player:
                continue
            for destination in all_zones:
                if destination != zone and is_legal_ability_move_destination(state, zone, destination):
                    candidates.append((unit.instance_id, destination))
    return candidates


# card_id -> (is_legal(state, action), effect(state, action), generate_candidate_params(state))
SPELL_EFFECTS: dict[str, tuple[
    Callable[[GameState, PlaySpell], bool],
    Callable[[GameState, PlaySpell], GameState],
    Callable[[GameState], list[tuple]],
]] = {
    RIDE_THE_WIND: (_ride_the_wind_is_legal, _ride_the_wind_effect, _ride_the_wind_candidates),
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
    return [(u.instance_id,) for bf in state.battlefields for u in bf.units]


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


def apply_spell(state: GameState, action: PlaySpell, card: CardDef) -> GameState:
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

    if combat.is_combat_triggered(state_after_play, unit, to_zone):
        our_assignment = action.trigger_params[1]
        outcomes = combat.enumerate_combat_outcomes(state_after_play, unit, from_zone, to_zone, our_assignment)
        return [scoring.resolve_control_change(state_after_play, o, to_zone) for o in outcomes]

    moved = relocate_unit(state_after_play, enemy_id, from_zone, to_zone, exhausted_after=True)
    return [scoring.resolve_control_change(state_after_play, moved, to_zone)]


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
        for unit in bf.units:
            if unit.controller == state.turn_player:
                continue
            if combat.is_combat_triggered(state_after_play, unit, base_action.target_zone):
                for our_assignment in combat.our_assignment_options(state_after_play, unit, base_action.target_zone):
                    candidates.append((unit.instance_id, our_assignment))
            else:
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
