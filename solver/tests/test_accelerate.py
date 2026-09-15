"""[Accelerate] — "You may pay 1 Energy + one rune of my domain as an
additional cost to have me enter ready."

Why this keyword matters more than its card count suggests: units enter
exhausted (rule 143.4.a), which is exactly why generate.py excludes plain
bodies from the hand pool — a freshly played vanilla can't move or fight,
so playing it is a dead action in a single-turn puzzle. Accelerate is the
one printed way out of that, which makes it the first keyword here that
adds a genuinely new shape of line rather than just Might arithmetic.
"""

from solver.engine.actions import (
    PlayUnit,
    RunePayment,
    apply_play_unit,
    generate_rune_payments,
    has_accelerate,
    is_legal_play_unit,
    legal_board_actions,
    play_unit_cost,
)
from solver.engine.card_pool import CARD_POOL, LEGION_REARGUARD, STALWART_PORO
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool

REARGUARD = CARD_POOL[LEGION_REARGUARD]  # 2 Energy, no Power, [Accelerate] (Fury)


def make_state(hand=(), runes=()):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=hand, runes=RunePool(available=runes), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def _payment(state, card, accelerated):
    energy_cost, power_cost, power_domain = play_unit_cost(card, accelerated)
    return generate_rune_payments(state.players[0].runes, energy_cost, power_cost, power_domain)[0]


def test_accelerated_cost_is_one_more_energy_plus_a_rune_of_the_cards_domain():
    assert has_accelerate(REARGUARD)
    assert play_unit_cost(REARGUARD, accelerated=False) == (2, 0, None)
    # Legion Rearguard has no Power cost of its own, so the Fury requirement
    # can only come from accelerate_domain.
    assert play_unit_cost(REARGUARD, accelerated=True) == (3, 1, "Fury")


def test_accelerated_play_enters_ready_and_plain_play_does_not():
    """The whole point of the keyword — and the half a puzzle actually
    cares about, since an exhausted unit can neither move nor fight."""
    state = make_state(hand=(LEGION_REARGUARD,), runes=("Fury", "Fury", "Fury", "Fury"))

    plain = PlayUnit(card_id=LEGION_REARGUARD, target_zone="base",
                      rune_payment=_payment(state, REARGUARD, False))
    assert is_legal_play_unit(state, plain, REARGUARD)
    assert next(iter(apply_play_unit(state, plain, REARGUARD).players[0].base_units)).exhausted is True

    fast = PlayUnit(card_id=LEGION_REARGUARD, target_zone="base",
                     rune_payment=_payment(state, REARGUARD, True), accelerated=True)
    assert is_legal_play_unit(state, fast, REARGUARD)
    assert next(iter(apply_play_unit(state, fast, REARGUARD).players[0].base_units)).exhausted is False


def test_accelerated_play_is_illegal_without_the_extra_runes():
    """Exactly the printed cost in the pool: enough for the plain play,
    one rune short of the accelerated one."""
    state = make_state(hand=(LEGION_REARGUARD,), runes=("Fury", "Fury"))
    assert generate_rune_payments(state.players[0].runes, 3, 1, "Fury") == []
    underpaid = PlayUnit(card_id=LEGION_REARGUARD, target_zone="base",
                          rune_payment=RunePayment(energy_runes=("Fury", "Fury"), power_runes=()),
                          accelerated=True)
    assert not is_legal_play_unit(state, underpaid, REARGUARD)


def test_accelerated_play_needs_the_right_domain_rune():
    """3 Energy available but no Fury to Recycle for the Power half."""
    state = make_state(hand=(LEGION_REARGUARD,), runes=("Order", "Order", "Order", "Order"))
    assert generate_rune_payments(state.players[0].runes, 3, 1, "Fury") == []


def test_a_card_without_accelerate_cannot_be_played_accelerated():
    poro = CARD_POOL[STALWART_PORO]
    assert not has_accelerate(poro)
    state = make_state(hand=(STALWART_PORO,), runes=("Fury", "Fury", "Fury", "Fury"))
    action = PlayUnit(card_id=STALWART_PORO, target_zone="base",
                       rune_payment=RunePayment(energy_runes=("Fury",) * 3, power_runes=("Fury",)),
                       accelerated=True)
    assert not is_legal_play_unit(state, action, poro)


def test_both_cost_modes_are_generated_as_separate_legal_actions():
    """Accelerate is a choice, not an upgrade: the runes it eats may be
    needed elsewhere in the turn, so both forms have to stay on the table
    for the search to weigh."""
    state = make_state(hand=(LEGION_REARGUARD,), runes=("Fury", "Fury", "Fury", "Fury"))
    cards = {LEGION_REARGUARD: REARGUARD}
    plays = [a for a in legal_board_actions(state, cards)
             if isinstance(a, PlayUnit) and a.target_zone == "base"]
    assert any(a.accelerated for a in plays)
    assert any(not a.accelerated for a in plays)


def test_only_the_plain_form_is_generated_when_the_extra_cost_is_unaffordable():
    state = make_state(hand=(LEGION_REARGUARD,), runes=("Fury", "Fury"))
    cards = {LEGION_REARGUARD: REARGUARD}
    plays = [a for a in legal_board_actions(state, cards)
             if isinstance(a, PlayUnit) and a.target_zone == "base"]
    assert plays
    assert not any(a.accelerated for a in plays)
