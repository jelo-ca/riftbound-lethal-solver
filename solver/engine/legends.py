"""Legend ability registry — same per-card, add-on-demand shape as
abilities.py's ABILITY_EFFECTS, but sourced from a player's Legend zone
rather than a unit on the board.

A Legend is a persistent card in its own zone (state.LegendState): never
at a battlefield, never a combat participant, so it has no instance_id
and no Might. What it does have is an Exhaust cost — every Legend
ability registered here pays one, some with Energy on top — which is why
LegendState tracks `exhausted` and canonical_key includes it.

Activation reuses the existing `ActivateAbility` action rather than
introducing a parallel action type: `source_id` is LEGEND_SOURCE_ID
(0, a value next_instance_id can never hand out since it starts at 1)
and `ability_id` keys into LEGEND_ABILITIES below. search.legal_actions
generates the candidates; abilities.is_legal_activate_ability /
apply_ability dispatch to here when the ability_id is a Legend's.
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Optional

from . import scoring
from .actions import (
    ActivateAbility,
    RunePayment,
    consume_runes,
    payment_is_affordable,
    find_unit,
    find_unit_anywhere,
    is_legal_ability_move_destination,
    relocate_unit,
)
from .state import GameState, replace_player

LEGEND_SOURCE_ID = 0

YASUO_UNFORGIVEN = "ogn-259-298"  # 2 Energy, Exhaust: Move a friendly unit to or from its base.
BLIND_MONK = "ogn-257-298"  # 1 Energy, Exhaust: Buff a friendly unit.
BLIND_MONK_NX = "ogn-304-298"  # same Legend, alternate printing
BLIND_MONK_STAR = "ogn-304-star-298"  # same Legend, alternate printing

# card_id -> (energy_cost, power_cost, power_domain) for the ability's
# rune cost on top of its Exhaust cost.
ABILITY_COSTS: dict[str, tuple[int, int, Optional[str]]] = {
    YASUO_UNFORGIVEN: (2, 0, None),
    BLIND_MONK: (1, 0, None),
    BLIND_MONK_NX: (1, 0, None),
    BLIND_MONK_STAR: (1, 0, None),
}


def _locate_unit(state: GameState, instance_id: int) -> Optional[str]:
    for zone in ["base"] + [bf.battlefield_id for bf in state.battlefields]:
        if find_unit(state, instance_id, zone) is not None:
            return zone
    return None


def exhaust_legend(state: GameState, player_index: int) -> GameState:
    player = state.players[player_index]
    assert player.legend is not None
    exhausted = dataclasses.replace(player.legend, exhausted=True)
    return replace_player(state, player_index, dataclasses.replace(player, legend=exhausted))


def _yasuo_unforgiven_is_legal(state: GameState, action: ActivateAbility) -> bool:
    """params = (instance_id, destination_zone). "Move a friendly unit to
    or from its base" — NARROWER than Ride The Wind's unrestricted move:
    one end of the move must be Base, so battlefield-to-battlefield is
    not a legal target even though a spell-granted move normally would
    be (see is_legal_ability_move_destination's docstring — a card that's
    actually restricted enforces the narrower rule itself)."""
    if len(action.params) != 2:
        return False
    instance_id, destination = action.params
    from_zone = _locate_unit(state, instance_id)
    if from_zone is None:
        return False
    unit = find_unit(state, instance_id, from_zone)
    if unit.controller != state.turn_player:
        return False  # "a FRIENDLY unit"
    if from_zone != "base" and destination != "base":
        return False  # "to or FROM its base" — one end must be Base
    return is_legal_ability_move_destination(state, from_zone, destination)


def _yasuo_unforgiven_effect(state: GameState, action: ActivateAbility) -> list[GameState]:
    instance_id, destination = action.params
    from_zone = _locate_unit(state, instance_id)
    assert from_zone is not None
    unit = find_unit(state, instance_id, from_zone)
    # ASSUMPTION pending confirmation: an effect-granted move is not a
    # Standard Move, so it doesn't carry rule 145.1's exhaust cost — the
    # unit keeps whatever exhaustion state it already had. Ride The Wind's
    # explicit "and ready it" reads as meaningful precisely because a bare
    # move wouldn't change it either way. (Blitzcrank's redirect currently
    # hardcodes exhausted_after=True, which may be wrong for the same
    # reason — flagged, not yet changed.)
    new_state = relocate_unit(state, instance_id, from_zone, destination,
                               exhausted_after=unit.exhausted)
    if destination != "base":
        new_state = scoring.resolve_control_change(state, new_state, destination)
    return [new_state]


def _yasuo_unforgiven_candidates(state: GameState) -> list[tuple]:
    """Every friendly unit, times the Base<->battlefield moves legal for
    it — no battlefield-to-battlefield, per the card's own restriction."""
    player = state.players[state.turn_player]
    battlefield_ids = [bf.battlefield_id for bf in state.battlefields]
    candidates: list[tuple] = []
    for unit in sorted(player.base_units, key=lambda u: u.instance_id):
        for destination in battlefield_ids:
            if is_legal_ability_move_destination(state, "base", destination):
                candidates.append((unit.instance_id, destination))
    for bf in state.battlefields:
        for unit in sorted(bf.units, key=lambda u: u.instance_id):
            if unit.controller != state.turn_player:
                continue
            if is_legal_ability_move_destination(state, bf.battlefield_id, "base"):
                candidates.append((unit.instance_id, "base"))
    return candidates


def _blind_monk_is_legal(state: GameState, action: ActivateAbility) -> bool:
    """params = (target_instance_id,). "Buff a friendly unit" — no
    restriction to a battlefield, so Base counts too. Only ever chooses
    our own units, so no [Deflect] tax can ever be owed."""
    if len(action.params) != 1:
        return False
    located = find_unit_anywhere(state, action.params[0])
    return located is not None and located[0].controller == state.turn_player


def _blind_monk_effect(state: GameState, action: ActivateAbility) -> list[GameState]:
    from .abilities import apply_buff  # deferred: abilities imports this module
    return [apply_buff(state, action.params[0])]


def _blind_monk_candidates(state: GameState) -> list[tuple]:
    player = state.players[state.turn_player]
    candidates = [(u.instance_id,) for u in sorted(player.base_units, key=lambda u: u.instance_id)]
    candidates += [(u.instance_id,) for bf in state.battlefields
                   for u in sorted(bf.units, key=lambda u: u.instance_id)
                   if u.controller == state.turn_player]
    return candidates


# card_id -> (is_legal(state, action), effect(state, action) -> list[GameState],
#             generate_candidate_params(state))
LEGEND_ABILITIES: dict[str, tuple[
    Callable[[GameState, ActivateAbility], bool],
    Callable[[GameState, ActivateAbility], list[GameState]],
    Callable[[GameState], list[tuple]],
]] = {
    YASUO_UNFORGIVEN: (_yasuo_unforgiven_is_legal, _yasuo_unforgiven_effect,
                        _yasuo_unforgiven_candidates),
    BLIND_MONK: (_blind_monk_is_legal, _blind_monk_effect, _blind_monk_candidates),
    BLIND_MONK_NX: (_blind_monk_is_legal, _blind_monk_effect, _blind_monk_candidates),
    BLIND_MONK_STAR: (_blind_monk_is_legal, _blind_monk_effect, _blind_monk_candidates),
}


def is_legend_ability(ability_id: str) -> bool:
    return ability_id in LEGEND_ABILITIES


def is_legal_legend_ability(state: GameState, action: ActivateAbility) -> bool:
    """Zone/cost checks shared by every Legend ability — the player must
    actually have this Legend, unexhausted, and be able to pay any rune
    cost — then the card's own target check."""
    entry = LEGEND_ABILITIES.get(action.ability_id)
    if entry is None:
        return False
    if action.source_id != LEGEND_SOURCE_ID:
        return False
    player = state.players[state.turn_player]
    if player.legend is None or player.legend.card_id != action.ability_id:
        return False
    if player.legend.exhausted:
        return False  # its cost includes Exhaust, so it can only fire once
    if not _can_pay(player, action.ability_id, action.rune_payment):
        return False
    is_legal_effect, _, _ = entry
    return is_legal_effect(state, action)


def _can_pay(player, ability_id: str, payment: Optional[RunePayment]) -> bool:
    energy_cost, power_cost, power_domain = ABILITY_COSTS[ability_id]
    if energy_cost == 0 and power_cost == 0:
        return payment is None or (not payment.energy_runes and not payment.power_runes)
    if payment is None:
        return False
    if len(payment.energy_runes) != energy_cost or len(payment.power_runes) != power_cost:
        return False
    if power_cost and any(d != power_domain for d in payment.power_runes):
        return False
    return payment_is_affordable(player.runes, payment)


def resolve_legend_ability_outcomes(state: GameState, action: ActivateAbility) -> list[GameState]:
    """Pays the ability's costs (Exhaust, plus any runes), then applies
    the card's own effect."""
    player_index = state.turn_player
    state = exhaust_legend(state, player_index)
    if action.rune_payment is not None:
        player = state.players[player_index]
        new_runes = consume_runes(player.runes, action.rune_payment)
        state = replace_player(state, player_index, dataclasses.replace(player, runes=new_runes))
    _, effect, _ = LEGEND_ABILITIES[action.ability_id]
    return effect(state, action)
