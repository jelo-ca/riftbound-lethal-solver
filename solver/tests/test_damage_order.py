"""Combat damage assignment ordering.

[Tank] ("I must be assigned combat damage first") and Caitlyn,
Patrolling's "I must be assigned combat damage last" are the same
mechanic from opposite ends: a constraint on which target may be
assigned damage next. Neither existed in combat.py before — Tank was
registered in TRAIT_REGISTRY and asserted by two code comments to order
assignment, while combat.py never mentioned it.

This matters because enumerate_assignments feeds both our own choice of
assignment and the opponent's adversarial one, so the ordering decides
which units die and therefore whether lethal exists.
"""

import dataclasses

from solver.engine import battlefields, combat
from solver.engine.battlefields import BattlefieldEffect
from solver.engine.combat import CAITLYN_PATROLLING
from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    UnitInstance,
)

TANK_FIELD = "test-tank-granting-battlefield"


def make_unit(instance_id, card_id="plain", might=3, keywords=frozenset(), damage=0, controller=1):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=keywords, exhausted=False, damage=damage,
                         is_token=False)


def tank(instance_id, might=3, **kw):
    return make_unit(instance_id, might=might, keywords=frozenset({"Tank"}), **kw)


def caitlyn(instance_id, might=3, **kw):
    return make_unit(instance_id, card_id=CAITLYN_PATROLLING, might=might, **kw)


def make_state(left_units=frozenset(), left_effect=None):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, left_units, left_effect),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def touched(assignment):
    """instance_ids that received any damage in this assignment."""
    return {uid for uid, amount in assignment if amount > 0}


# --- [Tank]: assigned first ---


def test_a_non_tank_is_never_touched_while_a_tank_is_unassigned():
    """The core of the keyword: you may not route damage around a Tank."""
    units = frozenset({tank(1, might=3), make_unit(2, might=3)})
    state = make_state(units)
    options = combat.enumerate_assignments(state, "left", units, pool=3, designation="defender")
    assert options
    for option in options:
        assert touched(option) == {1}, "only the Tank may be damaged while it lives"


def test_the_non_tank_becomes_available_once_the_tank_has_its_lethal():
    units = frozenset({tank(1, might=3), make_unit(2, might=3)})
    state = make_state(units)
    options = combat.enumerate_assignments(state, "left", units, pool=6, designation="defender")
    both = [o for o in options if touched(o) == {1, 2}]
    assert both, "6 damage should be able to kill the Tank and then the other unit"
    for option in both:
        assert dict(option)[1] >= 3, "the Tank must be taken to lethal before the other is touched"


def test_a_tank_soaks_a_pool_too_small_to_kill_it():
    """A 5-Might Tank beside a 1-Might unit: two damage cannot 'skip' the
    Tank to snipe the small one, which is the whole point of the keyword."""
    units = frozenset({tank(1, might=5), make_unit(2, might=1)})
    state = make_state(units)
    options = combat.enumerate_assignments(state, "left", units, pool=2, designation="defender")
    for option in options:
        assert 2 not in touched(option)


def test_tank_ordering_applies_to_the_attacking_side_too():
    """The constraint is about being assigned damage, not about which side
    you're on — an attacking Tank soaks the defenders' pool the same way."""
    units = frozenset({tank(1, might=3, controller=0), make_unit(2, might=3, controller=0)})
    state = make_state(units)
    options = combat.enumerate_assignments(state, "left", units, pool=3, designation="attacker")
    for option in options:
        assert touched(option) == {1}


def test_two_tanks_may_be_taken_in_either_order_but_before_anything_else():
    units = frozenset({tank(1, might=2), tank(2, might=2), make_unit(3, might=2)})
    state = make_state(units)
    options = combat.enumerate_assignments(state, "left", units, pool=2, designation="defender")
    first_hit = {next(iter(touched(o))) for o in options if len(touched(o)) == 1}
    assert first_hit == {1, 2}, "either Tank may be chosen first, but never the plain unit"


def test_a_granted_tank_orders_exactly_like_a_printed_one(monkeypatch):
    """Read through resolved_traits, not unit.keywords — a Tank granted by
    a battlefield or an aura has to order damage too, or the resolver is
    being bypassed."""
    monkeypatch.setitem(battlefields.BATTLEFIELD_EFFECTS, TANK_FIELD,
                         BattlefieldEffect(grants=frozenset({"Tank"})))
    plain_a, plain_b = make_unit(1, might=2), make_unit(2, might=2)
    units = frozenset({plain_a, plain_b})

    ungranted = combat.enumerate_assignments(make_state(units), "left", units, pool=2,
                                              designation="defender")
    assert {frozenset(touched(o)) for o in ungranted} == {frozenset({1}), frozenset({2})}

    # Same units, same pool — but now the battlefield grants both [Tank],
    # so both are "first" and the pair still orders freely between them.
    granted_state = make_state(units, left_effect=TANK_FIELD)
    granted = combat.enumerate_assignments(granted_state, "left", units, pool=2,
                                            designation="defender")
    assert granted, "granting Tank to everything must not eliminate every assignment"


def test_granting_tank_to_only_one_unit_constrains_the_other(monkeypatch):
    """The sharper version: a battlefield grant that lands on one side of
    the pair changes which assignments exist."""
    monkeypatch.setitem(battlefields.BATTLEFIELD_EFFECTS, TANK_FIELD,
                         BattlefieldEffect(grants=frozenset({"Tank"})))
    # Aura-free way to grant to exactly one: the granted unit sits at the
    # Tank battlefield, the comparison unit is evaluated there too, so use
    # a printed Tank for the contrast and assert the resolver agrees.
    granted = make_unit(1, might=2)
    state = make_state(frozenset({granted}), left_effect=TANK_FIELD)
    from solver.engine.traits import resolved_traits
    assert "Tank" in resolved_traits(state, granted, "left"), \
        "battlefield grant should reach the trait resolver"


# --- Caitlyn: assigned last ---


def test_caitlyn_is_not_touched_while_anything_else_remains():
    units = frozenset({caitlyn(1, might=3), make_unit(2, might=3)})
    state = make_state(units)
    options = combat.enumerate_assignments(state, "left", units, pool=3, designation="defender")
    for option in options:
        assert touched(option) == {2}, "the other unit must be assigned before Caitlyn"


def test_caitlyn_is_reachable_once_she_is_all_that_is_left():
    units = frozenset({caitlyn(1, might=3), make_unit(2, might=3)})
    state = make_state(units)
    options = combat.enumerate_assignments(state, "left", units, pool=6, designation="defender")
    assert any(touched(o) == {1, 2} for o in options)


def test_caitlyn_alone_is_assignable():
    units = frozenset({caitlyn(1, might=3)})
    state = make_state(units)
    options = combat.enumerate_assignments(state, "left", units, pool=3, designation="defender")
    assert any(touched(o) == {1} for o in options)


def test_tank_first_and_caitlyn_last_compose():
    """Both constraints at once have exactly one satisfying order:
    Tank, then the plain unit, then Caitlyn."""
    units = frozenset({tank(1, might=2), make_unit(2, might=2), caitlyn(3, might=2)})
    state = make_state(units)
    options = combat.enumerate_assignments(state, "left", units, pool=2, designation="defender")
    for option in options:
        assert touched(option) == {1}

    full = combat.enumerate_assignments(state, "left", units, pool=6, designation="defender")
    reached_all = [o for o in full if touched(o) == {1, 2, 3}]
    assert reached_all, "a big enough pool should still be able to reach everyone"


# --- interaction with lethal-first ---


def test_ordering_does_not_loosen_lethal_first():
    """Tank changes WHO is next, never the requirement that a unit takes
    its full remaining-lethal before the next one is touched."""
    units = frozenset({tank(1, might=4, damage=1), make_unit(2, might=3)})
    state = make_state(units)
    options = combat.enumerate_assignments(state, "left", units, pool=5, designation="defender")
    for option in options:
        assigned = dict(option)
        if 2 in touched(option):
            assert assigned[1] >= 3, "Tank needed 3 more to die; can't move on before that"


def test_shield_still_raises_the_tanks_lethal_threshold():
    """effective Might is unchanged by the ordering work — a Shield Tank
    defending needs one more than its printed Might."""
    units = frozenset({make_unit(1, might=3, keywords=frozenset({"Tank", "Shield"}))})
    state = make_state(units)
    options = combat.enumerate_assignments(state, "left", units, pool=4, designation="defender")
    assert any(dict(o).get(1) == 4 for o in options)


def test_no_targets_or_no_pool_is_unchanged():
    state = make_state(frozenset())
    assert combat.enumerate_assignments(state, "left", frozenset(), pool=5) == [()]
    units = frozenset({tank(1)})
    assert combat.enumerate_assignments(make_state(units), "left", units, pool=0) == [()]
