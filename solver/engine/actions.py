"""Action space: legality checks and board-mechanics apply(). See
design/03-action-space.md.

Scope of this module, deliberately: board mechanics only (unit location,
exhaustion, rune spending, control establishment). It does NOT grant points
or touch `scored_this_turn` / `score` — control establishment's scoring
consequences (Conquer, the Final Point restriction) are scoring.py's job
(design/04-scoring-rules.md). Composing the two (apply a board action, then
call scoring.resolve_conquer on the newly-controlled battlefield) is the
solver's job.

Also deliberately out of scope here: `PlaySpell`, `PlayGear`,
`ActivateAbility` apply() bodies (they need per-card hand-authored effects,
which don't exist until the whitelist is built — design/01-data-sources.md),
and `MoveUnit` onto a battlefield that already has enemy units present
(combat resolution doesn't exist yet). Their dataclasses and cost-legality
checks are here; generating or applying them further is future work.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Optional

from .cards import CardDef
from .state import (
    BattlefieldState,
    Domain,
    GameState,
    RunePool,
    UnitInstance,
    replace_player,
)

Zone = str  # "base" or a battlefield_id


@dataclass(frozen=True)
class RunePayment:
    energy_runes: tuple[Domain, ...]  # domains of runes Exhausted for Energy
    power_runes: tuple[Domain, ...]  # domains of runes Recycled for Power


@dataclass(frozen=True)
class PlayUnit:
    card_id: str
    target_zone: Zone
    rune_payment: RunePayment


@dataclass(frozen=True)
class MoveUnit:
    instance_id: int
    from_zone: Zone
    to_zone: Zone


@dataclass(frozen=True)
class PlaySpell:
    card_id: str
    targets: tuple[int, ...]  # instance_ids, or battlefield_ids as needed by the effect
    rune_payment: RunePayment


@dataclass(frozen=True)
class PlayGear:
    card_id: str
    target_unit: int  # instance_id
    rune_payment: RunePayment


@dataclass(frozen=True)
class ActivateAbility:
    source_id: int  # instance_id of the activating unit
    ability_id: str
    rune_payment: Optional[RunePayment]


Action = PlayUnit | MoveUnit | PlaySpell | PlayGear | ActivateAbility


# --- Rune payment -----------------------------------------------------------


def generate_rune_payments(pool: RunePool, energy_cost: int, power_cost: int,
                            power_domain: Optional[Domain]) -> list[RunePayment]:
    """All distinct ways to pay `energy_cost` Energy + `power_cost` Power
    (of `power_domain`) out of `pool`, deduplicated by domain-count split —
    not by which physical rune is used (design/03-action-space.md's
    "rune-payment dedup" note). A rune produces Energy (any domain) XOR
    Power (its own domain), never both (rule 164.2.b) — so this picks
    disjoint sub-multisets of `pool.available` for the two costs.
    """
    if power_cost > 0 and power_domain is None:
        raise ValueError("power_cost > 0 requires a power_domain")

    available = list(pool.available)
    matching_domain_count = available.count(power_domain) if power_domain else 0
    if power_cost > matching_domain_count:
        return []  # not enough of the right domain to pay Power at all

    payments = []
    # Power must be paid with power_domain runes specifically; the number of
    # ways to choose *which* power_domain runes is irrelevant (they're
    # interchangeable), so there's exactly one representative power split.
    power_runes = tuple([power_domain] * power_cost) if power_cost else ()

    # Energy can be paid with any remaining runes, any domain — again, only
    # the *count* used from each remaining domain matters, not which
    # physical rune. Remaining pool after removing the power runes:
    remaining = available[:]
    for _ in range(power_cost):
        remaining.remove(power_domain)
    if energy_cost > len(remaining):
        return []  # not enough runes left for Energy

    # v0 keeps this simple: Energy is domain-agnostic, so a single
    # representative payment (the first `energy_cost` remaining runes) is
    # sufficient — which specific domains get spent on Energy never affects
    # future legality, since Energy never checks domain. Only Power's
    # domain-matching requirement can create genuinely distinct splits, and
    # that's already pinned to power_domain above.
    energy_runes = tuple(remaining[:energy_cost])
    payments.append(RunePayment(energy_runes=energy_runes, power_runes=power_runes))
    return payments


def _consume_runes(pool: RunePool, payment: RunePayment) -> RunePool:
    remaining = list(pool.available)
    for domain in payment.energy_runes + payment.power_runes:
        remaining.remove(domain)
    return RunePool(available=tuple(remaining))


# --- Board helpers ------------------------------------------------------


def _battlefield(state: GameState, battlefield_id: str) -> BattlefieldState:
    for bf in state.battlefields:
        if bf.battlefield_id == battlefield_id:
            return bf
    raise KeyError(f"no battlefield {battlefield_id!r}")


def _replace_battlefield(state: GameState, updated: BattlefieldState) -> GameState:
    battlefields = tuple(
        updated if bf.battlefield_id == updated.battlefield_id else bf
        for bf in state.battlefields
    )
    return dataclasses.replace(state, battlefields=battlefields)


def _next_instance_id(state: GameState) -> int:
    ids = [0]
    for player in state.players:
        ids += [u.instance_id for u in player.base_units]
    for bf in state.battlefields:
        ids += [u.instance_id for u in bf.units]
    return max(ids) + 1


# --- PlayUnit -------------------------------------------------------------


def is_legal_play_unit(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    if card.card_type != "Unit":
        return False
    player = state.players[state.turn_player]
    if action.card_id not in player.hand:
        return False
    if len(action.rune_payment.energy_runes) != card.energy_cost:
        return False
    if len(action.rune_payment.power_runes) != card.power_cost:
        return False
    if card.power_cost and any(d != card.power_domain for d in action.rune_payment.power_runes):
        return False
    spent = list(action.rune_payment.energy_runes + action.rune_payment.power_runes)
    pool = list(player.runes.available)
    for domain in spent:
        if domain not in pool:
            return False
        pool.remove(domain)
    if action.target_zone == "base":
        return True
    # rule 355.7/355.8: a battlefield is only a valid PlayUnit target if the
    # controller already controls it, UNLESS the card's own text grants an
    # exception (e.g. Sneaky Deckhand: "You may play me to an open
    # battlefield") — rule 170.11.c: "open" means unoccupied AND
    # uncontrolled, not merely uncontrolled.
    try:
        bf = _battlefield(state, action.target_zone)
    except KeyError:
        return False
    if bf.controller == state.turn_player:
        return True
    return card.can_play_to_open_battlefield and bf.controller is None and not bf.units


def apply_play_unit(state: GameState, action: PlayUnit, card: CardDef) -> GameState:
    player_index = state.turn_player
    player = state.players[player_index]

    new_unit = UnitInstance(
        card_id=card.card_id,
        instance_id=_next_instance_id(state),
        controller=player_index,
        might=card.might if card.might is not None else 0,
        keywords=card.keywords,
        exhausted=True,  # rule 143.4.a: units enter the board exhausted
        damage=0,
        is_token=False,
    )

    new_hand = list(player.hand)
    new_hand.remove(action.card_id)
    new_runes = _consume_runes(player.runes, action.rune_payment)

    if action.target_zone == "base":
        new_player = dataclasses.replace(
            player,
            base_units=player.base_units | {new_unit},
            hand=tuple(new_hand),
            runes=new_runes,
        )
        return replace_player(state, player_index, new_player)

    new_player = dataclasses.replace(player, hand=tuple(new_hand), runes=new_runes)
    state = replace_player(state, player_index, new_player)
    bf = _battlefield(state, action.target_zone)
    # rule 466.7.b: playing to an open battlefield (via can_play_to_open_
    # battlefield) establishes control, same as MoveUnit does — playing to
    # a battlefield already controlled by this player is a no-op for
    # controller (it's already theirs).
    new_controller = bf.controller if bf.controller is not None else player_index
    new_bf = dataclasses.replace(bf, units=bf.units | {new_unit}, controller=new_controller)
    return _replace_battlefield(state, new_bf)


# --- MoveUnit ---------------------------------------------------------------


def _find_unit(state: GameState, instance_id: int, zone: Zone) -> Optional[UnitInstance]:
    if zone == "base":
        pool = state.players[state.turn_player].base_units
    else:
        pool = _battlefield(state, zone).units
    for u in pool:
        if u.instance_id == instance_id:
            return u
    return None


def is_legal_move_unit(state: GameState, action: MoveUnit) -> bool:
    if action.from_zone == action.to_zone:
        return False
    unit = _find_unit(state, action.instance_id, action.from_zone)
    if unit is None or unit.controller != state.turn_player:
        return False
    if unit.exhausted:
        return False
    if action.from_zone == "base":
        # rule 145.2.a: Base -> Battlefield always legal.
        return action.to_zone != "base" and any(
            bf.battlefield_id == action.to_zone for bf in state.battlefields
        )
    # from a battlefield
    if action.to_zone == "base":
        return True  # rule: Battlefield -> Base always legal
    # Battlefield -> Battlefield requires Ganking (rule 810).
    if not any(bf.battlefield_id == action.to_zone for bf in state.battlefields):
        return False
    return "Ganking" in unit.keywords


def apply_move_unit(state: GameState, action: MoveUnit) -> GameState:
    """Board mechanics: relocates the unit, exhausts it (rule 145.1), and
    updates `BattlefieldState.controller` as a plain board-state fact —
    rule 466.7.b (the player left with units present Establishes Control)
    and rule 468 (a battlefield with no units from any player becomes
    Uncontrolled). Does NOT resolve combat: callers must not use this for a
    destination with enemy units present (combat resolution isn't
    implemented yet, see the module docstring).

    Whether a resulting control change counts as a scoring Conquer (rule
    469.1: only if the player hasn't already Scored this battlefield this
    turn) is scoring.resolve_conquer's job, not this function's — the
    solver calls it when it sees `battlefields[i].controller` change to
    `state.turn_player`.
    """
    player_index = state.turn_player
    unit = _find_unit(state, action.instance_id, action.from_zone)
    assert unit is not None
    moved_unit = dataclasses.replace(unit, exhausted=True)

    # Remove from source.
    if action.from_zone == "base":
        player = state.players[player_index]
        new_player = dataclasses.replace(player, base_units=player.base_units - {unit})
        state = replace_player(state, player_index, new_player)
    else:
        bf = _battlefield(state, action.from_zone)
        remaining_units = bf.units - {unit}
        # rule 468: no units from any player left here -> Uncontrolled.
        new_controller = bf.controller if remaining_units else None
        state = _replace_battlefield(
            state, dataclasses.replace(bf, units=remaining_units, controller=new_controller)
        )

    # Add to destination.
    if action.to_zone == "base":
        player = state.players[player_index]
        new_player = dataclasses.replace(player, base_units=player.base_units | {moved_unit})
        return replace_player(state, player_index, new_player)

    bf = _battlefield(state, action.to_zone)
    if bf.units:
        raise NotImplementedError(
            "apply_move_unit: destination has units present — combat resolution "
            "isn't implemented yet (see design/03-action-space.md's combat section)"
        )
    # rule 466.7.b: the mover is the only player with units here now, so
    # they Establish Control (regardless of whether this also scores a
    # point, which resolve_conquer decides separately).
    new_bf = dataclasses.replace(bf, units=bf.units | {moved_unit}, controller=player_index)
    return _replace_battlefield(state, new_bf)


# --- Generation --------------------------------------------------------------


def legal_actions(state: GameState, cards: dict[str, CardDef]) -> list[Action]:
    """PlayUnit and MoveUnit candidates only — PlaySpell/PlayGear/
    ActivateAbility generation is deferred until their apply() exists (see
    module docstring). PlayUnit candidates include open battlefields for
    cards with can_play_to_open_battlefield set."""
    actions: list[Action] = []
    player = state.players[state.turn_player]

    battlefield_ids = [bf.battlefield_id for bf in state.battlefields]
    controlled_battlefields = [
        bf.battlefield_id for bf in state.battlefields if bf.controller == state.turn_player
    ]

    for card_id in set(player.hand):
        card = cards.get(card_id)
        if card is None or card.card_type != "Unit":
            continue
        candidate_zones = ["base"] + controlled_battlefields
        if card.can_play_to_open_battlefield:
            candidate_zones += [
                bf.battlefield_id for bf in state.battlefields
                if bf.controller is None and not bf.units
            ]
        for payment in generate_rune_payments(
            player.runes, card.energy_cost, card.power_cost, card.power_domain
        ):
            for zone in candidate_zones:
                action = PlayUnit(card_id=card_id, target_zone=zone, rune_payment=payment)
                if is_legal_play_unit(state, action, card):
                    actions.append(action)

    for unit in player.base_units:
        for bf_id in battlefield_ids:
            action = MoveUnit(instance_id=unit.instance_id, from_zone="base", to_zone=bf_id)
            if is_legal_move_unit(state, action):
                actions.append(action)
    for bf in state.battlefields:
        for unit in bf.units:
            if unit.controller != state.turn_player:
                continue
            for to_zone in ["base"] + [b for b in battlefield_ids if b != bf.battlefield_id]:
                action = MoveUnit(instance_id=unit.instance_id, from_zone=bf.battlefield_id, to_zone=to_zone)
                if is_legal_move_unit(state, action):
                    actions.append(action)

    return actions
