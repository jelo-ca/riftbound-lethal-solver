from solver.engine.actions import MoveUnit
from solver.engine.search import solve
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance


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


def test_solves_conquer_both_battlefields_for_final_point():
    # "One Point Short" shape (08-puzzle-concepts.md #1): at 6 points, two
    # readied units at base, both battlefields open. The winning line
    # conquers BOTH this turn (6->7->8, the second conquer is the Final
    # Point and is legal because both battlefields got Scored this turn).
    units = frozenset({make_unit(1), make_unit(2)})
    root = make_state(units, score=6)
    solution = solve(root, cards={}, max_depth=4)
    assert solution is not None
    assert len(solution) == 2
    assert all(isinstance(a, MoveUnit) for a in solution)
    targets = {a.to_zone for a in solution}
    assert targets == {"left", "right"}


def test_single_conquer_at_7_is_unsolvable_alone():
    # Same shape but starting at 7 with only ONE unit available: a single
    # Conquer can't satisfy "Scored every battlefield this turn" alone, and
    # there's no second unit or card-effect point available, so this is a
    # genuinely unsolvable position within the modeled action space.
    units = frozenset({make_unit(1)})
    root = make_state(units, score=7)
    solution = solve(root, cards={}, max_depth=4)
    assert solution is None


def test_already_winning_state_returns_empty_solution():
    root = make_state(frozenset(), score=8)
    solution = solve(root, cards={}, max_depth=4)
    assert solution == []


def test_finds_shortest_solution_first():
    # With 3 units available but only 2 battlefields, the winning line
    # still takes exactly 2 actions (IDDFS's depth-limit-1-then-2 order
    # guarantees the shortest win is returned, not a longer one that also
    # happens to work).
    units = frozenset({make_unit(1), make_unit(2), make_unit(3)})
    root = make_state(units, score=6)
    solution = solve(root, cards={}, max_depth=4)
    assert len(solution) == 2
