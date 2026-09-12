"""IDDFS solver. See design/05-dfs-solver.md and design/09-combat-resolution.md.

Scope note: pruning here is just the depth cap + transposition table (no
separate "no path to score" dead-end heuristic yet). Branching is still
small enough that full search at each depth is cheap, and writing a
speculative pruning rule against action types not yet exercised by a real
puzzle risks encoding wrong logic no test can meaningfully check. Revisit
once the action space is richer.

`legal_actions()` here composes actions.py's board-only legality
(legal_board_actions — PlayUnit/MoveUnit/ResolveCombat) with abilities.py's
registered spell candidates, since generating PlaySpell candidates needs
abilities.py and abilities.py imports from actions.py, so it can't live in
actions.py without a circular import. It can include moves apply() can't
resolve yet (e.g. a spell moving a unit onto an occupied battlefield —
spell-triggered combat isn't wired up yet, only Standard-Move-triggered
combat is, see design/09-combat-resolution.md). The search catches that
`NotImplementedError` and skips the action rather than crashing, which
correctly limits what puzzles this solver can currently solve without the
legality checks having to lie about what the rules allow.

`solve()` returns a **strategy** (dict[StateKey, Action]), not a flat
path — see design/09-combat-resolution.md's "solve()'s return type"
section for why a flat path can't represent a solution once an opponent's
adversarial choice can lead to different resulting states.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .engine import abilities, combat, scoring
from .engine.actions import (
    Action,
    ActivateAbility,
    MoveUnit,
    PlaySpell,
    PlayUnit,
    ResolveCombat,
    apply_move_unit,
    apply_play_unit,
    find_unit,
    generate_rune_payments,
    legal_board_actions,
)
from .engine.cards import CardDef
from .engine.state import GameState, canonical_key

StateKey = tuple
Strategy = dict[StateKey, Action]


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

    # ActivateAbility candidates: one registry per unit currently on the
    # board (not hand), keyed by card_id — same registry-lookup pattern as
    # spells, but scanning units instead of cards in hand.
    all_units = list(player.base_units) + [u for bf in state.battlefields for u in bf.units if u.controller == state.turn_player]
    for unit in all_units:
        entry = abilities.ABILITY_EFFECTS.get(unit.card_id)
        if entry is None:
            continue
        _, _, generate_candidates = entry
        for params in generate_candidates(state):
            action = ActivateAbility(source_id=unit.instance_id, ability_id=unit.card_id,
                                      params=params, rune_payment=None)
            if abilities.is_legal_activate_ability(state, action):
                result.append(action)

    # PlayUnit "when you play me" trigger candidates: legal_board_actions
    # already generated the plain (trigger_params=()) form for every
    # affordable PlayUnit — this adds the "use the trigger" variants on
    # top, one per registered card's own candidate generator.
    for base_action in [a for a in result if isinstance(a, PlayUnit)]:
        entry = abilities.UNIT_PLAY_TRIGGERS.get(base_action.card_id)
        if entry is None:
            continue
        card = cards[base_action.card_id]
        _, _, generate_trigger_candidates = entry
        for trigger_params in generate_trigger_candidates(state, base_action, card):
            triggered = dataclasses.replace(base_action, trigger_params=trigger_params)
            if abilities.is_legal_unit_play_trigger(state, triggered, card):
                result.append(triggered)
    return result


def apply(state: GameState, action: Action, cards: dict[str, CardDef]) -> GameState:
    """Board mechanics + scoring consequences for one action — composes
    actions.py (board state) with scoring.py (points); see both modules'
    docstrings for why the split exists.

    `ResolveCombat`, and a `PlayUnit` with non-empty `trigger_params`,
    deliberately raise: neither can produce a single resulting state on
    its own once a triggered effect can cause combat (the opponent's
    damage-assignment response is still pending) — use `solve()`, or
    `combat.apply_combat`/`abilities.resolve_unit_play_trigger_outcomes`
    directly with a chosen opponent assignment, instead.
    """
    if isinstance(action, PlayUnit):
        if action.trigger_params:
            raise NotImplementedError(
                "apply: PlayUnit with trigger_params can have multiple outcomes — see search.solve()"
            )
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

    if isinstance(action, ActivateAbility):
        return abilities.apply_ability(state, action)

    raise NotImplementedError(
        f"apply: {type(action).__name__} not supported yet (see design/03-action-space.md / "
        f"design/09-combat-resolution.md — ResolveCombat has no single-state apply(), see search.solve())"
    )


def solve(root: GameState, cards: dict[str, CardDef], max_depth: int = 12) -> Optional[Strategy]:
    """Iterative-deepening DFS: try depth 1, then 2, ... up to max_depth,
    returning the first (shallowest-found) winning strategy, or None if
    no win exists within max_depth. A strategy is a map from every state
    the player might find themselves in (including states reached via an
    opponent's forced combat-assignment branch) to the one action to take
    from there.
    """
    transposition_table: dict[tuple, bool] = {}
    for depth_limit in range(1, max_depth + 1):
        result = _dfs(root, depth_limit, cards, transposition_table)
        if result is not None:
            return result
    return None


def _dfs(state: GameState, remaining: int, cards: dict[str, CardDef],
         ttable: dict[tuple, bool]) -> Optional[Strategy]:
    if scoring.is_winning(state):
        return {}

    if remaining == 0:
        return None

    key = canonical_key(state)
    ttable_key = (key, remaining)
    if ttable.get(ttable_key):
        return None

    for action in legal_actions(state, cards):
        if isinstance(action, ResolveCombat):
            result = _resolve_combat_search(state, action, remaining, cards, ttable)
        elif isinstance(action, PlayUnit) and action.trigger_params:
            outcomes = abilities.resolve_unit_play_trigger_outcomes(state, action, cards[action.card_id])
            result = _and_or_search(state, action, outcomes, remaining, cards, ttable)
        else:
            try:
                child = apply(state, action, cards)
            except NotImplementedError:
                result = None
            else:
                sub = _dfs(child, remaining - 1, cards, ttable)
                result = None if sub is None else {**sub, key: action}
        if result is not None:
            return result

    ttable[ttable_key] = True
    return None


def _resolve_combat_search(state: GameState, action: ResolveCombat, remaining: int,
                            cards: dict[str, CardDef], ttable: dict[tuple, bool]) -> Optional[Strategy]:
    """Thin wrapper: computes ResolveCombat's outcomes, then defers to the
    shared _and_or_search."""
    mover = find_unit(state, action.instance_id, action.from_zone)
    outcomes = combat.enumerate_combat_outcomes(state, mover, action.from_zone, action.to_zone, action.our_assignment)
    outcomes = [scoring.resolve_control_change(state, o, action.to_zone) for o in outcomes]
    return _and_or_search(state, action, outcomes, remaining, cards, ttable)


def _and_or_search(state: GameState, action: Action, outcomes: list[GameState], remaining: int,
                    cards: dict[str, CardDef], ttable: dict[tuple, bool]) -> Optional[Strategy]:
    """The AND-node: `action` already bakes in our own choice (a specific
    damage assignment, tried in `legal_actions`'s outer OR-loop via
    `_dfs`); `outcomes` is every possible way the adversary's response can
    resolve it. For `action` to be validated, EVERY outcome must still
    lead to a win — see design/09-combat-resolution.md. Shared by
    ResolveCombat and any "when played" trigger whose effect can cause
    combat (abilities.UNIT_PLAY_TRIGGERS), since both reduce to the same
    shape once their outcomes are computed.
    """
    key = canonical_key(state)
    merged: Strategy = {}
    for child in outcomes:
        sub = _dfs(child, remaining - 1, cards, ttable)
        if sub is None:
            return None  # this adversary response defeats us — action doesn't survive
        merged.update(sub)

    merged[key] = action
    return merged
