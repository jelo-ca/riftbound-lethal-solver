import multiprocessing
import random

import pytest

from solver import generate as generate_module
from solver.engine.actions import MoveUnit
from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    UnitInstance,
    canonical_key,
)
from solver.generate import (
    CARD_POOL,
    _evaluate_attempt,
    MIN_STRATEGY_SIZE,
    REQUIRED_SOLUTION_COUNT,
    STARTING_SCORE,
    evaluate_candidate,
    generate,
    sample_for_attempt,
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
    assert count > REQUIRED_SOLUTION_COUNT


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
    assert evaluate_candidate(root, cards={}, puzzle_id="test", seen_signatures=set()) is None


@pytest.fixture
def permissive_generation(monkeypatch):
    """Isolate these tests from BOTH things that made them brittle:

    - the live registry/declined list, since they test the dedup
      mechanism rather than which tricks happen to be promoted today;
    - the length filter, since depending on "some seed finds a survivor
      within N attempts" breaks every time the sampler or the filters
      change. It already broke twice — once when a trick was declined,
      once when units started being sampled into hand — and each time the
      fix was to go hunting for a luckier seed, which just reloads the
      gun.

    Survivors become common, so these run in seconds instead of minutes.
    """
    monkeypatch.setattr(generate_module, "known_signatures", lambda: set())
    monkeypatch.setattr(generate_module, "MIN_STRATEGY_SIZE", 1)
    monkeypatch.setattr(generate_module, "_runes_left_over", lambda *args: False)


def test_evaluate_candidate_rejects_an_already_seen_signature(permissive_generation):
    """Puzzle 4's root is a known-good, fully deterministic position: it
    solves, has exactly one winning line, and spends every rune. Running
    it through evaluate_candidate twice with a shared seen_signatures set
    must reject the second call purely on dedup, every other filter
    having already passed once."""
    from solver import author_puzzle_004
    from solver.engine.abilities import RIDE_THE_WIND

    root = author_puzzle_004.build_root()
    cards = {RIDE_THE_WIND: author_puzzle_004.RIDE_THE_WIND_CARD}

    seen: set = set()
    first = evaluate_candidate(root, cards, "test-dedup-1", seen)
    assert first is not None
    second = evaluate_candidate(root, cards, "test-dedup-2", seen)
    assert second is None


def test_pool_and_inline_evaluation_agree_per_attempt():
    """Parallelism is only safe because attempt N evaluates to the same
    thing wherever it runs — that's what lets the parent reconcile dedup
    in attempt order and get worker-count-independent results.

    Checked directly rather than by comparing whole generate() runs:
    monkeypatched filters do NOT reach worker processes (Windows spawns
    fresh interpreters that re-import the module), so a permissive-filter
    comparison would silently pit permissive parent against strict
    workers. This uses the real filters and needs no survivors at all.
    """
    attempts = [(5, i) for i in range(1, 41)]
    inline = [(i, r["puzzle_id"] if r else None) for i, r in map(_evaluate_attempt, attempts)]
    with multiprocessing.Pool(4) as pool:
        pooled_raw = pool.map(_evaluate_attempt, attempts)
    pooled = [(i, r["puzzle_id"] if r else None) for i, r in pooled_raw]
    assert inline == pooled


def test_generation_is_deterministic_per_attempt():
    """The other half of the same property: an attempt's position depends
    only on (seed, attempt index), never on how many attempts preceded
    it — so splitting work across workers can't shift what gets sampled."""
    first = sample_for_attempt(5, 17)
    second = sample_for_attempt(5, 17)
    assert canonical_key(first[0]) == canonical_key(second[0])
    assert canonical_key(sample_for_attempt(5, 17)[0]) != canonical_key(sample_for_attempt(5, 18)[0])


def test_runes_left_over_false_when_the_line_spends_everything():
    from solver import author_puzzle_004, generate
    from solver.engine.abilities import RIDE_THE_WIND

    root = author_puzzle_004.build_root()
    cards = {RIDE_THE_WIND: author_puzzle_004.RIDE_THE_WIND_CARD}
    strategy = solve(root, cards, max_depth=4)
    assert strategy is not None
    assert generate._runes_left_over(root, cards, strategy) is False


def test_runes_left_over_true_when_a_spare_rune_goes_unused():
    import dataclasses

    from solver import author_puzzle_004, generate
    from solver.engine.abilities import RIDE_THE_WIND

    root = author_puzzle_004.build_root()
    cards = {RIDE_THE_WIND: author_puzzle_004.RIDE_THE_WIND_CARD}
    player = root.players[0]
    spare_player = dataclasses.replace(player, runes=RunePool(available=player.runes.available + ("Fury",)))
    root_with_spare = dataclasses.replace(root, players=(spare_player, root.players[1]))
    strategy = solve(root_with_spare, cards, max_depth=4)
    assert strategy is not None
    assert generate._runes_left_over(root_with_spare, cards, strategy) is True


def test_generate_survivors_all_satisfy_the_filters():
    survivors, attempts = generate(count=2, seed=42, attempt_multiplier=500)
    assert attempts > 0
    for result in survivors:
        meta = result["_generation_meta"]
        assert meta["solution_length"] >= MIN_STRATEGY_SIZE
        assert meta["solution_count"] == REQUIRED_SOLUTION_COUNT
        assert result["root"] in result["nodes"]


def test_generate_is_reproducible_with_a_seed():
    survivors_a, attempts_a = generate(count=2, seed=7, attempt_multiplier=500)
    survivors_b, attempts_b = generate(count=2, seed=7, attempt_multiplier=500)
    assert attempts_a == attempts_b
    assert [s["puzzle_id"] for s in survivors_a] == [s["puzzle_id"] for s in survivors_b]
