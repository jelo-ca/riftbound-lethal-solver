"""GameState and canonical hashing. See design/02-state-model.md.

Puzzles are single-turn: no Channel Phase, no Awaken/rune-recovery, no
turn-to-turn bookkeeping. Hold is pre-resolved into the starting position,
not modeled as a live transition here.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Literal, Optional

Domain = Literal["Fury", "Calm", "Mind", "Body", "Chaos", "Order"]


@dataclass(frozen=True)
class UnitInstance:
    card_id: str
    instance_id: int
    controller: int
    might: int
    keywords: frozenset[str]
    exhausted: bool
    damage: int
    is_token: bool
    # How many times this unit has moved this turn (Standard Move, a
    # spell-granted move, or moving into/as part of combat all count -
    # rule 456.1: "Spells, Abilities, or other effects may cause a Move").
    # Needed for cards whose own text counts moves (e.g. Yasuo - Windrider:
    # "The third time I move in a turn, you score 1 point") - default 0
    # since most units never reference it.
    moved_this_turn: int = 0
    # A buff is BINARY, not a counter: a unit either carries one or it
    # doesn't, it is worth +1 Might, and buffing an already-buffed unit
    # does nothing. Karma, Channeler's reminder text spells the rule out —
    # "if it doesn't have a buff, it gets a +1 Might buff".
    #
    # Kept as state rather than folded into `might` (which is where
    # unconditional Might changes normally go — see engine/traits.py)
    # because cards READ it: "while I'm buffed, I have an additional
    # +1 Might", "spend any number of buffs". A buff that had been added
    # straight to Might would be invisible to both.
    buffed: bool = False
    # RULES ANSWER (project owner, 2026-09-18): a stunned unit stays on the
    # board, alive and targetable, and its OWN death threshold is entirely
    # unaffected — only its SIDE's damage-dealing pool for the Combat
    # Damage Step ignores it (combat.side_damage_pool is the one place
    # that reads this; traits.effective_might, which still governs this
    # unit's own death threshold, never does). Binary and non-stacking,
    # same "rest of this single-turn puzzle, no expiry bookkeeping" shape
    # as `buffed` above — a puzzle never reaches a second turn.
    stunned: bool = False
    # Udyr, Wildman: "Spend my buff: Choose one you've not chosen this
    # turn — [4 modes]." Which of his own modes have already been picked
    # THIS TURN, keyed by a short mode name (see abilities.py's Udyr
    # section) — his ability can fire more than once if something re-buffs
    # him mid-turn, and each firing must pick a mode not already used.
    # Same per-instance, single-turn-puzzle, no-expiry-bookkeeping shape as
    # `moved_this_turn`/`buffed` above; empty for every unit that isn't
    # Udyr, since nothing else reads it.
    modes_chosen_this_turn: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RunePool:
    """A rune gives up to TWO things per turn, independently: 1 Energy by
    Exhausting it, and 1 Power of its own domain by Recycling it. Order
    doesn't matter — Recycling a ready rune leaves a "floating rune" that
    can still be Exhausted afterwards, and Exhausting one doesn't stop it
    being Recycled later. So the two capacities are tracked separately
    over the same physical runes.

    This corrects the original model, which deleted a rune from the pool
    the moment it paid for anything — roughly halving the real resources
    and making every puzzle authored against it tighter than actual
    Riftbound. The card text is unambiguous that runes persist with a
    ready/exhausted state ("ready 4 friendly runes", "Recycle me to ready
    your runes", and a dozen cards that specify "channel 1 rune
    exhausted", which only needs saying if channelling normally arrives
    ready).

    Energy is domain-agnostic, so its spend is just a count; Power is
    domain-matched, so its spend records which domains went.

    `available` uses `None` for a DOMAIN-LESS rune — RULING (project
    owner, 2026-09-18): this engine has no Rune Deck (see HANDOFF.md's
    position model), so a "channel N runes" or "add 1 rainbow rune"
    effect can't draw a real domain from anywhere; inventing one would be
    exactly the kind of guess coverage.py exists to forbid. The sound,
    safe reading is that such a rune contributes Energy capacity ONLY
    (it can be Exhausted like any rune) and NEVER Power capacity,
    regardless of domain — see `power_capacity`'s `None`-domain branch,
    which deliberately excludes it, and `add_runes` below, which is how
    one enters the pool. A domain-less rune is still a real rune for
    every other purpose: `ready_runes` un-Exhausts it exactly like any
    other, since nothing about "which domain" bears on readying.
    """
    available: tuple[Optional[Domain], ...]  # the runes held this turn
    energy_spent: int = 0  # how many have been Exhausted
    power_spent: tuple[Domain, ...] = ()  # domains already Recycled


def energy_capacity(pool: RunePool) -> int:
    """Runes still able to be Exhausted for Energy — any domain will do,
    a domain-less (channelled/added) rune included."""
    return len(pool.available) - pool.energy_spent


def add_runes(pool: RunePool, domains: tuple[Optional[Domain], ...],
              exhausted: bool = False) -> RunePool:
    """A rune (or runes) arriving MID-TURN from a card's own text — a
    "channel" or "add" effect — as opposed to `available` at position
    setup, which is always the starting hand of runes (see
    PlayerState.runes's field comment: no Main Deck, so nothing is ever
    channelled from position setup itself).

    `domains` uses `None` per rune for a domain-less arrival (see
    RunePool's docstring) and a real `Domain` when the card states one
    (e.g. a hypothetical "add 1 Fury rune" would pass `("Fury",)` and
    behaves exactly like any other rune from then on).

    `exhausted=True` models "channel N runes EXHAUSTED" (~12 cards use
    this exact phrasing): the rune arrives with its Energy already spent
    THIS turn. It still raises `len(available)` (so a later `ready_runes`
    can un-Exhaust it, same as any rune that spent its own Energy earlier
    this turn), but raises `energy_spent` by the same amount in the same
    call, so it contributes zero NET usable capacity until something
    readies it. Deliberately not folded into `energy_spent` alone without
    also extending `available` — Recycle capacity (for a real-domain
    rune) and the rune's very existence for `ready_runes` both key off
    `available`'s length.
    """
    return dataclasses.replace(
        pool,
        available=pool.available + domains,
        energy_spent=pool.energy_spent + (len(domains) if exhausted else 0),
    )


def sorted_available(available: tuple[Optional[Domain], ...]) -> list:
    """Deterministic ordering of a rune pool's domains for canonical_key
    and export.py — the two MUST agree (HANDOFF.md: anything canonical_key
    treats as significant must also render in export.py, or two distinct
    positions collide). A domain-less rune (`None`) can't be compared to a
    `str` by plain `sorted()`, so this is the one place that ordering is
    decided; both call sites route through it rather than each inventing
    their own key."""
    return sorted(available, key=lambda d: (d is None, d or ""))


def ready_runes(pool: RunePool, count: Optional[int] = None) -> RunePool:
    """Un-Exhaust up to `count` runes (all of them when None), restoring
    Energy capacity — Ekko, Recurrent's "[Deathknell] Recycle me to ready
    your runes".

    Readying touches the Exhausted state only. It does NOT give back
    Recycle capacity: a Recycled rune has already produced its Power, and
    readying is about untapping, not undoing that. So only `energy_spent`
    moves.

    Deliberately a separate function from `add_runes` (channelling), which
    pulls a fresh rune from the Rune Deck this model doesn't have — see
    `add_runes`'s docstring and `RunePool`'s for how a channelled rune is
    represented (domain-less, Energy-only). This function doesn't care
    whether a rune is domain-less or not: readying is purely about the
    Exhausted flag, which every rune carries the same way.
    """
    if count is None:
        return dataclasses.replace(pool, energy_spent=0)
    return dataclasses.replace(pool, energy_spent=max(0, pool.energy_spent - count))


def power_capacity(pool: RunePool, domain: Optional[Domain]) -> int:
    """Runes of `domain` still able to be Recycled for Power. `None`
    counts every REAL domain, for a domain-free (rainbow) cost —
    deliberately EXCLUDING domain-less runes (RunePool's docstring):
    their domain is unknowable, so they may never occupy any Power slot,
    rainbow included. `pool.power_spent` only ever records real domains
    (nothing ever selects a domain-less rune into a payment — see
    actions.generate_rune_payments), so subtracting its length here is
    still exact once the domain-less runes are excluded from the total."""
    if domain is None:
        return sum(1 for d in pool.available if d is not None) - len(pool.power_spent)
    return pool.available.count(domain) - pool.power_spent.count(domain)


@dataclass(frozen=True)
class BattlefieldState:
    battlefield_id: str
    controller: Optional[int]
    units: frozenset[UnitInstance]
    effect_id: Optional[str]


@dataclass(frozen=True)
class LegendState:
    """A player's Legend — a persistent card in its own zone, not a unit
    on the board and never at a battlefield. Modelled as just its card_id
    plus exhaustion, since every Legend ability registered so far pays an
    Exhaust cost (some with Energy on top) and nothing else about a
    Legend's state is reachable from a single-turn puzzle."""
    card_id: str
    exhausted: bool = False


@dataclass(frozen=True)
class GearInstance:
    """A Gear permanent. Gear does NOT attach to a unit — no Origins Gear
    card says "attach" or "equip"; all 30 refer to themselves as "this"
    and act from their own place on the board ("Exhaust: Deal 2 to a unit
    at a battlefield"). So Gear is a standalone permanent owned by a
    player, not an aura on a body, and a unit dying does nothing to it.

    It carries no Might (every printing has Might None) and so never
    fights, never occupies a battlefield, and never contests control.

    `exhausted` is real state: most Gear pays an Exhaust cost to activate.
    Unlike units, Gear enters READY by default — Iron Ballista has to
    spell out "This enters exhausted", which only needs saying because the
    default is the opposite (contrast rule 143.4.a for units).
    """
    card_id: str
    instance_id: int
    exhausted: bool = False


@dataclass(frozen=True)
class PlayerState:
    base_units: frozenset[UnitInstance]
    hand: tuple[str, ...]
    runes: RunePool
    score: int
    # Defaulted so every existing construction still works — Gear was
    # added long after these positions were authored.
    gear: frozenset[GearInstance] = frozenset()
    # None for a position that doesn't involve a Legend at all — every
    # puzzle authored before Legends existed, and any sampled position
    # that didn't draw one.
    legend: Optional[LegendState] = None
    # A tuple, not a frozenset: two dead copies of the same card_id are
    # distinct trash entries, and a set would collapse them. Always empty
    # at position setup (2026-09-17, project owner) — the engine never
    # assumes turn history, same convention as "no Main Deck" — and fills
    # live during the turn as units die or spells resolve (deaths.py's
    # fire_death_triggers, abilities.apply_play_spell_cost). Tokens
    # (UnitInstance.is_token) do NOT go to trash: they cease to exist
    # rather than occupying a zone, since they were never a printed card.
    trash: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShowdownState:
    """An open showdown: a unit has moved into a battlefield holding the
    other player's units (applying Contested status), but the Combat
    Damage Step hasn't resolved yet.

    This window exists because card speeds make it observable. A Slow
    card — which is anything without an explicit marker, including every
    unit and most abilities — cannot be played here, while an [Action] or
    [Reaction] one can. Standard Moves are out entirely: a unit can
    neither join nor leave a showdown by moving, only by being moved by a
    spell or ability (Ride The Wind doing either is the motivating case).

    `attacker_controller` is whoever's unit applied Contested, which is
    not always us — our own effects can move an ENEMY unit onto ground we
    hold, making them the Attacker (see design/09-combat-resolution.md).

    `attack_trigger_resolved` gates a mandatory "when I attack" trigger
    (engine/abilities.py's ATTACK_TRIGGERS): while False, legal_actions()
    offers ONLY the trigger's own resolution — no [Action]/[Reaction]
    spells, no ResolveShowdown — which is what forces Rule 465-adjacent
    triggers like "when I attack, deal 5 damage" to resolve BEFORE any
    damage-assignment options are computed. Defaults True so every
    existing showdown (nothing registered, or none of the cards that use
    this) behaves exactly as before with no call site needing to change.
    """
    battlefield_id: str
    attacker_controller: int
    attack_trigger_resolved: bool = True


@dataclass(frozen=True)
class PendingConquerChoice:
    """A conquer trigger that offers a genuine player choice (which card
    to discard, which spell to replay from trash, ...) recorded on
    GameState instead of resolved inline by scoring.resolve_control_change
    — the same "pending, gates everything else" shape as ShowdownState.
    attack_trigger_resolved, generalized past combat.

    engine/conquer.py documents why this shape was chosen over making
    resolve_control_change itself return a list of alternative resulting
    states: ANY of its ~9 callers (MoveUnit, PlayUnit's open-battlefield
    deploy, ResolveCombat/ResolveShowdown's damage step, or a control-
    changing spell/ability effect) can leave a state pending, and every
    one of them already threads a plain GameState back to its own caller
    via `dataclasses.replace`/`replace_player`/`replace_battlefield` — so
    a new GameState field flows through all of them for free, with none
    of the 9 needing to change. `search.legal_actions()` offers nothing
    but `ResolveConquerTrigger` while this is set, exactly the way
    `ShowdownState.attack_trigger_resolved` gates everything but
    `ResolveAttackTrigger`.

    `kind` distinguishes the two conquer-trigger grammars conquer.py
    implements (UNIT-keyed "when I conquer" vs BATTLEFIELD-keyed "when
    you conquer here"); `key` is the card_id (the unit's or the
    battlefield's) that owns the registered choice, so
    ResolveConquerTrigger's apply() knows which registry to dispatch
    into. `instance_id` names the conquering unit for a unit-keyed
    trigger and is unused (None) for a battlefield-keyed one, whose
    source is the battlefield itself, not a unit.
    """
    kind: Literal["unit", "battlefield"]
    key: str
    battlefield_id: str
    instance_id: Optional[int] = None


@dataclass(frozen=True)
class GameState:
    turn_player: int
    players: tuple[PlayerState, PlayerState]
    battlefields: tuple[BattlefieldState, BattlefieldState]
    scored_this_turn: frozenset[str]
    cards_played_this_turn: int
    # None outside combat. While set, the action space narrows sharply —
    # see ShowdownState.
    showdown: Optional[ShowdownState] = None
    # How many cards have left a hand via discard this turn — Raging Soul's
    # "if you've discarded a card this turn, I have [Assault] and
    # [Ganking]" reads this directly (traits.SELF_CONDITIONALS), the same
    # shape as cards_played_this_turn feeding legion_condition_met.
    # Defaulted so every pre-existing GameState construction still works;
    # a multi-card discard (Scrapyard Champion's "discard 2") bumps this
    # once per card, same as cards_played_this_turn counts one play at a
    # time — Raging Soul's condition is a plain ">0" threshold, so the
    # exact count past 1 is never actually read.
    cards_discarded_this_turn: int = 0
    # None unless a choice-bearing conquer trigger is awaiting resolution —
    # see PendingConquerChoice.
    pending_conquer_choice: Optional[PendingConquerChoice] = None


def _canonical_unit(unit: UnitInstance) -> tuple:
    # instance_id deliberately excluded — see design/02-state-model.md's
    # "Correction from the initial design pass". Two structurally-identical
    # units (e.g. two 1-might Recruit tokens) must compare equal regardless
    # of which instance_id counter values they happen to carry.
    return (
        unit.card_id,
        unit.controller,
        unit.might,
        tuple(sorted(unit.keywords)),
        unit.exhausted,
        unit.damage,
        unit.is_token,
        unit.moved_this_turn,
        unit.buffed,
        unit.stunned,
        tuple(sorted(unit.modes_chosen_this_turn)),
    )


def _canonical_units(units: frozenset[UnitInstance]) -> tuple:
    return tuple(sorted(_canonical_unit(u) for u in units))


def _canonical_player(player: PlayerState) -> tuple:
    return (
        _canonical_units(player.base_units),
        tuple(sorted(player.hand)),
        # Both spend-trackers are significant: the same starting runes with
        # different amounts already Exhausted or Recycled are genuinely
        # different positions. sorted_available (not plain sorted()) since
        # a domain-less rune (None) can't compare against a domain str.
        (tuple(sorted_available(player.runes.available)), player.runes.energy_spent,
         tuple(sorted(player.runes.power_spent))),
        player.score,
        # Exhaustion matters: a Legend that's already paid its Exhaust cost
        # this turn is a genuinely different position from one that hasn't.
        (player.legend.card_id, player.legend.exhausted) if player.legend else None,
        # Same reasoning for Gear, and for the same reason instance_id is
        # excluded from units: two structurally identical Gear pieces are
        # the same position regardless of which counter values they drew.
        tuple(sorted((g.card_id, g.exhausted) for g in player.gear)),
        # NOT deduplicated — two dead copies of the same card_id are two
        # distinct trash entries (Rhasa/Dr. Mundo count them; a "return a
        # unit from trash" choice has two to pick from), so this sorts a
        # multiset rather than a set.
        tuple(sorted(player.trash)),
    )


def _canonical_battlefield(battlefield: BattlefieldState) -> tuple:
    return (
        battlefield.battlefield_id,
        battlefield.controller,
        _canonical_units(battlefield.units),
        battlefield.effect_id,
    )


def replace_player(state: GameState, player_index: int, updated: PlayerState) -> GameState:
    """Return `state` with `state.players[player_index]` swapped for `updated`.
    Shared by actions.py and scoring.py so both modules mutate players the
    same way."""
    players = list(state.players)
    players[player_index] = updated
    return dataclasses.replace(state, players=tuple(players))


def canonical_key(state: GameState) -> tuple:
    """Hashable, order-normalized representation of `state` for use as a
    transposition-table key (design/05-dfs-solver.md). Battlefield order is
    NOT normalized — battlefield_id is a fixed identity, not interchangeable.
    """
    return (
        state.turn_player,
        tuple(_canonical_player(p) for p in state.players),
        tuple(_canonical_battlefield(b) for b in state.battlefields),
        tuple(sorted(state.scored_this_turn)),
        state.cards_played_this_turn,
        state.cards_discarded_this_turn,
        # Mid-showdown is a genuinely different position from the same
        # board after damage resolved — conflating them would let the
        # transposition table prune real lines. attack_trigger_resolved is
        # significant for the same reason moved_this_turn is: two states
        # that look identical on the board otherwise offer different legal
        # actions (only the trigger vs. the normal showdown menu).
        (state.showdown.battlefield_id, state.showdown.attacker_controller,
         state.showdown.attack_trigger_resolved)
        if state.showdown else None,
        # A pending choice changes the legal action space (ONLY
        # ResolveConquerTrigger is offered), so two otherwise-identical
        # boards, one pending and one not, are genuinely different
        # positions — same reasoning as showdown above.
        (state.pending_conquer_choice.kind, state.pending_conquer_choice.key,
         state.pending_conquer_choice.battlefield_id, state.pending_conquer_choice.instance_id)
        if state.pending_conquer_choice else None,
    )
