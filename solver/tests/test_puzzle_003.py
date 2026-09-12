from solver.author_puzzle_003 import RIDE_THE_WIND_CARD, build_root
from solver.engine.abilities import RIDE_THE_WIND
from solver.engine.actions import MoveUnit, PlaySpell, RunePayment
from solver.engine.scoring import is_winning
from solver.export import export_puzzle
from solver.search import apply, solve

CARDS = {RIDE_THE_WIND: RIDE_THE_WIND_CARD}

# A concrete, hand-picked 3-move sequence: Standard Move (1st, exhausts
# Yasuo), Ride The Wind moves him back and readies him (2nd), Standard
# Move again (3rd, fires the card-effect point). Any 3 moves work per the
# card text — this is just one deterministic example for the tests.
MOVE_1 = MoveUnit(instance_id=1, from_zone="left", to_zone="right")
MOVE_2 = PlaySpell(card_id=RIDE_THE_WIND, params=(1, "left"),
                    rune_payment=RunePayment(energy_runes=("Fury", "Fury"), power_runes=("Chaos",)))
MOVE_3 = MoveUnit(instance_id=1, from_zone="left", to_zone="right")


def test_puzzle_003_solves_in_exactly_three_actions():
    root = build_root()
    strategy = solve(root, CARDS, max_depth=6)
    assert strategy is not None
    assert len(strategy) == 3


def test_puzzle_003_two_moves_do_not_win():
    """The whole point: Yasuo's card-effect point fires on exactly the
    third move, not sooner — two moves alone can't win."""
    root = build_root()
    state = apply(root, MOVE_1, CARDS)
    state = apply(state, MOVE_2, CARDS)
    assert not is_winning(state)
    assert state.players[0].score == 7
    yasuo = next(u for u in state.battlefields[0].units if u.instance_id == 1)
    assert yasuo.moved_this_turn == 2


def test_puzzle_003_third_move_wins():
    root = build_root()
    state = apply(root, MOVE_1, CARDS)
    state = apply(state, MOVE_2, CARDS)
    state = apply(state, MOVE_3, CARDS)
    assert is_winning(state)
    assert state.players[0].score == 8


def test_puzzle_003_exports_cleanly():
    root = build_root()
    result = export_puzzle("puzzle-003-the-long-way-around", root, CARDS, max_solver_depth=6)
    assert len(result["solution"]) == 3
    assert "win" in result["terminal"].values()
