"""IDDFS solver. See design/05-dfs-solver.md.

Scope note: pruning here is just the depth cap + transposition table (no
separate "no path to score" dead-end heuristic yet). Branching is still
small enough that full search at each depth is cheap, and writing a
speculative pruning rule against action types not yet exercised by a real
puzzle risks encoding wrong logic no test can meaningfully check. Revisit
once the action space is richer.

`legal_actions()` reflects pure rules legality (actions.py's job) and can
include moves apply() can't resolve yet (e.g. MoveUnit onto a battlefield
with enemy units — combat resolution isn't implemented). The search catches
that `NotImplementedError` and skips the action rather than crashing, which
correctly limits what puzzles this solver can currently solve without
actions.py's legality check having to lie about what the rules allow.
"""

from __future__ import annotations

from typing import Optional

from .engine import scoring
from .engine.actions import Action, MoveUnit, PlayUnit, apply_move_unit, apply_play_unit, legal_actions
from .engine.cards import CardDef
from .engine.state import GameState, canonical_key


def _resolve_control_change(state: GameState, new_state: GameState, battlefield_id: str) -> GameState:
    """If `battlefield_id`'s controller changed to `state.turn_player` as a
    result of the action that produced `new_state` from `state`, resolve
    the scoring consequences (rule 469.1: establishing control only scores
    if not already Scored this turn — scoring.resolve_conquer handles
    that check). Shared by PlayUnit (open-battlefield deploy) and MoveUnit
    — both can establish control, per actions.py.
    """
    turn_player = state.turn_player
    old_controller = next(bf.controller for bf in state.battlefields if bf.battlefield_id == battlefield_id)
    if old_controller == turn_player:
        return new_state
    new_bf = next(bf for bf in new_state.battlefields if bf.battlefield_id == battlefield_id)
    if new_bf.controller != turn_player:
        return new_state
    return scoring.resolve_conquer(new_state, battlefield_id)


def apply(state: GameState, action: Action, cards: dict[str, CardDef]) -> GameState:
    """Board mechanics + scoring consequences for one action — composes
    actions.py (board state) with scoring.py (points); see both modules'
    docstrings for why the split exists.
    """
    if isinstance(action, PlayUnit):
        new_state = apply_play_unit(state, action, cards[action.card_id])
        if action.target_zone != "base":
            new_state = _resolve_control_change(state, new_state, action.target_zone)
        return new_state

    if isinstance(action, MoveUnit):
        new_state = apply_move_unit(state, action)
        if action.to_zone != "base":
            new_state = _resolve_control_change(state, new_state, action.to_zone)
        return new_state

    raise NotImplementedError(
        f"apply: {type(action).__name__} not supported yet (see design/03-action-space.md)"
    )


def solve(root: GameState, cards: dict[str, CardDef], max_depth: int = 12) -> Optional[list[Action]]:
    """Iterative-deepening DFS: try depth 1, then 2, ... up to max_depth,
    returning the first (shortest) winning action sequence found, or None
    if no win exists within max_depth.
    """
    # Kept across all depth-limit iterations, not cleared between them: a
    # (state, remaining) FAIL proven at a shallow depth_limit pass is
    # equally valid at a deeper one, since it's keyed on remaining moves
    # from that state, not on the outer iteration (design/05-dfs-solver.md).
    transposition_table: dict[tuple, bool] = {}
    for depth_limit in range(1, max_depth + 1):
        result = _dfs(root, depth_limit, [], cards, transposition_table)
        if result is not None:
            return result
    return None


def _dfs(state: GameState, remaining: int, path: list[Action], cards: dict[str, CardDef],
         ttable: dict[tuple, bool]) -> Optional[list[Action]]:
    if scoring.is_winning(state):
        return path

    if remaining == 0:
        return None

    key = (canonical_key(state), remaining)
    if ttable.get(key):
        return None

    for action in legal_actions(state, cards):
        try:
            child = apply(state, action, cards)
        except NotImplementedError:
            continue
        result = _dfs(child, remaining - 1, path + [action], cards, ttable)
        if result is not None:
            return result

    ttable[key] = True
    return None
