from solver.author_puzzle_002 import build_root
from solver.engine.actions import MoveUnit
from solver.engine.scoring import is_winning
from solver.export import export_puzzle
from solver.search import apply, solve


def test_puzzle_002_solves_in_one_move():
    root = build_root()
    strategy = solve(root, cards={}, max_depth=4)
    assert strategy is not None
    assert len(strategy) == 1
    action = next(iter(strategy.values()))
    assert isinstance(action, MoveUnit)
    assert action.to_zone == "left"


def test_puzzle_002_validates_hold_plus_conquer_correction():
    """The exact case that would break under the wrong (blog-sourced)
    'must Conquer both' assumption: 'right' was Scored via Hold, not
    Conquer, this turn. A single Conquer on 'left' must still win.
    """
    root = build_root()
    assert root.scored_this_turn == frozenset({"right"})
    assert root.players[0].score == 7

    conqueror = next(iter(root.players[0].base_units))
    action = MoveUnit(instance_id=conqueror.instance_id, from_zone="base", to_zone="left")
    new_state = apply(root, action, cards={})

    assert is_winning(new_state)
    assert new_state.players[0].score == 8


def test_puzzle_002_reconquering_right_grants_no_bonus_point():
    """Regression for the 'pull opponent in and reconquer for an extra
    point' idea (rule 471.1.b) — moving the holder away from 'right' and
    then reconquering it does NOT grant a second point for that
    battlefield, since it was already Scored this turn via Hold.
    """
    root = build_root()
    holder = next(iter(root.battlefields[1].units))  # "right"
    state = apply(root, MoveUnit(instance_id=holder.instance_id, from_zone="right", to_zone="base"), cards={})
    assert state.players[0].score == 7  # leaving doesn't cost or grant anything

    conqueror = next(iter(state.players[0].base_units - {holder}))
    state = apply(state, MoveUnit(instance_id=conqueror.instance_id, from_zone="base", to_zone="right"), cards={})
    assert state.players[0].score == 7  # no bonus point for reconquering
    assert not is_winning(state)


def test_puzzle_002_exports_cleanly():
    root = build_root()
    result = export_puzzle("puzzle-002-borrowed-time", root, cards={})
    assert len(result["solution"]) == 1
    assert "win" in result["terminal"].values()
    assert set(result["terminal"].values()) <= {"win", "dead_end"}
