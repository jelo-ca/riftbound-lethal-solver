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
    """
    available: tuple[Domain, ...]  # the runes held this turn
    energy_spent: int = 0  # how many have been Exhausted
    power_spent: tuple[Domain, ...] = ()  # domains already Recycled


def energy_capacity(pool: RunePool) -> int:
    """Runes still able to be Exhausted for Energy — any domain will do."""
    return len(pool.available) - pool.energy_spent


def ready_runes(pool: RunePool, count: Optional[int] = None) -> RunePool:
    """Un-Exhaust up to `count` runes (all of them when None), restoring
    Energy capacity — Ekko, Recurrent's "[Deathknell] Recycle me to ready
    your runes".

    Readying touches the Exhausted state only. It does NOT give back
    Recycle capacity: a Recycled rune has already produced its Power, and
    readying is about untapping, not undoing that. So only `energy_spent`
    moves.

    Deliberately NOT paired with a channel operation. Channelling pulls a
    fresh rune off the Rune Deck, which this model doesn't have, and every
    printed channel in Origins reads "channel N runes EXHAUSTED" — a rune
    arriving with its Energy already spent and its domain unknowable,
    which can pay nothing except a domain-free Recycle cost. See
    engine/coverage.py for how those cards are classified instead.
    """
    if count is None:
        return dataclasses.replace(pool, energy_spent=0)
    return dataclasses.replace(pool, energy_spent=max(0, pool.energy_spent - count))


def power_capacity(pool: RunePool, domain: Optional[Domain]) -> int:
    """Runes of `domain` still able to be Recycled for Power. `None`
    counts every domain, for a domain-free (rainbow) cost."""
    if domain is None:
        return len(pool.available) - len(pool.power_spent)
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
    )


def _canonical_units(units: frozenset[UnitInstance]) -> tuple:
    return tuple(sorted(_canonical_unit(u) for u in units))


def _canonical_player(player: PlayerState) -> tuple:
    return (
        _canonical_units(player.base_units),
        tuple(sorted(player.hand)),
        # Both spend-trackers are significant: the same starting runes with
        # different amounts already Exhausted or Recycled are genuinely
        # different positions.
        (tuple(sorted(player.runes.available)), player.runes.energy_spent,
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
    )
