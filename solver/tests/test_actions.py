import pytest

from solver.engine.actions import (
    MoveUnit,
    PlayUnit,
    RunePayment,
    apply_move_unit,
    apply_play_unit,
    generate_rune_payments,
    is_legal_move_unit,
    is_legal_play_unit,
    legal_board_actions,
)
from solver.engine.cards import CardDef
from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    UnitInstance,
)


def make_unit(card_id="tok", instance_id=1, controller=0, might=1,
              keywords=frozenset(), exhausted=False, damage=0, is_token=True):
    return UnitInstance(card_id, instance_id, controller, might, keywords,
                         exhausted, damage, is_token)


def make_state(hand=(), runes=(), base_units=frozenset(),
               bf0_units=frozenset(), bf1_units=frozenset(),
               bf0_controller=None, bf1_controller=None):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=hand,
                        runes=RunePool(available=runes), score=0),
            PlayerState(base_units=frozenset(), hand=(),
                        runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", bf0_controller, bf0_units, None),
            BattlefieldState("right", bf1_controller, bf1_units, None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


# --- rune payment ---


def test_generate_rune_payment_simple():
    pool = RunePool(available=("Order", "Order", "Fury"))
    payments = generate_rune_payments(pool, energy_cost=1, power_cost=1, power_domain="Order")
    assert len(payments) == 1
    p = payments[0]
    assert p.power_runes == ("Order",)
    assert len(p.energy_runes) == 1


def test_generate_rune_payment_insufficient_domain():
    pool = RunePool(available=("Fury", "Fury"))
    payments = generate_rune_payments(pool, energy_cost=0, power_cost=1, power_domain="Order")
    assert payments == []


def test_generate_rune_payment_insufficient_total():
    pool = RunePool(available=("Order",))
    payments = generate_rune_payments(pool, energy_cost=1, power_cost=1, power_domain="Order")
    assert payments == []


def test_generate_rune_payment_no_power_cost():
    pool = RunePool(available=("Fury", "Order"))
    payments = generate_rune_payments(pool, energy_cost=2, power_cost=0, power_domain=None)
    assert len(payments) == 1
    assert payments[0].power_runes == ()


# --- PlayUnit ---


CHEAP_UNIT = CardDef(card_id="ogn-010-298", card_type="Unit", energy_cost=2,
                      power_cost=0, might=2, keywords=frozenset())

DOMAIN_UNIT = CardDef(card_id="ogn-218-298", card_type="Unit", energy_cost=2,
                       power_cost=1, power_domain="Order", might=3, keywords=frozenset())


def test_play_unit_to_base_legal_and_applies():
    state = make_state(hand=("ogn-010-298",), runes=("Fury", "Fury"))
    payment = generate_rune_payments(state.players[0].runes, 2, 0, None)[0]
    action = PlayUnit(card_id="ogn-010-298", target_zone="base", rune_payment=payment)
    assert is_legal_play_unit(state, action, CHEAP_UNIT)

    new_state = apply_play_unit(state, action, CHEAP_UNIT)
    assert "ogn-010-298" not in new_state.players[0].hand
    assert new_state.players[0].runes.available == ()
    new_units = new_state.players[0].base_units
    assert len(new_units) == 1
    unit = next(iter(new_units))
    assert unit.exhausted is True
    assert unit.might == 2


def test_play_unit_insufficient_runes_illegal():
    state = make_state(hand=("ogn-010-298",), runes=("Fury",))
    payments = generate_rune_payments(state.players[0].runes, 2, 0, None)
    assert payments == []  # not enough runes to even build a payment


def test_play_unit_to_uncontrolled_battlefield_illegal():
    # rule 355.7/355.8: can only play directly to Base or a battlefield you
    # already have units on — not an open or opponent-held one.
    state = make_state(hand=("ogn-010-298",), runes=("Fury", "Fury"), bf0_controller=None)
    payment = generate_rune_payments(state.players[0].runes, 2, 0, None)[0]
    action = PlayUnit(card_id="ogn-010-298", target_zone="left", rune_payment=payment)
    assert not is_legal_play_unit(state, action, CHEAP_UNIT)


def test_play_unit_to_a_battlefield_we_have_units_on_is_legal():
    state = make_state(hand=("ogn-010-298",), runes=("Fury", "Fury"),
                        bf0_units=frozenset({make_unit(instance_id=9)}), bf0_controller=0)
    payment = generate_rune_payments(state.players[0].runes, 2, 0, None)[0]
    action = PlayUnit(card_id="ogn-010-298", target_zone="left", rune_payment=payment)
    assert is_legal_play_unit(state, action, CHEAP_UNIT)
    new_state = apply_play_unit(state, action, CHEAP_UNIT)
    assert len(new_state.battlefields[0].units) == 2


def test_play_unit_needs_units_present_not_merely_control():
    """The rule is "a battlefield you have units on", which is NOT the same
    statement as "a battlefield you control" — they only coincide because
    every path that empties a battlefield also clears its controller. This
    pins the rule itself, so the check can't silently drift back to
    keying on control if some future effect ever grants control without
    presence."""
    state = make_state(hand=("ogn-010-298",), runes=("Fury", "Fury"),
                        bf0_units=frozenset(), bf0_controller=0)
    payment = generate_rune_payments(state.players[0].runes, 2, 0, None)[0]
    action = PlayUnit(card_id="ogn-010-298", target_zone="left", rune_payment=payment)
    assert not is_legal_play_unit(state, action, CHEAP_UNIT)


def test_play_unit_to_a_battlefield_holding_only_enemy_units_illegal():
    enemy = make_unit(instance_id=9, controller=1)
    state = make_state(hand=("ogn-010-298",), runes=("Fury", "Fury"),
                        bf0_units=frozenset({enemy}), bf0_controller=1)
    payment = generate_rune_payments(state.players[0].runes, 2, 0, None)[0]
    action = PlayUnit(card_id="ogn-010-298", target_zone="left", rune_payment=payment)
    assert not is_legal_play_unit(state, action, CHEAP_UNIT)


def test_play_unit_wrong_power_domain_illegal():
    state = make_state(hand=("ogn-218-298",), runes=("Fury", "Fury", "Fury"))
    # Only Fury runes available, but this card needs Order power.
    payments = generate_rune_payments(state.players[0].runes, 2, 1, "Order")
    assert payments == []


OPEN_DEPLOY_UNIT = CardDef(card_id="ogn-176-298", card_type="Unit", energy_cost=3,
                            power_cost=0, might=2, keywords=frozenset(),
                            can_play_to_open_battlefield=True)


def test_play_unit_to_open_battlefield_illegal_without_flag():
    state = make_state(hand=("ogn-010-298",), runes=("Fury", "Fury"), bf0_controller=None)
    payment = generate_rune_payments(state.players[0].runes, 2, 0, None)[0]
    action = PlayUnit(card_id="ogn-010-298", target_zone="left", rune_payment=payment)
    assert not is_legal_play_unit(state, action, CHEAP_UNIT)  # no can_play_to_open_battlefield


def test_play_unit_to_open_battlefield_legal_with_flag_and_establishes_control():
    state = make_state(hand=("ogn-176-298",), runes=("Fury", "Fury", "Fury"), bf0_controller=None)
    payment = generate_rune_payments(state.players[0].runes, 3, 0, None)[0]
    action = PlayUnit(card_id="ogn-176-298", target_zone="left", rune_payment=payment)
    assert is_legal_play_unit(state, action, OPEN_DEPLOY_UNIT)

    new_state = apply_play_unit(state, action, OPEN_DEPLOY_UNIT)
    assert new_state.battlefields[0].controller == 0


def test_play_unit_to_open_battlefield_illegal_if_occupied():
    # rule 170.11.c: "open" means unoccupied AND uncontrolled — a
    # battlefield with units present isn't "open" even if uncontrolled
    # doesn't apply here since a unit's presence implies its controller
    # controls it, but this guards the not-bf.units check directly.
    occupant = make_unit(card_id="occupant", instance_id=99, controller=1)
    state = make_state(hand=("ogn-176-298",), runes=("Fury", "Fury", "Fury"),
                        bf0_units=frozenset({occupant}), bf0_controller=None)
    payment = generate_rune_payments(state.players[0].runes, 3, 0, None)[0]
    action = PlayUnit(card_id="ogn-176-298", target_zone="left", rune_payment=payment)
    assert not is_legal_play_unit(state, action, OPEN_DEPLOY_UNIT)


# --- MoveUnit ---


def test_move_base_to_battlefield_legal_and_exhausts():
    unit = make_unit(instance_id=1, exhausted=False)
    state = make_state(base_units=frozenset({unit}))
    action = MoveUnit(instance_id=1, from_zone="base", to_zone="left")
    assert is_legal_move_unit(state, action)

    new_state = apply_move_unit(state, action)
    assert new_state.players[0].base_units == frozenset()
    moved = next(iter(new_state.battlefields[0].units))
    assert moved.exhausted is True  # rule 145.1


def test_move_exhausted_unit_illegal():
    unit = make_unit(instance_id=1, exhausted=True)
    state = make_state(base_units=frozenset({unit}))
    action = MoveUnit(instance_id=1, from_zone="base", to_zone="left")
    assert not is_legal_move_unit(state, action)


def test_move_battlefield_to_battlefield_requires_ganking():
    unit = make_unit(instance_id=1, exhausted=False, keywords=frozenset())
    state = make_state(bf0_units=frozenset({unit}), bf0_controller=0)
    action = MoveUnit(instance_id=1, from_zone="left", to_zone="right")
    assert not is_legal_move_unit(state, action)

    ganking_unit = make_unit(instance_id=1, exhausted=False, keywords=frozenset({"Ganking"}))
    state2 = make_state(bf0_units=frozenset({ganking_unit}), bf0_controller=0)
    assert is_legal_move_unit(state2, action)


def test_move_battlefield_to_base_always_legal():
    unit = make_unit(instance_id=1, exhausted=False)
    state = make_state(bf0_units=frozenset({unit}), bf0_controller=0)
    action = MoveUnit(instance_id=1, from_zone="left", to_zone="base")
    assert is_legal_move_unit(state, action)


def test_move_to_open_battlefield_establishes_control():
    unit = make_unit(instance_id=1, exhausted=False)
    state = make_state(base_units=frozenset({unit}))
    action = MoveUnit(instance_id=1, from_zone="base", to_zone="left")
    new_state = apply_move_unit(state, action)
    assert new_state.battlefields[0].controller == 0


def test_move_away_leaving_battlefield_empty_clears_control():
    unit = make_unit(instance_id=1, exhausted=False)
    state = make_state(bf0_units=frozenset({unit}), bf0_controller=0)
    action = MoveUnit(instance_id=1, from_zone="left", to_zone="base")
    new_state = apply_move_unit(state, action)
    assert new_state.battlefields[0].controller is None


def test_move_away_leaving_teammate_unit_keeps_control():
    mover = make_unit(instance_id=1, exhausted=False)
    stayer = make_unit(instance_id=2, exhausted=True)  # same controller, stays behind
    state = make_state(bf0_units=frozenset({mover, stayer}), bf0_controller=0)
    action = MoveUnit(instance_id=1, from_zone="left", to_zone="base")
    new_state = apply_move_unit(state, action)
    assert new_state.battlefields[0].controller == 0


def test_move_onto_occupied_battlefield_not_implemented():
    mover = make_unit(instance_id=1, exhausted=False)
    blocker = make_unit(card_id="blocker", instance_id=2, controller=1)
    state = make_state(base_units=frozenset({mover}), bf0_units=frozenset({blocker}))
    action = MoveUnit(instance_id=1, from_zone="base", to_zone="left")
    with pytest.raises(NotImplementedError):
        apply_move_unit(state, action)


# --- legal_board_actions orchestration ---


def test_legal_actions_includes_play_and_move():
    unit = make_unit(instance_id=1, exhausted=False)
    state = make_state(hand=("ogn-010-298",), runes=("Fury", "Fury"),
                        base_units=frozenset({unit}))
    cards = {"ogn-010-298": CHEAP_UNIT}
    actions = legal_board_actions(state, cards)
    assert any(isinstance(a, PlayUnit) for a in actions)
    assert any(isinstance(a, MoveUnit) for a in actions)


def test_legal_actions_excludes_unaffordable_cards():
    state = make_state(hand=("ogn-218-298",), runes=("Fury",))  # can't afford
    cards = {"ogn-218-298": DOMAIN_UNIT}
    actions = legal_board_actions(state, cards)
    assert not any(isinstance(a, PlayUnit) for a in actions)
