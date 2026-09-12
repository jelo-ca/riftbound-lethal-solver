from solver.author_puzzle_001 import build_root
from solver.engine.actions import MoveUnit
from solver.engine.scoring import is_winning
from solver.export import export_puzzle
from solver.search import apply


def test_puzzle_001_solves_in_two_moves():
    root = build_root()
    result = export_puzzle("puzzle-001-one-point-short", root, cards={})
    assert len(result["solution"]) == 2
    assert set(result["terminal"].values()) == {"win"}


def test_puzzle_001_the_trap_a_single_conquer_does_not_win():
    """The whole point of this puzzle: the obvious line — throw one unit
    at a battlefield, expect the 8th point — fails. rule 474-476's Final
    Point restriction requires Scoring every battlefield this turn; one
    Conquer alone doesn't satisfy it.
    """
    root = build_root()
    one_unit = next(iter(root.players[0].base_units))
    action = MoveUnit(instance_id=one_unit.instance_id, from_zone="base", to_zone="left")
    after_one_conquer = apply(root, action, cards={})

    assert not is_winning(after_one_conquer)
    assert after_one_conquer.players[0].score == 7  # no point granted, per rule 476.1
    assert "left" in after_one_conquer.scored_this_turn  # still marked Scored


def test_puzzle_001_committing_both_units_wins():
    root = build_root()
    units = sorted(root.players[0].base_units, key=lambda u: u.instance_id)

    state = apply(root, MoveUnit(instance_id=units[0].instance_id, from_zone="base", to_zone="left"), cards={})
    assert not is_winning(state)

    state = apply(state, MoveUnit(instance_id=units[1].instance_id, from_zone="base", to_zone="right"), cards={})
    assert is_winning(state)
    assert state.players[0].score == 8
