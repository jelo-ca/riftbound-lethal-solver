"""[Deflect] — "Opponents must pay ⟨rainbow rune⟩ to choose me with a
spell or ability." "Deflect 2" charges two.

The rainbow rune is Recycled (rule 164.2.b's Power half) but accepts any
domain, so it can't ride in RunePayment.power_runes, which are
domain-checked. Hence the separate rainbow_runes channel.

Since the opponent never acts in these puzzles, the tax only ever bites
in one direction: us paying extra to touch an enemy unit.
"""

from solver.engine.abilities import (
    CAITLYN_PATROLLING,
    CHARM,
    ZAUNITE_BOUNCER,
    is_legal_activate_ability,
    is_legal_play_spell,
    is_legal_unit_play_trigger,
)
from solver.engine.actions import (
    ActivateAbility,
    PlaySpell,
    PlayUnit,
    RunePayment,
    consume_runes,
    generate_rune_payments,
)
from solver.engine.card_pool import CARD_POOL, POUTY_PORO
from solver.engine.cards import CardDef
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from solver.engine.traits import deflect_tax
from solver.search import legal_actions

CHARM_CARD = CARD_POOL[CHARM]  # 1 Energy, 1 Calm Power
# Free stand-in so a test pool only has to cover the tax, not a 4/2 body
# (same trick test_blitzcrank.py uses).
FREE_BOUNCER = CardDef(card_id=ZAUNITE_BOUNCER, card_type="Unit", energy_cost=0,
                        power_cost=0, might=2, keywords=frozenset())


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


# --- enforcement: spells (Charm) ---


def _charm_state(enemy_keywords, runes, hand=(CHARM,)):
    """An enemy unit alone at "left", an empty "right" to shove it onto —
    so Charm's redirect triggers no combat and the only variable is the
    tax."""
    enemy = UnitInstance(card_id=POUTY_PORO, instance_id=20, controller=1, might=2,
                          keywords=enemy_keywords, exhausted=False, damage=0, is_token=False)
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=hand, runes=RunePool(available=runes), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 1, frozenset({enemy}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def _charm_actions(state):
    return [a for a in legal_actions(state, {CHARM: CHARM_CARD})
            if isinstance(a, PlaySpell) and a.card_id == CHARM]


def test_charm_on_a_deflect_enemy_is_generated_with_the_tax_paid():
    state = _charm_state(frozenset({"Deflect"}), ("Calm", "Fury", "Fury"))
    actions = _charm_actions(state)
    assert actions
    assert all(len(a.rune_payment.rainbow_runes) == 1 for a in actions)


def test_charm_on_a_plain_enemy_pays_no_tax():
    state = _charm_state(frozenset(), ("Calm", "Fury", "Fury"))
    actions = _charm_actions(state)
    assert actions
    assert all(a.rune_payment.rainbow_runes == () for a in actions)


def test_paying_the_printed_cost_alone_is_illegal_against_a_deflect_target():
    """The whole point: the obvious line stops being affordable."""
    state = _charm_state(frozenset({"Deflect"}), ("Calm", "Fury", "Fury"))
    untaxed = PlaySpell(card_id=CHARM, params=(20, "right"),
                         rune_payment=RunePayment(energy_runes=("Fury",), power_runes=("Calm",)))
    assert not is_legal_play_spell(state, untaxed, CHARM_CARD)

    taxed = PlaySpell(card_id=CHARM, params=(20, "right"),
                       rune_payment=RunePayment(energy_runes=("Fury",), power_runes=("Calm",),
                                                 rainbow_runes=("Fury",)))
    assert is_legal_play_spell(state, taxed, CHARM_CARD)


def test_deflect_can_price_a_spell_out_entirely():
    """Exactly the printed cost in the pool — enough untaxed, one rune
    short once Deflect charges."""
    assert _charm_actions(_charm_state(frozenset(), ("Calm", "Fury")))
    assert _charm_actions(_charm_state(frozenset({"Deflect"}), ("Calm", "Fury"))) == []


def test_deflect_2_charges_two_runes():
    state = _charm_state(frozenset({"Deflect 2"}), ("Calm", "Fury", "Fury", "Fury"))
    actions = _charm_actions(state)
    assert actions
    assert all(len(a.rune_payment.rainbow_runes) == 2 for a in actions)


# --- enforcement: a unit ability that prints no rune cost (Caitlyn) ---


def _caitlyn_state(enemy_keywords, runes):
    caitlyn = UnitInstance(card_id=CAITLYN_PATROLLING, instance_id=10, controller=0, might=3,
                            keywords=frozenset(), exhausted=False, damage=0, is_token=False)
    enemy = UnitInstance(card_id=POUTY_PORO, instance_id=20, controller=1, might=2,
                          keywords=enemy_keywords, exhausted=False, damage=0, is_token=False)
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=runes), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, frozenset({caitlyn}), None),
            BattlefieldState("right", 1, frozenset({enemy}), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def _shoot(payment=None):
    return ActivateAbility(source_id=10, ability_id=CAITLYN_PATROLLING, params=(20,),
                            rune_payment=payment)


def test_a_free_ability_still_owes_the_tax():
    """Caitlyn prints no rune cost — exhaust only — but the tax attaches
    to CHOOSING a unit, so her usual free shot isn't free here."""
    state = _caitlyn_state(frozenset({"Deflect"}), ("Fury",))
    assert not is_legal_activate_ability(state, _shoot(None))
    paid = RunePayment(energy_runes=(), power_runes=(), rainbow_runes=("Fury",))
    assert is_legal_activate_ability(state, _shoot(paid))


def test_a_free_ability_stays_free_against_a_plain_target():
    state = _caitlyn_state(frozenset(), ("Fury",))
    assert is_legal_activate_ability(state, _shoot(None))


def test_deflect_can_switch_off_a_free_ability_when_the_pool_is_empty():
    """With no runes, the Deflect enemy drops out of her target list —
    while she keeps the untaxed targets (her own text doesn't restrict to
    enemies, so she can still point at friendlies)."""
    state = _caitlyn_state(frozenset({"Deflect"}), ())
    assert not is_legal_activate_ability(state, _shoot(None))
    abilities_generated = [a for a in legal_actions(state, {}) if isinstance(a, ActivateAbility)]
    assert not [a for a in abilities_generated if a.params == (20,)]
    assert [a for a in abilities_generated if a.params == (10,)]  # friendly target still fine


def test_caitlyns_tax_is_actually_spent():
    from solver.engine.abilities import apply_ability
    state = _caitlyn_state(frozenset({"Deflect"}), ("Fury", "Calm"))
    paid = RunePayment(energy_runes=(), power_runes=(), rainbow_runes=("Fury",))
    result = apply_ability(state, _shoot(paid))
    assert sorted(result.players[0].runes.available) == ["Calm"]


# --- enforcement: a "when you play me" trigger, which has no cost channel of its own ---


def _bouncer_state(enemy_keywords, runes):
    enemy = UnitInstance(card_id=POUTY_PORO, instance_id=20, controller=1, might=2,
                          keywords=enemy_keywords, exhausted=False, damage=0, is_token=False)
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(ZAUNITE_BOUNCER,),
                        runes=RunePool(available=runes), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 1, frozenset({enemy}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def _bounce(trigger_payment=None):
    return PlayUnit(card_id=ZAUNITE_BOUNCER, target_zone="base",
                     rune_payment=RunePayment(energy_runes=(), power_runes=()),
                     trigger_params=(20,), trigger_payment=trigger_payment)


def test_a_play_trigger_owes_the_tax_through_its_own_payment_channel():
    state = _bouncer_state(frozenset({"Deflect"}), ("Fury",))
    assert not is_legal_unit_play_trigger(state, _bounce(None), FREE_BOUNCER)
    paid = RunePayment(energy_runes=(), power_runes=(), rainbow_runes=("Fury",))
    assert is_legal_unit_play_trigger(state, _bounce(paid), FREE_BOUNCER)


def test_a_play_trigger_on_a_plain_target_owes_nothing():
    state = _bouncer_state(frozenset(), ("Fury",))
    assert is_legal_unit_play_trigger(state, _bounce(None), FREE_BOUNCER)


def test_generation_attaches_the_trigger_payment():
    state = _bouncer_state(frozenset({"Deflect"}), ("Fury",))
    triggered = [a for a in legal_actions(state, {ZAUNITE_BOUNCER: FREE_BOUNCER})
                 if isinstance(a, PlayUnit) and a.trigger_params]
    assert triggered
    assert all(len(a.trigger_payment.rainbow_runes) == 1 for a in triggered)


def test_an_unaffordable_trigger_tax_removes_that_target():
    state = _bouncer_state(frozenset({"Deflect"}), ())
    triggered = [a for a in legal_actions(state, {ZAUNITE_BOUNCER: FREE_BOUNCER})
                 if isinstance(a, PlayUnit) and a.trigger_params]
    assert triggered == []


def test_the_trigger_tax_is_actually_spent():
    from solver.engine.abilities import resolve_unit_play_trigger_outcomes
    state = _bouncer_state(frozenset({"Deflect"}), ("Fury", "Calm"))
    paid = RunePayment(energy_runes=(), power_runes=(), rainbow_runes=("Fury",))
    result = resolve_unit_play_trigger_outcomes(state, _bounce(paid), FREE_BOUNCER)[0]
    assert sorted(result.players[0].runes.available) == ["Calm"]
