"""Shakedown, Meditation, Convergent Mutation, and Cannon Barrage — a small
[Reaction]-speed sweep. See engine/coverage.py for the per-card reasoning
(especially Shakedown's "unless" clause and Meditation's actually-useful
cost) and abilities.py's "More [Reaction] spells" section for the code.
"""

import dataclasses

from solver.engine import abilities, combat
from solver.engine.abilities import (
    CANNON_BARRAGE,
    CONVERGENT_MUTATION,
    MEDITATION,
    SHAKEDOWN,
)
from solver.engine.gear import ARENA_BAR
from solver.engine.actions import ActivateAbility, PlaySpell, RunePayment
from solver.engine.card_pool import card_def
from solver.engine.state import (
    BattlefieldState,
    GameState,
    GearInstance,
    PlayerState,
    RunePool,
    ShowdownState,
    UnitInstance,
)
from solver.search import legal_actions


def unit(instance_id, controller=0, might=3, keywords=frozenset(), exhausted=False, card_id="u"):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=keywords, exhausted=exhausted, damage=0,
                         is_token=False)


def state_with(left=frozenset(), base=frozenset(), hand=(), runes=("Fury",) * 12,
               gear_pieces=frozenset(), showdown=None):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base, hand=hand, runes=RunePool(available=runes), score=0,
                        gear=gear_pieces),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, left, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
        showdown=showdown,
    )


def cast(card_id, params, state):
    card = card_def(card_id)
    payment = RunePayment(energy_runes=("Fury",) * card.energy_cost,
                          power_runes=(card.power_domain,) * card.power_cost)
    action = PlaySpell(card_id=card_id, params=params, rune_payment=payment)
    return abilities.resolve_spell_outcomes(state, action, card)[0]


# --- Shakedown -------------------------------------------------------------


def test_shakedown_always_deals_six_regardless_of_the_never_made_choice():
    """The "unless its controller has you draw 2" branch belongs to the
    opponent, who never acts — so it's never taken, and the 6 always
    lands."""
    enemy = unit(1, controller=1, might=9)
    state = state_with(left=frozenset({enemy}), hand=(SHAKEDOWN,), runes=("Fury",) * 3)
    out = cast(SHAKEDOWN, (1,), state)
    assert next(u for u in out.battlefields[0].units if u.instance_id == 1).damage == 6


def test_shakedown_cannot_target_a_friendly_unit():
    ours = unit(1, controller=0)
    state = state_with(left=frozenset({ours}), hand=(SHAKEDOWN,), runes=("Fury",) * 3)
    card = card_def(SHAKEDOWN)
    payment = RunePayment(energy_runes=("Fury", "Fury"), power_runes=("Fury",))
    action = PlaySpell(card_id=SHAKEDOWN, params=(1,), rune_payment=payment)
    assert not abilities.is_legal_play_spell(state, action, card)


def test_shakedown_reachable_through_legal_actions():
    enemy = unit(1, controller=1, might=9)
    state = state_with(left=frozenset({enemy}), hand=(SHAKEDOWN,), runes=("Fury",) * 3)
    plays = [a for a in legal_actions(state, {SHAKEDOWN: card_def(SHAKEDOWN)})
             if isinstance(a, PlaySpell) and a.card_id == SHAKEDOWN]
    assert plays, "Shakedown is not being generated"


# --- Meditation --------------------------------------------------------


def test_meditation_can_be_declined():
    ours = unit(1, controller=0, exhausted=False)
    state = state_with(base=frozenset({ours}), hand=(MEDITATION,), runes=("Fury", "Fury"))
    out = cast(MEDITATION, (), state)
    assert next(iter(out.players[0].base_units)).exhausted is False


def test_meditation_can_exhaust_a_friendly_ready_unit():
    ours = unit(1, controller=0, exhausted=False)
    state = state_with(base=frozenset({ours}), hand=(MEDITATION,), runes=("Fury", "Fury"))
    out = cast(MEDITATION, (1,), state)
    assert next(iter(out.players[0].base_units)).exhausted is True


def test_meditation_cannot_exhaust_an_already_exhausted_unit():
    """Paying an Exhaust cost needs something ready to Exhaust, the same
    convention as every other Exhaust cost in the pool."""
    ours = unit(1, controller=0, exhausted=True)
    state = state_with(base=frozenset({ours}), hand=(MEDITATION,), runes=("Fury", "Fury"))
    card = card_def(MEDITATION)
    payment = RunePayment(energy_runes=("Fury", "Fury"), power_runes=())
    action = PlaySpell(card_id=MEDITATION, params=(1,), rune_payment=payment)
    assert not abilities.is_legal_play_spell(state, action, card)


def test_meditation_cannot_exhaust_an_enemy_unit():
    enemy = unit(1, controller=1, exhausted=False)
    state = state_with(left=frozenset({enemy}), hand=(MEDITATION,), runes=("Fury", "Fury"))
    card = card_def(MEDITATION)
    payment = RunePayment(energy_runes=("Fury", "Fury"), power_runes=())
    action = PlaySpell(card_id=MEDITATION, params=(1,), rune_payment=payment)
    assert not abilities.is_legal_play_spell(state, action, card)


def test_meditation_exhausting_a_unit_makes_it_a_legal_arena_bar_target():
    """The interaction the card is actually implemented for: Arena Bar's
    ability requires an EXHAUSTED friendly unit, and a unit that's ready
    at position setup has no other free way to become one."""
    ours = unit(1, controller=0, exhausted=False)
    state = state_with(base=frozenset({ours}), hand=(MEDITATION,), runes=("Fury", "Fury"),
                        gear_pieces=frozenset({GearInstance(card_id=ARENA_BAR, instance_id=50,
                                                             exhausted=False)}))
    from solver.engine import gear
    arena_bar_action = ActivateAbility(source_id=50, ability_id=ARENA_BAR, params=(1,),
                                       rune_payment=None)
    assert not gear.is_legal_gear_ability(state, arena_bar_action)  # not exhausted yet

    after_meditation = cast(MEDITATION, (1,), state)
    assert gear.is_legal_gear_ability(after_meditation, arena_bar_action)
    result = gear.apply_gear_ability(after_meditation, arena_bar_action)
    assert next(iter(result.players[0].base_units)).buffed is True


def test_meditation_reachable_through_legal_actions():
    ours = unit(1, controller=0, exhausted=False)
    state = state_with(base=frozenset({ours}), hand=(MEDITATION,), runes=("Fury", "Fury"))
    plays = [a for a in legal_actions(state, {MEDITATION: card_def(MEDITATION)})
             if isinstance(a, PlaySpell) and a.card_id == MEDITATION]
    assert any(p.params == () for p in plays)
    assert any(p.params == (1,) for p in plays)


# --- Convergent Mutation ------------------------------------------------


def test_convergent_mutation_raises_the_lower_unit():
    small = unit(1, controller=0, might=2)
    big = unit(2, controller=0, might=6)
    state = state_with(base=frozenset({small, big}), hand=(CONVERGENT_MUTATION,),
                        runes=("Fury", "Fury", "Mind"))
    out = cast(CONVERGENT_MUTATION, (1, 2), state)
    assert {u.instance_id: u.might for u in out.players[0].base_units} == {1: 6, 2: 6}


def test_convergent_mutation_does_nothing_when_the_reference_is_not_higher():
    """"Increase" — no effect when the reference unit isn't actually
    ahead, per the printed word."""
    even = unit(1, controller=0, might=4)
    other = unit(2, controller=0, might=4)
    state = state_with(base=frozenset({even, other}), hand=(CONVERGENT_MUTATION,),
                        runes=("Fury", "Fury", "Mind"))
    out = cast(CONVERGENT_MUTATION, (1, 2), state)
    assert next(u for u in out.players[0].base_units if u.instance_id == 1).might == 4


def test_convergent_mutation_needs_a_second_distinct_friendly_unit():
    lone = unit(1, controller=0, might=2)
    state = state_with(base=frozenset({lone}), hand=(CONVERGENT_MUTATION,),
                        runes=("Fury", "Fury", "Mind"))
    card = card_def(CONVERGENT_MUTATION)
    payment = RunePayment(energy_runes=("Fury", "Fury"), power_runes=("Mind",))
    action = PlaySpell(card_id=CONVERGENT_MUTATION, params=(1, 1), rune_payment=payment)
    assert not abilities.is_legal_play_spell(state, action, card)


def test_convergent_mutation_cannot_reference_an_enemy_unit():
    ours = unit(1, controller=0, might=2)
    enemy = unit(2, controller=1, might=9)
    state = state_with(left=frozenset({enemy}), base=frozenset({ours}),
                        hand=(CONVERGENT_MUTATION,), runes=("Fury", "Fury", "Mind"))
    card = card_def(CONVERGENT_MUTATION)
    payment = RunePayment(energy_runes=("Fury", "Fury"), power_runes=("Mind",))
    action = PlaySpell(card_id=CONVERGENT_MUTATION, params=(1, 2), rune_payment=payment)
    assert not abilities.is_legal_play_spell(state, action, card)


def test_convergent_mutation_reachable_through_legal_actions():
    small = unit(1, controller=0, might=2)
    big = unit(2, controller=0, might=6)
    state = state_with(base=frozenset({small, big}), hand=(CONVERGENT_MUTATION,),
                        runes=("Fury", "Fury", "Mind"))
    plays = [a for a in legal_actions(state, {CONVERGENT_MUTATION: card_def(CONVERGENT_MUTATION)})
             if isinstance(a, PlaySpell) and a.card_id == CONVERGENT_MUTATION]
    assert any(p.params == (1, 2) for p in plays)


# --- Cannon Barrage -------------------------------------------------------


def _open_showdown_state():
    ours = unit(1, controller=0)
    enemy = unit(2, controller=1, might=9)
    state = state_with(left=frozenset({enemy}), base=frozenset({ours}),
                        hand=(CANNON_BARRAGE,), runes=("Fury", "Fury", "Body"))
    mover = next(iter(state.players[0].base_units))
    return combat.open_showdown(state, mover, "base", "left")


def test_cannon_barrage_is_illegal_outside_a_showdown():
    enemy = unit(2, controller=1, might=9)
    state = state_with(left=frozenset({enemy}), hand=(CANNON_BARRAGE,),
                        runes=("Fury", "Fury", "Body"))
    card = card_def(CANNON_BARRAGE)
    payment = RunePayment(energy_runes=("Fury", "Fury"), power_runes=("Body",))
    action = PlaySpell(card_id=CANNON_BARRAGE, params=(), rune_payment=payment)
    assert not abilities.is_legal_play_spell(state, action, card)


def test_cannon_barrage_hits_only_the_enemy_side_of_the_open_showdown():
    state = _open_showdown_state()
    out = cast(CANNON_BARRAGE, (), state)
    left = out.battlefields[0]
    by_id = {u.instance_id: u for u in left.units}
    assert by_id[2].damage == 2  # the enemy defender, in combat
    assert by_id[1].damage == 0  # our own attacker, untouched


def test_cannon_barrage_leaves_units_elsewhere_untouched():
    """"In combat" is scoped to the open showdown's battlefield — an
    enemy unit sitting somewhere else entirely isn't in this fight."""
    state = _open_showdown_state()
    bystander = unit(3, controller=1, might=5)
    right = dataclasses.replace(state.battlefields[1], controller=1, units=frozenset({bystander}))
    state = dataclasses.replace(state, battlefields=(state.battlefields[0], right))
    out = cast(CANNON_BARRAGE, (), state)
    right = next(bf for bf in out.battlefields if bf.battlefield_id == "right")
    assert next(iter(right.units)).damage == 0


def test_cannon_barrage_reachable_through_legal_actions_inside_a_showdown():
    state = _open_showdown_state()
    plays = [a for a in legal_actions(state, {CANNON_BARRAGE: card_def(CANNON_BARRAGE)})
             if isinstance(a, PlaySpell) and a.card_id == CANNON_BARRAGE]
    assert plays, "Cannon Barrage is not being generated inside an open showdown"
