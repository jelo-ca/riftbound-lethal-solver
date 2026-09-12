"""IDDFS solver. See design/05-dfs-solver.md.

Scope note: pruning here is just the depth cap + transposition table (no
separate "no path to score" dead-end heuristic yet). Branching is still
small enough that full search at each depth is cheap, and writing a
speculative pruning rule against action types not yet exercised by a real
puzzle risks encoding wrong logic no test can meaningfully check. Revisit
once the action space is richer.

`legal_actions()` here composes actions.py's board-only legality
(legal_board_actions — PlayUnit/MoveUnit) with abilities.py's registered
spell candidates, since generating PlaySpell candidates needs abilities.py
and abilities.py imports from actions.py, so it can't live in actions.py
without a circular import. It can include moves apply() can't resolve yet
(e.g. MoveUnit onto a battlefield with enemy units — combat resolution
isn't implemented). The search catches that `NotImplementedError` and
skips the action rather than crashing, which correctly limits what
puzzles this solver can currently solve without the legality checks
having to lie about what the rules allow.
"""

from __future__ import annotations

from typing import Optional

from .engine import abilities, scoring
from .engine.actions import (
    Action,
    MoveUnit,
    PlaySpell,
    PlayUnit,
    apply_move_unit,
    apply_play_unit,
    generate_rune_payments,
    legal_board_actions,
)
from .engine.cards import CardDef
from .engine.state import GameState, canonical_key


def legal_actions(state: GameState, cards: dict[str, CardDef]) -> list[Action]:
    result = list(legal_board_actions(state, cards))
    player = state.players[state.turn_player]
    for card_id in set(player.hand):
        card = cards.get(card_id)
        if card is None:
            continue
        entry = abilities.SPELL_EFFECTS.get(card_id)
        if entry is None:
            continue
        _, _, generate_candidates = entry
        payments = generate_rune_payments(player.runes, card.energy_cost, card.power_cost, card.power_domain)
        for payment in payments:
            for params in generate_candidates(state):
                action = PlaySpell(card_id=card_id, params=params, rune_payment=payment)
                if abilities.is_legal_play_spell(state, action, card):
                    result.append(action)
    return result


def apply(state: GameState, action: Action, cards: dict[str, CardDef]) -> GameState:
    """Board mechanics + scoring consequences for one action — composes
    actions.py (board state) with scoring.py (points); see both modules'
    docstrings for why the split exists.
    """
    if isinstance(action, PlayUnit):
        new_state = apply_play_unit(state, action, cards[action.card_id])
        if action.target_zone != "base":
            new_state = scoring.resolve_control_change(state, new_state, action.target_zone)
        return new_state

    if isinstance(action, MoveUnit):
        new_state = apply_move_unit(state, action)
        if action.to_zone != "base":
            new_state = scoring.resolve_control_change(state, new_state, action.to_zone)
        return new_state

    if isinstance(action, PlaySpell):
        return abilities.apply_spell(state, action, cards[action.card_id])

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
