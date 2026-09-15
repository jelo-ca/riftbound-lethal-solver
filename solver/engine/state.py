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


@dataclass(frozen=True)
class RunePool:
    available: tuple[Domain, ...]


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
class PlayerState:
    base_units: frozenset[UnitInstance]
    hand: tuple[str, ...]
    runes: RunePool
    score: int
    # None for a position that doesn't involve a Legend at all — every
    # puzzle authored before Legends existed, and any sampled position
    # that didn't draw one.
    legend: Optional[LegendState] = None


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
    """
    battlefield_id: str
    attacker_controller: int


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
    )


def _canonical_units(units: frozenset[UnitInstance]) -> tuple:
    return tuple(sorted(_canonical_unit(u) for u in units))


def _canonical_player(player: PlayerState) -> tuple:
    return (
        _canonical_units(player.base_units),
        tuple(sorted(player.hand)),
        tuple(sorted(player.runes.available)),
        player.score,
        # Exhaustion matters: a Legend that's already paid its Exhaust cost
        # this turn is a genuinely different position from one that hasn't.
        (player.legend.card_id, player.legend.exhausted) if player.legend else None,
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
        # Mid-showdown is a genuinely different position from the same
        # board after damage resolved — conflating them would let the
        # transposition table prune real lines.
        (state.showdown.battlefield_id, state.showdown.attacker_controller)
        if state.showdown else None,
    )
