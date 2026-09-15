from solver.engine import legends
from solver.engine.actions import ActivateAbility, RunePayment
from solver.engine.legends import LEGEND_SOURCE_ID, YASUO_UNFORGIVEN
from solver.engine.state import (
    BattlefieldState,
    GameState,
    LegendState,
    PlayerState,
    RunePool,
    UnitInstance,
    canonical_key,
)
from solver.search import apply, legal_actions

PAYMENT = RunePayment(energy_runes=("Fury", "Fury"), power_runes=())


def make_unit(instance_id, controller=0, might=2, exhausted=False):
    return UnitInstance(card_id="ogn-010-298", instance_id=instance_id, controller=controller,
                         might=might, keywords=frozenset(), exhausted=exhausted, damage=0, is_token=False)


def make_state(base_units=frozenset(), left_units=frozenset(), left_ctrl=None,
                legend=LegendState(YASUO_UNFORGIVEN), runes=("Fury", "Fury")):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=(), runes=RunePool(available=runes),
                        score=0, legend=legend),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", left_ctrl, left_units, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def activate(instance_id, destination, payment=PAYMENT):
    return ActivateAbility(source_id=LEGEND_SOURCE_ID, ability_id=YASUO_UNFORGIVEN,
                            params=(instance_id, destination), rune_payment=payment)


def test_legend_ability_moves_a_unit_from_base_and_pays_its_costs():
    unit = make_unit(1)
    state = make_state(base_units=frozenset({unit}))
    action = activate(1, "left")
    assert legends.is_legal_legend_ability(state, action)

    new_state = apply(state, action, {})
    assert new_state.players[0].base_units == frozenset()
    assert next(iter(new_state.battlefields[0].units)).instance_id == 1
    assert new_state.battlefields[0].controller == 0  # established control
    assert new_state.players[0].legend.exhausted is True  # paid its Exhaust cost
    assert new_state.players[0].runes.energy_spent == 2  # paid 2 Energy by Exhausting


def test_legend_ability_cannot_fire_twice():
    """Its cost includes Exhaust, so once used it's done for the turn."""
    unit = make_unit(1)
    state = make_state(base_units=frozenset({unit}),
                        legend=LegendState(YASUO_UNFORGIVEN, exhausted=True))
    assert not legends.is_legal_legend_ability(state, activate(1, "left"))


def test_legend_ability_requires_having_that_legend():
    unit = make_unit(1)
    assert not legends.is_legal_legend_ability(make_state(base_units=frozenset({unit}), legend=None),
                                                activate(1, "left"))


def test_legend_ability_requires_affording_the_energy_cost():
    unit = make_unit(1)
    state = make_state(base_units=frozenset({unit}), runes=("Fury",))  # only 1, needs 2
    assert not legends.is_legal_legend_ability(state, activate(1, "left", RunePayment(("Fury",), ())))


def test_yasuo_unforgiven_cannot_move_battlefield_to_battlefield():
    """"Move a friendly unit to or from its base" - one end must be Base,
    narrower than Ride The Wind's unrestricted move."""
    unit = make_unit(1)
    state = make_state(left_units=frozenset({unit}), left_ctrl=0)
    assert not legends.is_legal_legend_ability(state, activate(1, "right"))


def test_yasuo_unforgiven_can_pull_a_unit_back_to_base():
    unit = make_unit(1)
    state = make_state(left_units=frozenset({unit}), left_ctrl=0)
    action = activate(1, "base")
    assert legends.is_legal_legend_ability(state, action)
    new_state = apply(state, action, {})
    assert new_state.battlefields[0].units == frozenset()
    assert next(iter(new_state.players[0].base_units)).instance_id == 1


def test_legend_ability_cannot_target_an_enemy_unit():
    enemy = make_unit(1, controller=1)
    state = make_state(left_units=frozenset({enemy}), left_ctrl=1)
    assert not legends.is_legal_legend_ability(state, activate(1, "base"))


def test_legend_ability_appears_in_legal_actions():
    unit = make_unit(1)
    state = make_state(base_units=frozenset({unit}))
    actions = [a for a in legal_actions(state, {})
               if isinstance(a, ActivateAbility) and a.ability_id == YASUO_UNFORGIVEN]
    assert any(a.params == (1, "left") for a in actions)
    assert all(a.source_id == LEGEND_SOURCE_ID for a in actions)


def test_no_legend_means_no_legend_actions():
    unit = make_unit(1)
    state = make_state(base_units=frozenset({unit}), legend=None)
    assert not [a for a in legal_actions(state, {}) if isinstance(a, ActivateAbility)]


def test_canonical_key_distinguishes_legend_exhaustion():
    """Otherwise the transposition table would treat 'Legend already used'
    as the same position as 'Legend still available'."""
    unit = make_unit(1)
    ready = make_state(base_units=frozenset({unit}))
    used = make_state(base_units=frozenset({unit}),
                       legend=LegendState(YASUO_UNFORGIVEN, exhausted=True))
    assert canonical_key(ready) != canonical_key(used)


def test_canonical_key_ignores_legend_when_absent_on_both():
    unit = make_unit(1)
    a = make_state(base_units=frozenset({unit}), legend=None)
    b = make_state(base_units=frozenset({unit}), legend=None)
    assert canonical_key(a) == canonical_key(b)
