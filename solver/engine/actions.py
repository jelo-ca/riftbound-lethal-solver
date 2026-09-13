"""Action space: legality checks and board-mechanics apply(). See
design/03-action-space.md.

Scope of this module, deliberately: board mechanics only (unit location,
exhaustion, rune spending, control establishment). It does NOT grant points
or touch `scored_this_turn` / `score` — control establishment's scoring
consequences (Conquer, the Final Point restriction) are scoring.py's job
(design/04-scoring-rules.md). Composing the two (apply a board action, then
call scoring.resolve_conquer on the newly-controlled battlefield) is the
solver's job.

`PlaySpell`'s cost/hand bookkeeping lives here (apply_play_spell), but its
actual game effect is per-card and lives in abilities.py's registry —
added one spell at a time as puzzles need them, not a general effect
engine. `PlayGear`/`ActivateAbility` apply() bodies are still deliberately
out of scope (same reasoning, just not needed by any puzzle yet), as is
`MoveUnit`/relocate_unit onto a battlefield that already has enemy units
present (combat resolution doesn't exist yet).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Optional

from . import battlefields, combat
from .cards import CardDef
from .combat import Assignment
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
    # Opaque, effect-specific — same params convention as PlaySpell/
    # ActivateAbility, for units with a registered "when you play me"
    # trigger (abilities.UNIT_PLAY_TRIGGERS). Empty tuple = no trigger
    # registered, or the player declined an optional one ("you may...").
    trigger_params: tuple = ()


@dataclass(frozen=True)
class MoveUnit:
    instance_id: int
    from_zone: Zone
    to_zone: Zone


@dataclass(frozen=True)
class ResolveCombat:
    """A Standard Move whose destination has enemy units present — see
    design/09-combat-resolution.md. `our_assignment` is OUR chosen
    damage split, targeting whichever side is the opponent's (in this v0
    pass, always the Defender's units, since a Standard Move only ever
    moves a unit we control, making us the Attacker every time — spell-
    granted combat, where an enemy unit gets moved onto ground we hold
    and we become the Defender, isn't wired up yet). Generated in place
    of a plain MoveUnit whenever the destination is combat-triggering;
    one candidate per distinct assignment we could choose.
    """
    instance_id: int
    from_zone: Zone
    to_zone: Zone
    our_assignment: Assignment


@dataclass(frozen=True)
class PlaySpell:
    card_id: str
    # Opaque, effect-specific: whatever the card's registered ability
    # (abilities.py) needs — e.g. (instance_id, destination_zone) for a
    # "move a unit" spell. Kept generic rather than a fixed shape since
    # different spells need different parameters.
    params: tuple
    rune_payment: RunePayment


@dataclass(frozen=True)
class PlayGear:
    card_id: str
    target_unit: int  # instance_id
    rune_payment: RunePayment


@dataclass(frozen=True)
class ActivateAbility:
    source_id: int  # instance_id of the activating unit
    ability_id: str  # keyed into abilities.ABILITY_EFFECTS, by convention == the source's card_id
    # Opaque, effect-specific — same convention as PlaySpell.params.
    params: tuple
    rune_payment: Optional[RunePayment]  # None for abilities with no rune cost (e.g. exhaust-only)


Action = PlayUnit | MoveUnit | ResolveCombat | PlaySpell | PlayGear | ActivateAbility


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


def consume_runes(pool: RunePool, payment: RunePayment) -> RunePool:
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


def replace_battlefield(state: GameState, updated: BattlefieldState) -> GameState:
    battlefields = tuple(
        updated if bf.battlefield_id == updated.battlefield_id else bf
        for bf in state.battlefields
    )
    return dataclasses.replace(state, battlefields=battlefields)


def next_instance_id(state: GameState) -> int:
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
    # rule 355.7/355.8: a battlefield is only a valid PlayUnit target if you
    # already have UNITS there, UNLESS the card's own text grants an
    # exception (e.g. Sneaky Deckhand: "You may play me to an open
    # battlefield") — rule 170.11.c: "open" means unoccupied AND
    # uncontrolled, not merely uncontrolled.
    #
    # Checked as "do we have a unit here", which is what the rule says,
    # rather than "do we control here". Those coincide today only because
    # every path that empties a battlefield also clears its controller —
    # an invariant held elsewhere in this module and in combat.py, not
    # something this check should be quietly depending on.
    try:
        bf = _battlefield(state, action.target_zone)
    except KeyError:
        return False
    if any(u.controller == state.turn_player for u in bf.units):
        return True
    return card.can_play_to_open_battlefield and bf.controller is None and not bf.units


def apply_play_unit(state: GameState, action: PlayUnit, card: CardDef) -> GameState:
    player_index = state.turn_player
    player = state.players[player_index]

    new_unit = UnitInstance(
        card_id=card.card_id,
        instance_id=next_instance_id(state),
        controller=player_index,
        might=card.might if card.might is not None else 0,
        keywords=card.keywords,
        exhausted=True,  # rule 143.4.a: units enter the board exhausted
        damage=0,
        is_token=False,
    )

    new_hand = list(player.hand)
    new_hand.remove(action.card_id)
    new_runes = consume_runes(player.runes, action.rune_payment)

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
    return replace_battlefield(state, new_bf)


# --- PlaySpell (generic cost/hand bookkeeping; effects live in abilities.py) --


def is_legal_play_spell_cost(state: GameState, action: PlaySpell, card: CardDef) -> bool:
    """Cost/hand checks only — same shape as is_legal_play_unit's cost
    checks, minus anything unit-specific. A spell's own target/params
    legality is the registered ability's job (abilities.py), since that's
    entirely card-specific."""
    if card.card_type != "Spell":
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
    return True


def apply_play_spell_cost(state: GameState, action: PlaySpell) -> GameState:
    """Removes the card from hand and spends its runes. Does NOT apply the
    spell's game effect — that's abilities.py's job, called after this.
    No trash/discard zone is modeled (design/07-scope-and-cut-list.md
    doesn't need one yet — no whitelisted card references trash); the
    spell simply leaves the hand."""
    player_index = state.turn_player
    player = state.players[player_index]
    new_hand = list(player.hand)
    new_hand.remove(action.card_id)
    new_runes = consume_runes(player.runes, action.rune_payment)
    new_player = dataclasses.replace(player, hand=tuple(new_hand), runes=new_runes)
    return replace_player(state, player_index, new_player)


# --- MoveUnit ---------------------------------------------------------------


def find_unit(state: GameState, instance_id: int, zone: Zone) -> Optional[UnitInstance]:
    if zone == "base":
        pool = state.players[state.turn_player].base_units
    else:
        pool = _battlefield(state, zone).units
    for u in pool:
        if u.instance_id == instance_id:
            return u
    return None


def find_unit_at_any_battlefield(state: GameState, instance_id: int) -> Optional[tuple[UnitInstance, str]]:
    """Searches only battlefields (not either player's Base) — sufficient
    for abilities like Caitlyn - Patrolling's ("deal damage to a unit at
    a battlefield") that only ever target board presence, not Base. Base
    isn't searched here since our Zone type can't disambiguate whose
    Base a match came from without a target zone already in hand."""
    for bf in state.battlefields:
        for u in bf.units:
            if u.instance_id == instance_id:
                return u, bf.battlefield_id
    return None


def find_unit_anywhere(state: GameState, instance_id: int) -> Optional[tuple[UnitInstance, Zone]]:
    """Searches every zone on the board - both players' Base plus every
    battlefield - for effects like Vengeance ("kill a unit," unrestricted
    to battlefield presence or a specific controller). The unit's own
    `controller` field (not the return value) disambiguates whose Base a
    `"base"` match came from - `Zone` alone can't."""
    for player in state.players:
        for u in player.base_units:
            if u.instance_id == instance_id:
                return u, "base"
    return find_unit_at_any_battlefield(state, instance_id)


def kill_unit(state: GameState, instance_id: int) -> GameState:
    """Removes a unit outright regardless of its current damage — for
    effects like Vengeance ("kill a unit") that aren't a damage
    *amount*, just a removal. Reuses combat.deal_damage_to_unit for a
    battlefield target (dealing its own Might guarantees lethal,
    correctly recomputing the battlefield's controller); a Base target
    has no controller to recompute, just removal from that player's
    base_units."""
    located = find_unit_anywhere(state, instance_id)
    assert located is not None
    unit, zone = located
    if zone == "base":
        player = state.players[unit.controller]
        new_player = dataclasses.replace(player, base_units=player.base_units - {unit})
        return replace_player(state, unit.controller, new_player)
    return combat.deal_damage_to_unit(state, zone, instance_id, unit.might)


def return_unit_to_hand(state: GameState, battlefield_id: str, instance_id: int) -> GameState:
    """Removes a unit from a battlefield and returns its card to its
    OWNER's hand (not necessarily the acting player's) — for effects
    like Zaunite Bouncer ("return another unit at a battlefield to its
    owner's hand"). Tank doesn't gate this (rule: Tank only orders
    Combat Damage Step assignment, not other effects) — any unit at the
    battlefield is a legal target, keyword or not."""
    bf = _battlefield(state, battlefield_id)
    unit = next(u for u in bf.units if u.instance_id == instance_id)
    remaining = bf.units - {unit}
    controllers = {u.controller for u in remaining}
    new_controller = next(iter(controllers)) if len(controllers) == 1 else None
    state = replace_battlefield(state, dataclasses.replace(bf, units=remaining, controller=new_controller))

    owner = state.players[unit.controller]
    new_owner = dataclasses.replace(owner, hand=owner.hand + (unit.card_id,))
    return replace_player(state, unit.controller, new_owner)


def battlefield_effect_id(state: GameState, zone: Zone) -> Optional[str]:
    """The registered effect on `zone`'s battlefield, or None for Base or
    an effect-less battlefield."""
    if zone == "base":
        return None
    for bf in state.battlefields:
        if bf.battlefield_id == zone:
            return bf.effect_id
    return None


def effective_keywords(state: GameState, unit: UnitInstance, zone: Zone) -> frozenset[str]:
    """A unit's own keywords plus any its current battlefield grants it
    (e.g. Windswept Hillock: "Units here have [Ganking]") — always ask
    for these rather than reading `unit.keywords` directly wherever the
    unit's location could matter."""
    return unit.keywords | battlefields.granted_keywords(battlefield_effect_id(state, zone))


def is_legal_destination(state: GameState, unit: UnitInstance, from_zone: Zone, to_zone: Zone) -> bool:
    """Zone-rule legality for a unit's own Standard Move only (rule
    145.2.a Base<->Battlefield, rule 810 Ganking for Battlefield-to-
    Battlefield) — does NOT check exhaustion. This restriction is specific
    to the Standard Move game action; spell/ability-granted "Move" effects
    are NOT bound by it (see is_legal_ability_move_destination) — a spell
    states explicitly if it's restricted to Base (e.g. "Move a unit from a
    battlefield to its base"), otherwise it can move a unit to any zone
    including Battlefield-to-Battlefield with no Ganking requirement.

    Ganking can also come from the battlefield the unit is standing on
    rather than the unit's own text (Windswept Hillock), so this reads
    effective_keywords, not unit.keywords."""
    if from_zone == to_zone:
        return False
    if from_zone == "base":
        return to_zone != "base" and any(bf.battlefield_id == to_zone for bf in state.battlefields)
    if to_zone == "base":
        return not battlefields.blocks_move_to_base(battlefield_effect_id(state, from_zone))
    if not any(bf.battlefield_id == to_zone for bf in state.battlefields):
        return False
    return "Ganking" in effective_keywords(state, unit, from_zone)


def is_legal_ability_move_destination(state: GameState, from_zone: Zone, to_zone: Zone) -> bool:
    """Zone-rule legality for a spell/ability-granted "Move" effect (e.g.
    Ride The Wind, Charm) — any zone to any other zone is legal by
    default, no Ganking requirement, since that restriction is specific to
    a unit's own Standard Move (see is_legal_destination). A spell that's
    actually restricted (e.g. "Move a unit from a battlefield to its
    base") enforces that narrower rule itself rather than calling this.

    A battlefield's own movement restriction (Vilemaw's Lair: "Units
    can't move from here to base") DOES bind spell-granted moves — its
    text restricts movement itself, not one particular way of moving."""
    if from_zone == to_zone:
        return False
    if to_zone != "base" and not any(bf.battlefield_id == to_zone for bf in state.battlefields):
        return False
    if to_zone == "base" and battlefields.blocks_move_to_base(battlefield_effect_id(state, from_zone)):
        return False
    return from_zone == "base" or any(bf.battlefield_id == from_zone for bf in state.battlefields)


def is_legal_move_unit(state: GameState, action: MoveUnit) -> bool:
    unit = find_unit(state, action.instance_id, action.from_zone)
    if unit is None or unit.controller != state.turn_player:
        return False
    if unit.exhausted:  # rule 145.1: a Standard Move requires the unit not already exhausted
        return False
    if not is_legal_destination(state, unit, action.from_zone, action.to_zone):
        return False
    # A destination with enemy units triggers combat — that's ResolveCombat's
    # job, not a plain MoveUnit's (see is_legal_resolve_combat below).
    if action.to_zone != "base" and combat.is_combat_triggered(state, unit, action.to_zone):
        return False
    return True


def is_legal_resolve_combat(state: GameState, action: ResolveCombat) -> bool:
    unit = find_unit(state, action.instance_id, action.from_zone)
    if unit is None or unit.controller != state.turn_player:
        return False
    if unit.exhausted:  # rule 145.1
        return False
    if action.to_zone == "base" or not is_legal_destination(state, unit, action.from_zone, action.to_zone):
        return False
    if not combat.is_combat_triggered(state, unit, action.to_zone):
        return False
    _, _, _, defender_units = combat.determine_sides(state, unit, action.to_zone)
    destination_effect = battlefield_effect_id(state, action.to_zone)
    our_pool = combat.effective_might(unit, "attacker", destination_effect)
    return action.our_assignment in combat.enumerate_assignments(
        defender_units, our_pool, "defender", destination_effect)


def relocate_unit(state: GameState, instance_id: int, from_zone: Zone, to_zone: Zone,
                   exhausted_after: bool) -> GameState:
    """Board mechanics: relocates a unit and updates `BattlefieldState.
    controller` as a plain board-state fact — rule 466.7.b (the player
    left with units present Establishes Control) and rule 468 (a
    battlefield with no units from any player becomes Uncontrolled). Does
    NOT resolve combat: callers must not target a destination with enemy
    units present (combat resolution isn't implemented yet, see the module
    docstring).

    `exhausted_after` lets callers represent moves that don't carry the
    normal rule 145.1 exhaust cost (e.g. Ride The Wind: "Move a friendly
    unit and ready it" — the unit ends up readied, not exhausted).

    Whether a resulting control change counts as a scoring Conquer (rule
    469.1) is scoring.resolve_control_change's job, not this function's.
    """
    player_index = state.turn_player
    unit = find_unit(state, instance_id, from_zone)
    assert unit is not None
    moved_unit = dataclasses.replace(unit, exhausted=exhausted_after, moved_this_turn=unit.moved_this_turn + 1)

    if from_zone == "base":
        player = state.players[player_index]
        new_player = dataclasses.replace(player, base_units=player.base_units - {unit})
        state = replace_player(state, player_index, new_player)
    else:
        bf = _battlefield(state, from_zone)
        remaining_units = bf.units - {unit}
        new_controller = bf.controller if remaining_units else None  # rule 468
        state = replace_battlefield(
            state, dataclasses.replace(bf, units=remaining_units, controller=new_controller)
        )

    if to_zone == "base":
        player = state.players[player_index]
        new_player = dataclasses.replace(player, base_units=player.base_units | {moved_unit})
        return replace_player(state, player_index, new_player)

    bf = _battlefield(state, to_zone)
    if any(u.controller != player_index for u in bf.units):
        raise NotImplementedError(
            "relocate_unit: destination has enemy units present — combat resolution "
            "isn't implemented here (see design/03-action-space.md's combat section); "
            "callers must route enemy-occupied destinations through ResolveCombat instead"
        )
    # Destination is empty or already ours — either way the mover joins
    # whatever's there and control (already ours, or newly established if
    # it was open) doesn't need to change here beyond staying/being ours.
    new_bf = dataclasses.replace(bf, units=bf.units | {moved_unit}, controller=player_index)
    return replace_battlefield(state, new_bf)


def apply_move_unit(state: GameState, action: MoveUnit) -> GameState:
    return relocate_unit(state, action.instance_id, action.from_zone, action.to_zone, exhausted_after=True)


# --- Generation --------------------------------------------------------------


def legal_board_actions(state: GameState, cards: dict[str, CardDef]) -> list[Action]:
    """PlayUnit and MoveUnit candidates only. PlaySpell generation lives in
    search.legal_actions() instead — it needs abilities.py's per-spell
    candidate generators, and abilities.py imports from this module, so
    generating spells here would be a circular import. PlayGear/
    ActivateAbility generation is deferred until their apply() exists.
    PlayUnit candidates include open battlefields for cards with
    can_play_to_open_battlefield set."""
    actions: list[Action] = []
    player = state.players[state.turn_player]

    battlefield_ids = [bf.battlefield_id for bf in state.battlefields]
    controlled_battlefields = [
        bf.battlefield_id for bf in state.battlefields if bf.controller == state.turn_player
    ]

    for card_id in sorted(set(player.hand)):
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

    def add_move_candidates(unit: UnitInstance, from_zone: Zone, to_zone: Zone) -> None:
        if to_zone != "base" and combat.is_combat_triggered(state, unit, to_zone):
            _, _, _, defender_units = combat.determine_sides(state, unit, to_zone)
            destination_effect = battlefield_effect_id(state, to_zone)
            our_pool = combat.effective_might(unit, "attacker", destination_effect)
            for assignment in combat.enumerate_assignments(
                    defender_units, our_pool, "defender", destination_effect):
                action = ResolveCombat(
                    instance_id=unit.instance_id, from_zone=from_zone, to_zone=to_zone,
                    our_assignment=assignment,
                )
                if is_legal_resolve_combat(state, action):
                    actions.append(action)
            return
        action = MoveUnit(instance_id=unit.instance_id, from_zone=from_zone, to_zone=to_zone)
        if is_legal_move_unit(state, action):
            actions.append(action)

    for unit in sorted(player.base_units, key=lambda u: u.instance_id):
        for bf_id in battlefield_ids:
            add_move_candidates(unit, "base", bf_id)
    for bf in state.battlefields:
        for unit in sorted(bf.units, key=lambda u: u.instance_id):
            if unit.controller != state.turn_player:
                continue
            for to_zone in ["base"] + [b for b in battlefield_ids if b != bf.battlefield_id]:
                add_move_candidates(unit, bf.battlefield_id, to_zone)

    return actions
