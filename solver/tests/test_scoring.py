from solver.engine.scoring import (
    VICTORY_SCORE,
    grant_card_effect_point,
    is_winning,
    resolve_conquer,
)
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool


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
