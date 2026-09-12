"""IDDFS solver. See design/05-dfs-solver.md.

Scope note: pruning here is just the depth cap + transposition table (no
separate "no path to score" dead-end heuristic yet). With only PlayUnit and
MoveUnit-onto-an-open-battlefield implemented so far (see actions.py),
branching is already small enough that full search at each depth is cheap,
and writing a speculative pruning rule against action types that don't
exist yet (spells, gear, combat) risks encoding wrong logic no test can
meaningfully check. Revisit once the action space is richer.

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


def apply(state: GameState, action: Action, cards: dict[str, CardDef]) -> GameState:
    """Board mechanics + scoring consequences for one action — composes
    actions.py (board state) with scoring.py (points); see both modules'
    docstrings for why the split exists.
    """
    if isinstance(action, PlayUnit):
        # PlayUnit can only target Base or a battlefield already controlled
        # by the player (rule 355.7/355.8), so it never changes control —
        # no scoring consequence to resolve.
        return apply_play_unit(state, action, cards[action.card_id])

    if isinstance(action, MoveUnit):
        turn_player = state.turn_player
        old_controller = None
        if action.to_zone != "base":
            old_controller = next(
                bf.controller for bf in state.battlefields if bf.battlefield_id == action.to_zone
            )
        new_state = apply_move_unit(state, action)
        if action.to_zone != "base" and old_controller != turn_player:
            new_bf = next(
                bf for bf in new_state.battlefields if bf.battlefield_id == action.to_zone
            )
            if new_bf.controller == turn_player:
                new_state = scoring.resolve_conquer(new_state, action.to_zone)
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
