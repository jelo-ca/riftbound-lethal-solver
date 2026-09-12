import json

import pytest

from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from solver.export import export_puzzle, render_state, state_hash


def make_unit(instance_id, controller=0, might=2, exhausted=False):
    return UnitInstance(
        card_id="ogn-010-298",
        instance_id=instance_id,
        controller=controller,
        might=might,
        keywords=frozenset(),
        exhausted=exhausted,
        damage=0,
        is_token=False,
    )


def make_state(base_units, score):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=(), runes=RunePool(available=()), score=score),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def test_state_hash_is_stable_and_string():
    state = make_state(frozenset({make_unit(1)}), score=6)
    h1 = state_hash(state)
    h2 = state_hash(state)
    assert h1 == h2
    assert isinstance(h1, str)


def test_state_hash_differs_for_different_states():
    s1 = make_state(frozenset({make_unit(1)}), score=6)
    s2 = make_state(frozenset({make_unit(1)}), score=7)
    assert state_hash(s1) != state_hash(s2)


def test_render_state_is_json_serializable():
    state = make_state(frozenset({make_unit(1), make_unit(2)}), score=6)
    rendered = render_state(state)
    json.dumps(rendered)  # must not raise


def test_export_puzzle_solvable_position():
    root = make_state(frozenset({make_unit(1), make_unit(2)}), score=6)
    result = export_puzzle("test-1", root, cards={})

    assert result["schema_version"] == 2
    assert result["puzzle_id"] == "test-1"
    assert result["root"] in result["nodes"]
    assert len(result["solution"]) == 2  # 2 states in the strategy: root, and the state after 1 move
    assert result["root"] in result["solution"]

    # solution's action_ids must all exist somewhere in edges
    all_action_ids = {e["action"]["id"] for edge_list in result["edges"].values() for e in edge_list}
    assert set(result["solution"].values()).issubset(all_action_ids)

    # every edge's "to" is a list; no adversarial branching in this shape
    for edge_list in result["edges"].values():
        for e in edge_list:
            assert isinstance(e["to"], list)
            assert e["adversarial"] is False

    assert "win" in result["terminal"].values()
    json.dumps(result)  # full round-trip: must be valid JSON


def test_export_puzzle_unsolvable_raises():
    root = make_state(frozenset({make_unit(1)}), score=7)  # can't reach 8 alone
    with pytest.raises(ValueError):
        export_puzzle("test-2", root, cards={}, max_solver_depth=4)


def test_export_puzzle_terminal_values_are_only_win_or_dead_end():
    # Invariant check: whatever the graph shape, `terminal` must never
    # contain a value other than the two the schema defines (06-export-
    # schema.md) - no silently-invented third status for a truncated node.
    root = make_state(frozenset({make_unit(1), make_unit(2)}), score=6)
    result = export_puzzle("test-3", root, cards={}, max_solver_depth=4)
    assert set(result["terminal"].values()) <= {"win", "dead_end"}
