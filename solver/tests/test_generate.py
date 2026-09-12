import random

from solver.engine.actions import MoveUnit
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from solver.generate import (
    CARD_POOL,
    MAX_SOLUTION_COUNT,
    MIN_STRATEGY_SIZE,
    STARTING_SCORE,
    evaluate_candidate,
    generate,
    sample_position,
)
from solver.search import count_winning_strategies, solve


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


def test_sample_position_starts_at_six_with_two_to_four_units():
    rng = random.Random(1234)
    for _ in range(50):
        root, cards = sample_position(rng)
        assert root.players[0].score == STARTING_SCORE
        total_our_units = len(root.players[0].base_units) + sum(
            len([u for u in bf.units if u.controller == 0]) for bf in root.battlefields
        )
        assert 2 <= total_our_units <= 4
        assert len(root.scored_this_turn) <= 1
        for card_id in root.players[0].hand:
            assert card_id in CARD_POOL


def test_sample_position_is_internally_consistent():
    """Every sampled position must be legal board state: a battlefield's
    controller matches who's actually posted there, and card ids used
    anywhere are present in the returned cards dict."""
    rng = random.Random(99)
    for _ in range(50):
        root, cards = sample_position(rng)
        for bf in root.battlefields:
            if bf.units:
                controllers = {u.controller for u in bf.units}
                assert controllers == {bf.controller}
            else:
                assert bf.controller is None
        for unit in root.players[0].base_units:
            assert unit.card_id in cards


def test_count_winning_strategies_flags_the_symmetric_two_unit_puzzle_as_too_easy():
    # Same shape as puzzle 1 / test_search.py's "conquer both battlefields"
    # case: two interchangeable units, two open battlefields, score 6. Any
    # of the 4 initial moves (either unit to either battlefield) still
    # wins from there, so this should read as MANY correct first moves —
    # exactly the "too easy" signal the solution-count filter exists for.
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset({make_unit(1), make_unit(2)}), hand=(),
                        runes=RunePool(available=()), score=6),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    count = count_winning_strategies(root, cards={}, max_depth=4)
    assert count > MAX_SOLUTION_COUNT


def test_count_winning_strategies_is_one_for_a_forced_line():
    # Only one unit, one battlefield already Scored this turn (via Hold),
    # the other open: the single unit's only useful move is into the open
    # battlefield for the Final Point. Exactly 1 correct first move.
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset({make_unit(1)}), hand=(),
                        runes=RunePool(available=()), score=7),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", 0, frozenset(), None),
        ),
        scored_this_turn=frozenset({"right"}),
        cards_played_this_turn=0,
    )
    assert count_winning_strategies(root, cards={}, max_depth=4) == 1


def test_evaluate_candidate_rejects_short_solutions():
    # The classic 2-action "conquer both" shape is solvable but shorter
    # than MIN_STRATEGY_SIZE — must be rejected regardless of anything else.
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset({make_unit(1), make_unit(2)}), hand=(),
                        runes=RunePool(available=()), score=6),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    assert solve(root, cards={}, max_depth=4) is not None
    assert evaluate_candidate(root, cards={}, puzzle_id="test") is None


def test_generate_survivors_all_satisfy_the_filters():
    survivors, attempts = generate(count=2, seed=42, attempt_multiplier=500)
    assert attempts > 0
    for result in survivors:
        meta = result["_generation_meta"]
        assert meta["solution_length"] >= MIN_STRATEGY_SIZE
        assert 1 <= meta["solution_count"] <= MAX_SOLUTION_COUNT
        assert result["root"] in result["nodes"]


def test_generate_is_reproducible_with_a_seed():
    survivors_a, attempts_a = generate(count=2, seed=7, attempt_multiplier=500)
    survivors_b, attempts_b = generate(count=2, seed=7, attempt_multiplier=500)
    assert attempts_a == attempts_b
    assert [s["puzzle_id"] for s in survivors_a] == [s["puzzle_id"] for s in survivors_b]
