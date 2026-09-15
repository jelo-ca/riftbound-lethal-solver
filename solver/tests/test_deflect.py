"""[Deflect] — "Opponents must pay ⟨rainbow rune⟩ to choose me with a
spell or ability." "Deflect 2" charges two.

The rainbow rune is Recycled (rule 164.2.b's Power half) but accepts any
domain, so it can't ride in RunePayment.power_runes, which are
domain-checked. Hence the separate rainbow_runes channel.

Since the opponent never acts in these puzzles, the tax only ever bites
in one direction: us paying extra to touch an enemy unit.
"""

from solver.engine.actions import RunePayment, consume_runes, generate_rune_payments
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from solver.engine.traits import deflect_tax


def make_unit(instance_id, controller=1, keywords=frozenset(), might=2):
    return UnitInstance(card_id="u", instance_id=instance_id, controller=controller,
                         might=might, keywords=keywords, exhausted=False, damage=0, is_token=False)


def make_state(left_units=frozenset()):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, left_units, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


# --- deflect_tax ---


def test_no_deflect_means_no_tax():
    unit = make_unit(1)
    assert deflect_tax(make_state(frozenset({unit})), unit, "left", chooser=0) == 0


def test_bare_deflect_taxes_one_rune():
    unit = make_unit(1, keywords=frozenset({"Deflect"}))
    assert deflect_tax(make_state(frozenset({unit})), unit, "left", chooser=0) == 1


def test_numbered_deflect_taxes_that_many():
    unit = make_unit(1, keywords=frozenset({"Deflect 2"}))
    assert deflect_tax(make_state(frozenset({unit})), unit, "left", chooser=0) == 2


def test_targeting_your_own_unit_is_never_taxed():
    """"Opponents must pay" — a Deflect unit doesn't tax its own
    controller, so our spells on our own units stay free."""
    ours = make_unit(1, controller=0, keywords=frozenset({"Deflect 2"}))
    assert deflect_tax(make_state(frozenset({ours})), ours, "left", chooser=0) == 0


# --- the rainbow payment channel ---


def test_rainbow_runes_accept_any_domain():
    """Unlike power_runes, which must match one domain."""
    pool = RunePool(available=("Fury", "Order", "Calm"))
    payments = generate_rune_payments(pool, energy_cost=0, power_cost=0, power_domain=None,
                                       rainbow_cost=2)
    assert payments
    assert len(payments[0].rainbow_runes) == 2


def test_rainbow_tax_stacks_on_top_of_a_normal_cost():
    """A 1-Energy/1-Order spell aimed at a Deflect unit needs a third rune
    on top — which is the whole point of the keyword in a puzzle where
    runes are counted exactly."""
    pool = RunePool(available=("Order", "Fury", "Calm"))
    payments = generate_rune_payments(pool, energy_cost=1, power_cost=1, power_domain="Order",
                                       rainbow_cost=1)
    assert payments
    p = payments[0]
    assert p.power_runes == ("Order",)
    assert len(p.energy_runes) == 1
    assert len(p.rainbow_runes) == 1


def test_rainbow_tax_can_make_an_otherwise_affordable_cost_unpayable():
    pool = RunePool(available=("Order", "Fury"))
    assert generate_rune_payments(pool, 1, 1, "Order", rainbow_cost=0)  # fine untaxed
    assert generate_rune_payments(pool, 1, 1, "Order", rainbow_cost=1) == []  # one rune short


def test_consume_runes_spends_the_rainbow_runes_too():
    """Missing this would hand the tax back for free on the next action."""
    pool = RunePool(available=("Fury", "Order", "Calm"))
    payment = RunePayment(energy_runes=("Fury",), power_runes=(), rainbow_runes=("Order",))
    assert sorted(consume_runes(pool, payment).available) == ["Calm"]


def test_payments_without_a_tax_carry_no_rainbow_runes():
    """Default stays empty, so every existing call site is unaffected."""
    pool = RunePool(available=("Fury", "Fury"))
    payment = generate_rune_payments(pool, energy_cost=2, power_cost=0, power_domain=None)[0]
    assert payment.rainbow_runes == ()
