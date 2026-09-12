from solver.author_puzzle_004 import RIDE_THE_WIND_CARD, build_root
from solver.engine.abilities import RIDE_THE_WIND
from solver.engine.actions import MoveUnit, PlaySpell, RunePayment
from solver.engine.scoring import is_winning
from solver.export import export_puzzle
from solver.search import apply, legal_actions, solve

CARDS = {RIDE_THE_WIND: RIDE_THE_WIND_CARD}


def test_puzzle_004_solves_in_one_action():
    root = build_root()
    strategy = solve(root, CARDS, max_depth=3)
    assert strategy is not None
    assert len(strategy) == 1
    action = next(iter(strategy.values()))
    assert isinstance(action, PlaySpell)
    assert action.card_id == RIDE_THE_WIND


def test_puzzle_004_the_trap_a_standard_move_is_illegal():
    """The whole point: the conqueror is exhausted from its earlier
    Conquer this turn, so a plain Standard Move to "right" isn't even a
    legal option -- only Ride The Wind's readying effect makes the
    "extra" action possible."""
    root = build_root()
    actions = legal_actions(root, CARDS)
    assert not any(isinstance(a, MoveUnit) for a in actions)  # exhausted, no Standard Move available


def test_puzzle_004_ride_the_wind_wins():
    root = build_root()
    conqueror = next(iter(root.battlefields[0].units))
    action = PlaySpell(
        card_id=RIDE_THE_WIND,
        params=(conqueror.instance_id, "right"),
        rune_payment=RunePayment(energy_runes=("Fury", "Fury"), power_runes=("Chaos",)),
    )
    new_state = apply(root, action, CARDS)
    assert is_winning(new_state)
    assert new_state.players[0].score == 8


def test_puzzle_004_exports_cleanly():
    root = build_root()
    result = export_puzzle("puzzle-004-extra-innings", root, CARDS)
    assert len(result["solution"]) == 1
    assert "win" in result["terminal"].values()
