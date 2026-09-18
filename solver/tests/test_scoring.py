import dataclasses

from solver.engine.scoring import (
    ASPIRANTS_CLIMB,
    VICTORY_SCORE,
    grant_card_effect_point,
    is_winning,
    resolve_conquer,
    victory_score,
)
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance


def make_state(score=0, scored_this_turn=frozenset()):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=score),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=scored_this_turn,
        cards_played_this_turn=0,
    )


def test_conquer_below_final_point_always_scores():
    state = make_state(score=3)
    new_state = resolve_conquer(state, "left")
    assert new_state.players[0].score == 4
    assert not is_winning(new_state)


def test_conquer_to_8_with_other_battlefield_held_this_turn_wins():
    # "Borrowed Time" (08-puzzle-concepts.md #2): Hold already Scored
    # "right" this turn (pre-baked into the starting position), so
    # Conquering "left" satisfies "Scored every battlefield this turn"
    # WITHOUT needing to Conquer both — the correction from the blog
    # sources that said "must Conquer both."
    state = make_state(score=7, scored_this_turn=frozenset({"right"}))
    new_state = resolve_conquer(state, "left")
    assert new_state.players[0].score == 8
    assert is_winning(new_state)


def test_conquer_to_8_with_both_battlefields_conquered_this_turn_wins():
    # At 6, conquering "left" is a normal point (not yet a final-point
    # attempt); the second conquer on "right" brings it to 8 and IS the
    # final-point attempt — legal because both battlefields were Scored
    # this turn via Conquer.
    state = make_state(score=6)
    state = resolve_conquer(state, "left")
    assert state.players[0].score == 7
    state = resolve_conquer(state, "right")
    assert state.players[0].score == 8
    assert is_winning(state)


def test_conquer_to_8_with_only_this_battlefield_scored_draws_instead():
    # At 7, conquering only "left" this turn (not "right") must NOT win.
    state = make_state(score=7, scored_this_turn=frozenset())
    new_state = resolve_conquer(state, "left")
    assert new_state.players[0].score == 7  # no point granted
    assert not is_winning(new_state)
    assert "left" in new_state.scored_this_turn  # still marked Scored


def test_card_effect_point_to_8_always_wins():
    state = make_state(score=7)
    new_state = grant_card_effect_point(state)
    assert new_state.players[0].score == 8
    assert is_winning(new_state)
    assert new_state.scored_this_turn == frozenset()  # no battlefield interaction


def test_battlefield_already_scored_this_turn_cannot_score_again():
    # rule 471.1.b — reconquering a battlefield already Scored this turn
    # (by either method) is a no-op for points. See 08-puzzle-concepts.md's
    # "rejected mechanics" section.
    state = make_state(score=3, scored_this_turn=frozenset({"left"}))
    new_state = resolve_conquer(state, "left")
    assert new_state.players[0].score == 3


def test_victory_score_constant_is_8():
    assert VICTORY_SCORE == 8


# --- Aspirant's Climb: "Increase the points needed to win by 1" -----------


def _with_climb(state):
    return dataclasses.replace(state, battlefields=(
        BattlefieldState("left", None, frozenset(), ASPIRANTS_CLIMB),
        state.battlefields[1],
    ))


def test_aspirants_climb_raises_victory_score_by_one():
    state = _with_climb(make_state(score=8))
    assert victory_score(state) == 9
    assert not is_winning(state)  # 8 points is no longer enough
    nine = dataclasses.replace(state, players=(
        dataclasses.replace(state.players[0], score=9), state.players[1]))
    assert is_winning(nine)


def test_without_the_climb_victory_score_is_unchanged():
    assert victory_score(make_state(score=0)) == VICTORY_SCORE == 8


def test_aspirants_climb_shifts_the_final_point_gate_too():
    """Without the Climb, conquering "left" at 7 (with "right" already
    Scored this turn) would BE the Final Point and win at 8 (rule 476).
    With the Climb raising the threshold to 9, the same conquer is now an
    ORDINARY point — 7 isn't within 1 of 9 — so it's unconditional and
    doesn't need every battlefield Scored this turn at all."""
    state = _with_climb(make_state(score=7, scored_this_turn=frozenset()))
    new_state = resolve_conquer(state, "left")
    assert new_state.players[0].score == 8
    assert not is_winning(new_state)


def test_aspirants_climb_is_reachable_through_a_full_solve():
    """End to end via search.solve(), not scoring.py in isolation: a board
    that's a winning Conquer-to-Final-Point at Victory Score 8 stops being
    solvable at the depth that used to win it once Aspirant's Climb raises
    the target to 9."""
    from solver import search

    def make_unit(instance_id, might=1):
        return UnitInstance(card_id="chaff", instance_id=instance_id, controller=0, might=might,
                             keywords=frozenset(), exhausted=False, damage=0, is_token=False)

    def board(score, climb):
        return GameState(
            turn_player=0,
            players=(
                PlayerState(base_units=frozenset({make_unit(1)}), hand=(),
                            runes=RunePool(available=()), score=score),
                PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
            ),
            battlefields=(
                BattlefieldState("left", None, frozenset(), ASPIRANTS_CLIMB if climb else None),
                BattlefieldState("right", 0, frozenset(), None),
            ),
            scored_this_turn=frozenset({"right"}),
            cards_played_this_turn=0,
        )

    without_climb = board(score=7, climb=False)
    assert search.solve(without_climb, {}, max_depth=2) is not None  # Conquer "left" -> 8, wins

    with_climb = board(score=7, climb=True)
    assert search.solve(with_climb, {}, max_depth=2) is None  # only reaches 8, needs 9
