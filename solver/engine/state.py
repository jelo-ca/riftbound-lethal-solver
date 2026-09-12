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
class PlayerState:
    base_units: frozenset[UnitInstance]
    hand: tuple[str, ...]
    runes: RunePool
    score: int


@dataclass(frozen=True)
class GameState:
    turn_player: int
    players: tuple[PlayerState, PlayerState]
    battlefields: tuple[BattlefieldState, BattlefieldState]
    scored_this_turn: frozenset[str]
    cards_played_this_turn: int


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
    )
