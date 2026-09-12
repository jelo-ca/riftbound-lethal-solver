"""Per-card spell/gear effect registry. Added one card at a time as
puzzles need them — not a general effect engine (design/07-scope-and-cut-
list.md's "add mechanics on demand" policy). Each registered spell pairs a
target/params legality check with the actual game-effect function;
apply_spell() looks a card up here after actions.py's generic cost/hand
bookkeeping (apply_play_spell_cost) has already run.
"""

from __future__ import annotations

from typing import Callable, Optional

from . import scoring
from .actions import (
    PlaySpell,
    apply_play_spell_cost,
    find_unit,
    is_legal_ability_move_destination,
    is_legal_play_spell_cost,
    relocate_unit,
)
from .cards import CardDef
from .state import GameState

RIDE_THE_WIND = "ogn-173-298"  # 2 Energy, 1 Chaos Power: "Move a friendly unit and ready it."


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
