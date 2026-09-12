from solver.engine.abilities import YASUO_WINDRIDER, apply_move_triggers
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance


def make_yasuo(instance_id=1, moved_this_turn=0, exhausted=False):
    return UnitInstance(
        card_id=YASUO_WINDRIDER, instance_id=instance_id, controller=0, might=2,
        keywords=frozenset({"Ganking"}), exhausted=exhausted, damage=0, is_token=False,
        moved_this_turn=moved_this_turn,
    )


def make_state(yasuo):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=7),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, frozenset({yasuo}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def test_no_point_before_third_move():
    for count in (0, 1, 2):
        state = make_state(make_yasuo(moved_this_turn=count))
        result = apply_move_triggers(state, 1)
        assert result.players[0].score == 7


def test_point_granted_exactly_on_third_move():
    state = make_state(make_yasuo(moved_this_turn=3))
    result = apply_move_triggers(state, 1)
    assert result.players[0].score == 8


def test_no_repeat_trigger_past_third_move():
    """The card fires once, at exactly the third move — not every move
    from then on."""
    state = make_state(make_yasuo(moved_this_turn=4))
    result = apply_move_triggers(state, 1)
    assert result.players[0].score == 7


def test_only_controllers_own_move_counts():
    import dataclasses

    yasuo = make_yasuo(moved_this_turn=3)
    enemy_yasuo = dataclasses.replace(yasuo, controller=1)
    state = make_state(yasuo)
    state = dataclasses.replace(state, battlefields=(
        BattlefieldState("left", 1, frozenset({enemy_yasuo}), None),
        state.battlefields[1],
    ))
    result = apply_move_triggers(state, enemy_yasuo.instance_id)
    assert result.players[0].score == 7  # not granted to us — it's the opponent's card
