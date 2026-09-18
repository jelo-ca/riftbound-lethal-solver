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
engine. `PlayGear` now has cost/hand bookkeeping here with its per-card
effects in engine/gear.py, following the same split; it is not yet
emitted by action generation, so no line plays Gear until that is wired.
`ActivateAbility`'s apply() body remains out of scope (same reasoning,
just not needed yet), as is `MoveUnit`/relocate_unit onto a battlefield
that already has enemy units present (combat resolution doesn't exist
there).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Optional

from . import battlefields, combat, deaths, traits
from .cards import CardDef
from .combat import Assignment
from .state import (
    BattlefieldState,
    Domain,
    GameState,
    GearInstance,
    RunePool,
    UnitInstance,
    energy_capacity,
    power_capacity,
    replace_player,
)

Zone = str  # "base" or a battlefield_id


@dataclass(frozen=True)
class RunePayment:
    energy_runes: tuple[Domain, ...]  # domains of runes Exhausted for Energy
    power_runes: tuple[Domain, ...]  # domains of runes Recycled for Power
    # Runes Recycled to pay a domain-FREE cost — today only [Deflect]'s
    # "opponents must pay ⟨rainbow⟩ to choose me." Recycled like Power but
    # accepting any domain, so it can't ride in power_runes (which are
    # domain-checked). Recorded separately rather than folded into
    # energy_runes because the two are paid by different rule 164.2.b
    # halves (Recycle vs Exhaust), even though this engine consumes a rune
    # identically either way — nothing here models rune recovery, so the
    # distinction is currently bookkeeping, not mechanics.
    rainbow_runes: tuple[Domain, ...] = ()


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
    # [Accelerate]'s optional additional cost was paid, so this unit enters
    # READY instead of exhausted (rule 143.4.a's default). Genuinely
    # optional — both the plain and accelerated forms are generated as
    # separate legal actions whenever the card has Accelerate and the
    # bigger payment is affordable.
    accelerated: bool = False
    # Runes for the [Deflect] tax owed by this card's "when you play me"
    # trigger, when that trigger chooses an enemy unit that has Deflect.
    # Separate from `rune_payment` because it pays for the TRIGGER's
    # targeting, not the card's own cost, and is spent from what's left
    # after the card itself is paid for. None when no tax is owed.
    trigger_payment: Optional[RunePayment] = None


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
class EnterShowdown:
    """Move into an enemy-occupied battlefield and STOP, leaving the
    showdown open for [Action]/[Reaction] plays before damage.

    Only generated when such a play is actually available; otherwise the
    atomic ResolveCombat below is emitted instead, since a showdown whose
    only legal action is "resolve" is not a decision and folding it away
    keeps search depth honest.
    """
    instance_id: int
    from_zone: Zone
    to_zone: Zone


@dataclass(frozen=True)
class ResolveShowdown:
    """The Combat Damage Step of an already-open showdown. Carries only
    OUR assignment; who is attacking, and which units are even involved,
    is read from the board at resolve time — cards played during the
    window may have moved units in or out."""
    our_assignment: Assignment


@dataclass(frozen=True)
class ResolveAttackTrigger:
    """Resolves a mandatory "when I attack" trigger (abilities.py's
    ATTACK_TRIGGERS registry) for the unit currently attacking in an open
    showdown — before any [Action]/[Reaction] spell and before any
    damage-assignment option exists. See ShowdownState.attack_trigger_
    resolved: while False, this is the ONLY legal action in the showdown.

    `instance_id` names the attacking unit for validation/clarity, though
    it is always derivable from the showdown itself (the attacking side
    is exactly one unit — see combat.py's module docstring — and no spell
    can have joined it yet, since nothing else is legal until this
    resolves). `trigger_params` is opaque and effect-specific, same
    convention as PlayUnit.trigger_params / PlaySpell.params.
    """
    instance_id: int
    trigger_params: tuple


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
    """Gear has NO target. The original shape here carried a
    `target_unit`, assuming equipment that attaches to a body — no Origins
    Gear card works that way. All 30 refer to themselves as "this" and act
    from their own place on the board, so playing one is just paying its
    cost and putting it down. See state.GearInstance.
    """
    card_id: str
    rune_payment: RunePayment


@dataclass(frozen=True)
class ActivateAbility:
    source_id: int  # instance_id of the activating unit
    ability_id: str  # keyed into abilities.ABILITY_EFFECTS, by convention == the source's card_id
    # Opaque, effect-specific — same convention as PlaySpell.params.
    params: tuple
    rune_payment: Optional[RunePayment]  # None for abilities with no rune cost (e.g. exhaust-only)


Action = (PlayUnit | MoveUnit | ResolveCombat | EnterShowdown | ResolveShowdown
          | ResolveAttackTrigger | PlaySpell | PlayGear | ActivateAbility)


# --- Rune payment -----------------------------------------------------------


def generate_rune_payments(pool: RunePool, energy_cost: int, power_cost: int,
                            power_domain: Optional[Domain],
                            rainbow_cost: int = 0) -> list[RunePayment]:
    """All distinct ways to pay `energy_cost` Energy + `power_cost` Power
    (of `power_domain`) + `rainbow_cost` domain-free Recycled runes out of
    `pool`.

    Energy and Power draw on SEPARATE capacities of the same runes (see
    RunePool): Exhausting a rune for Energy doesn't stop it being Recycled
    for Power later, and vice versa. So the two never compete, and the
    only real choice left is which domains absorb a domain-free rainbow
    cost — those DO compete with a later Power cost, since they consume
    Recycle capacity of a specific domain.

    Energy is therefore a pure count (no domain ever checks it) and gets
    one representative split; rainbow splits are enumerated properly,
    because picking Fury over Order here can strand an Order spell later.
    """
    if power_cost > 0 and power_domain is None:
        raise ValueError("power_cost > 0 requires a power_domain")

    if energy_cost > energy_capacity(pool):
        return []
    if power_cost > power_capacity(pool, power_domain):
        return []

    power_runes = tuple([power_domain] * power_cost) if power_cost else ()

    # Recycle capacity left per domain once this cost's own Power is taken.
    remaining_by_domain: dict[Domain, int] = {}
    for domain in set(pool.available):
        left = power_capacity(pool, domain) - (power_cost if domain == power_domain else 0)
        if left > 0:
            remaining_by_domain[domain] = left

    # Energy is domain-agnostic, so which runes are Exhausted is never
    # observable — one representative is exact, not a simplification.
    energy_runes = tuple(pool.available[:energy_cost])

    payments = []
    for rainbow_runes in _domain_multisets(remaining_by_domain, rainbow_cost):
        payments.append(RunePayment(energy_runes=energy_runes, power_runes=power_runes,
                                     rainbow_runes=rainbow_runes))
    return payments


def _domain_multisets(capacity: dict[Domain, int], size: int) -> list[tuple[Domain, ...]]:
    """Every distinct multiset of `size` domains drawable from `capacity`.
    Distinct by domain counts, not by which physical rune — two Fury runes
    are interchangeable, but Fury-vs-Order is a real choice with different
    consequences for what's payable afterwards."""
    if size == 0:
        return [()]
    results: list[tuple[Domain, ...]] = []
    domains = sorted(capacity)

    def recurse(index: int, left: int, picked: tuple[Domain, ...]) -> None:
        if left == 0:
            results.append(picked)
            return
        if index >= len(domains):
            return
        domain = domains[index]
        for count in range(min(capacity[domain], left) + 1):
            recurse(index + 1, left - count, picked + (domain,) * count)

    recurse(0, size, ())
    return results


def payment_is_affordable(pool: RunePool, payment: RunePayment) -> bool:
    """Whether `pool` can still cover `payment`. Energy draws Exhaust
    capacity (domain-agnostic); Power and the rainbow tax are both
    Recycles and draw that domain's Recycle capacity. The two never
    compete — one rune supplies both."""
    if len(payment.energy_runes) > energy_capacity(pool):
        return False
    recycled = list(payment.power_runes + payment.rainbow_runes)
    return all(recycled.count(domain) <= power_capacity(pool, domain) for domain in set(recycled))


def consume_runes(pool: RunePool, payment: RunePayment) -> RunePool:
    """Energy spend is a count; Power and the rainbow tax are both Recycles
    and record their domains."""
    return RunePool(
        available=pool.available,
        energy_spent=pool.energy_spent + len(payment.energy_runes),
        power_spent=pool.power_spent + payment.power_runes + payment.rainbow_runes,
    )


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
        # Gear shares the unit id space: effects that return "a friendly
        # gear, unit, or Hidden card" (Pack of Wonders) name one target by
        # instance_id without caring which kind it is, so the ids must not
        # collide.
        ids += [g.instance_id for g in player.gear]
    for bf in state.battlefields:
        ids += [u.instance_id for u in bf.units]
    return max(ids) + 1


# --- PlayUnit -------------------------------------------------------------


def has_accelerate(card: CardDef) -> bool:
    """Read off the CARD, not a UnitInstance's resolved traits: Accelerate
    is paid at play time, when the unit isn't on the board yet and has no
    zone to resolve positional/aura grants against. Nothing in the set
    grants Accelerate to something that didn't print it."""
    return "Accelerate" in card.keywords and card.accelerate_domain is not None


def play_unit_cost(card: CardDef, accelerated: bool) -> tuple[int, int, Optional[Domain]]:
    """The (Energy, Power, power domain) a PlayUnit must pay. Accelerate
    adds 1 Energy + one rune of the card's own domain on top of the
    printed cost — and since that domain always matches the card's Power
    domain where it has one (see CardDef.accelerate_domain), the whole
    accelerated cost still resolves to a single domain."""
    if not accelerated:
        return card.energy_cost, card.power_cost, card.power_domain
    return card.energy_cost + 1, card.power_cost + 1, card.accelerate_domain


def is_legal_play_unit(state: GameState, action: PlayUnit, card: CardDef) -> bool:
    if card.card_type != "Unit":
        return False
    player = state.players[state.turn_player]
    if action.card_id not in player.hand:
        return False
    if action.accelerated and not has_accelerate(card):
        return False
    energy_cost, power_cost, power_domain = play_unit_cost(card, action.accelerated)
    if len(action.rune_payment.energy_runes) != energy_cost:
        return False
    if len(action.rune_payment.power_runes) != power_cost:
        return False
    if power_cost and any(d != power_domain for d in action.rune_payment.power_runes):
        return False
    # Playing a unit doesn't CHOOSE one, so a card's own cost never carries
    # a [Deflect] tax — that rides on trigger_payment, checked by the
    # trigger's own legality in abilities.py.
    if action.rune_payment.rainbow_runes:
        return False
    if not payment_is_affordable(player.runes, action.rune_payment):
        return False
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
        # rule 143.4.a: units enter the board exhausted — unless [Accelerate]'s
        # additional cost was paid, which is the entire point of the keyword.
        exhausted=not action.accelerated,
        damage=0,
        is_token=False,
    )

    new_hand = list(player.hand)
    new_hand.remove(action.card_id)
    new_runes = consume_runes(player.runes, action.rune_payment)
    state = dataclasses.replace(state, cards_played_this_turn=state.cards_played_this_turn + 1)

    from . import observers  # deferred — see observers.py's module docstring

    if action.target_zone == "base":
        new_player = dataclasses.replace(
            player,
            base_units=player.base_units | {new_unit},
            hand=tuple(new_hand),
            runes=new_runes,
        )
        state = replace_player(state, player_index, new_player)
        return observers.fire_observer_play_triggers(state, new_unit)

    new_player = dataclasses.replace(player, hand=tuple(new_hand), runes=new_runes)
    state = replace_player(state, player_index, new_player)
    bf = _battlefield(state, action.target_zone)
    # rule 466.7.b: playing to an open battlefield (via can_play_to_open_
    # battlefield) establishes control, same as MoveUnit does — playing to
    # a battlefield already controlled by this player is a no-op for
    # controller (it's already theirs).
    new_controller = bf.controller if bf.controller is not None else player_index
    new_bf = dataclasses.replace(bf, units=bf.units | {new_unit}, controller=new_controller)
    state = replace_battlefield(state, new_bf)
    return observers.fire_observer_play_triggers(state, new_unit)


def mint_token_unit(state: GameState, card: CardDef, controller: int, zone: Zone) -> GameState:
    """Creates a fresh token unit straight from `card`'s printed stats
    (is_token=True, enters exhausted per rule 143.4.a same as any other
    unit) directly into `zone` — no hand/cost bookkeeping, since a token
    is never actually played from hand. For card-effect token generation
    (Faithful Manufactor, Vanguard Captain) rather than a PlayUnit action;
    does NOT bump `cards_played_this_turn` for the same reason.

    Establishes control the same way apply_play_unit does when entering
    a battlefield — matters when the token's own card text sends it to an
    open battlefield, though neither card in the pool today does that."""
    new_unit = UnitInstance(
        card_id=card.card_id,
        instance_id=next_instance_id(state),
        controller=controller,
        might=card.might if card.might is not None else 0,
        keywords=card.keywords,
        exhausted=True,
        damage=0,
        is_token=True,
    )
    if zone == "base":
        player = state.players[controller]
        new_player = dataclasses.replace(player, base_units=player.base_units | {new_unit})
        return replace_player(state, controller, new_player)
    bf = _battlefield(state, zone)
    new_controller = bf.controller if bf.controller is not None else controller
    new_bf = dataclasses.replace(bf, units=bf.units | {new_unit}, controller=new_controller)
    return replace_battlefield(state, new_bf)


# --- PlayGear -------------------------------------------------------------


def is_legal_play_gear(state: GameState, action: PlayGear, card: CardDef) -> bool:
    """Cost and hand checks only. Gear has no target and no placement
    choice — it isn't played "to" anywhere, so none of PlayUnit's rule
    355.7/355.8 zone restrictions apply. Its own text is the per-card
    registry's business (engine/gear.py), same split as PlaySpell."""
    if card.card_type != "Gear":
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
    # Playing Gear chooses no unit, so nothing can charge a [Deflect] tax.
    if action.rune_payment.rainbow_runes:
        return False
    return payment_is_affordable(player.runes, action.rune_payment)


def apply_play_gear(state: GameState, action: PlayGear, card: CardDef) -> GameState:
    """Board mechanics only: spend the runes, drop the card from hand, and
    put the Gear down. Any "when you play this" text is the registry's
    job, exactly as apply_play_unit leaves triggers to abilities.py."""
    player_index = state.turn_player
    player = state.players[player_index]

    new_gear = GearInstance(
        card_id=card.card_id,
        instance_id=next_instance_id(state),
        exhausted=card.gear_enters_exhausted,
    )
    new_hand = list(player.hand)
    new_hand.remove(action.card_id)
    state = dataclasses.replace(state, cards_played_this_turn=state.cards_played_this_turn + 1)
    return replace_player(state, player_index, dataclasses.replace(
        player,
        hand=tuple(new_hand),
        runes=consume_runes(player.runes, action.rune_payment),
        gear=player.gear | {new_gear},
    ))


def find_gear(state: GameState, instance_id: int) -> Optional[tuple[GearInstance, int]]:
    """The Gear with this instance_id and whose player holds it, or None."""
    for index, player in enumerate(state.players):
        for gear in player.gear:
            if gear.instance_id == instance_id:
                return gear, index
    return None


def replace_gear(state: GameState, controller: int, old: GearInstance,
                  new: Optional[GearInstance]) -> GameState:
    """Swap one Gear for an updated copy, or remove it entirely when `new`
    is None (Treasure Trove's "Kill this")."""
    player = state.players[controller]
    remaining = player.gear - {old}
    if new is not None:
        remaining = remaining | {new}
    return replace_player(state, controller, dataclasses.replace(player, gear=remaining))


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
    # rainbow_runes are the [Deflect] tax on whatever this spell chooses.
    # Affordability is checked here; that the AMOUNT matches what the
    # chosen targets actually charge is abilities.is_legal_play_spell's
    # job, since only the per-card registry knows what a spell targets.
    return payment_is_affordable(player.runes, action.rune_payment)


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
    state = dataclasses.replace(state, cards_played_this_turn=state.cards_played_this_turn + 1)
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
    correctly recomputing the battlefield's controller, and firing any
    [Deathknell] on the way); a Base target has no controller to
    recompute, just removal from that player's base_units — and its own
    death trigger fired here, since that path doesn't go through
    combat.py at all."""
    located = find_unit_anywhere(state, instance_id)
    assert located is not None
    unit, zone = located
    if zone == "base":
        player = state.players[unit.controller]
        new_player = dataclasses.replace(player, base_units=player.base_units - {unit})
        return deaths.fire_death_triggers(
            replace_player(state, unit.controller, new_player), [(unit, "base")])
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
    """Every trait the unit actually has right now — always ask for these
    rather than reading `unit.keywords`, wherever the unit's location or
    board context could matter.

    Delegates to traits.resolved_traits rather than reimplementing it.
    This function used to union `unit.keywords` with the battlefield's
    grants and nothing else, which quietly made it a SECOND, weaker trait
    resolver: it knew about Windswept Hillock but not about auras or
    "while I'm buffed" self-grants. So a Bilgewater Bully that had earned
    [Ganking] could not actually use it to move — the Might half of the
    same grant worked, because that path goes through the real resolver.
    Exactly the two-sources-of-truth defect that made a battlefield-granted
    [Shield] invisible to damage maths before traits.py existed.
    """
    return traits.resolved_traits(state, unit, zone)


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
    our_pool = combat.effective_might(state, unit, action.to_zone, "attacker")
    return action.our_assignment in combat.enumerate_assignments(
        state, action.to_zone, defender_units, our_pool, "defender")


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
        # Both cost modes where the card has [Accelerate] — paying the extra
        # to enter ready is a real choice, not an upgrade, since the runes
        # it eats may be needed elsewhere in the turn.
        for accelerated in ([False, True] if has_accelerate(card) else [False]):
            energy_cost, power_cost, power_domain = play_unit_cost(card, accelerated)
            for payment in generate_rune_payments(
                player.runes, energy_cost, power_cost, power_domain
            ):
                for zone in candidate_zones:
                    action = PlayUnit(card_id=card_id, target_zone=zone, rune_payment=payment,
                                       accelerated=accelerated)
                    if is_legal_play_unit(state, action, card):
                        actions.append(action)

    def add_move_candidates(unit: UnitInstance, from_zone: Zone, to_zone: Zone) -> None:
        if to_zone != "base" and combat.is_combat_triggered(state, unit, to_zone):
            _, _, _, defender_units = combat.determine_sides(state, unit, to_zone)
            our_pool = combat.effective_might(state, unit, to_zone, "attacker")
            for assignment in combat.enumerate_assignments(
                    state, to_zone, defender_units, our_pool, "defender"):
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
