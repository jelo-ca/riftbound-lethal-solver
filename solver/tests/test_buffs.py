"""Buffs — binary, +1 Might, non-stacking.

Riftbound's buff is not a counter. A unit either carries a buff or it
doesn't, it is worth +1 Might, and buffing an already-buffed unit does
nothing. Karma, Channeler's own reminder text states the rule: "if it
doesn't have a buff, it gets a +1 Might buff."

It lives as state rather than being folded into `might` (where
unconditional Might changes normally go) because cards read it back:
"while I'm buffed, I have an additional +1 Might", "spend any number of
buffs".
"""

from solver.engine import combat
from solver.engine.abilities import apply_buff, spend_buff
from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    UnitInstance,
    canonical_key,
)


def make_unit(instance_id=1, controller=0, might=3, buffed=False):
    return UnitInstance(card_id="u", instance_id=instance_id, controller=controller,
                         might=might, keywords=frozenset(), exhausted=False, damage=0,
                         is_token=False, buffed=buffed)


def make_state(left_units=frozenset(), base_units=frozenset()):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=(), runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, left_units, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def unit_at(state, instance_id=1):
    return next(u for u in state.battlefields[0].units if u.instance_id == instance_id)


def test_a_buff_is_worth_one_might():
    state = make_state(frozenset({make_unit(might=3)}))
    assert combat.effective_might(state, unit_at(state), "left") == 3
    buffed = apply_buff(state, 1)
    assert combat.effective_might(buffed, unit_at(buffed), "left") == 4


def test_a_buff_applies_whether_attacking_or_defending():
    """Unlike Shield and Assault, a buff isn't gated on a combat role."""
    state = apply_buff(make_state(frozenset({make_unit(might=3)})), 1)
    unit = unit_at(state)
    assert combat.effective_might(state, unit, "left", "attacker") == 4
    assert combat.effective_might(state, unit, "left", "defender") == 4
    assert combat.effective_might(state, unit, "left", None) == 4


def test_buffs_do_not_stack():
    """The rule that makes this binary rather than a counter: a second
    buff on the same unit is not a second +1."""
    state = apply_buff(apply_buff(make_state(frozenset({make_unit(might=3)})), 1), 1)
    assert unit_at(state).buffed is True
    assert combat.effective_might(state, unit_at(state), "left") == 4


def test_buffing_an_already_buffed_unit_changes_nothing_at_all():
    """Not merely 'adds no Might' — the position must be identical, or the
    search would treat a no-op as progress."""
    state = apply_buff(make_state(frozenset({make_unit(might=3)})), 1)
    assert canonical_key(apply_buff(state, 1)) == canonical_key(state)


def test_a_buff_raises_the_lethal_threshold_too():
    """Might is one stat doing both jobs, so a buffed unit is also harder
    to kill."""
    state = apply_buff(make_state(frozenset({make_unit(might=3)})), 1)
    unit = unit_at(state)
    assert len(combat._apply_damage(state, "left", frozenset({unit}), ((1, 3),))) == 1
    assert combat._apply_damage(state, "left", frozenset({unit}), ((1, 4),)) == frozenset()


def test_spending_a_buff_removes_it():
    state = apply_buff(make_state(frozenset({make_unit(might=3)})), 1)
    spent = spend_buff(state, 1)
    assert unit_at(spent).buffed is False
    assert combat.effective_might(spent, unit_at(spent), "left") == 3


def test_spending_a_buff_that_isnt_there_is_a_no_op():
    state = make_state(frozenset({make_unit(might=3)}))
    assert canonical_key(spend_buff(state, 1)) == canonical_key(state)


def test_buff_is_part_of_the_canonical_key():
    """Otherwise the transposition table would treat a buffed board as the
    same position as an unbuffed one and prune a real line."""
    plain = make_state(frozenset({make_unit(might=3)}))
    assert canonical_key(apply_buff(plain, 1)) != canonical_key(plain)


def test_buffs_work_at_base_too():
    state = make_state(base_units=frozenset({make_unit(might=3)}))
    buffed = apply_buff(state, 1)
    unit = next(iter(buffed.players[0].base_units))
    assert unit.buffed is True
    assert combat.effective_might(buffed, unit, "base") == 4


# --- the cards that apply buffs on play ---

from solver.engine.abilities import (  # noqa: E402
    PEAK_GUARDIAN,
    PIT_ROOKIE,
    TRIFARIAN_GLORYSEEKER,
    resolve_unit_play_trigger_outcomes,
)
from solver.engine.actions import PlayUnit, RunePayment  # noqa: E402
from solver.engine.card_pool import card_def  # noqa: E402


def play(card_id, zone, trigger_params, runes=("Fury",) * 8, board=frozenset(), hand_extra=()):
    card = card_def(card_id)
    state = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(card_id,) + hand_extra,
                        runes=RunePool(available=runes), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0 if board else None, board, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    payment = RunePayment(energy_runes=("Fury",) * card.energy_cost,
                          power_runes=(card.power_domain,) * card.power_cost)
    action = PlayUnit(card_id=card_id, target_zone=zone, rune_payment=payment,
                       trigger_params=trigger_params)
    return state, card, action


def test_pit_rookie_buffs_another_friendly_unit():
    ally = make_unit(instance_id=5, might=2)
    state, card, action = play(PIT_ROOKIE, "left", (5,), board=frozenset({ally}))
    result = resolve_unit_play_trigger_outcomes(state, action, card)[0]
    assert unit_at(result, 5).buffed is True


def test_pit_rookie_cannot_buff_itself():
    """"Another friendly unit" — the Rookie is not a legal target for its
    own trigger."""
    from solver.engine.abilities import is_legal_unit_play_trigger

    ally = make_unit(instance_id=5, might=2)
    state, card, _ = play(PIT_ROOKIE, "left", (), board=frozenset({ally}))
    from solver.engine.actions import next_instance_id
    own_id = next_instance_id(state)
    _, _, self_target = play(PIT_ROOKIE, "left", (own_id,), board=frozenset({ally}))
    assert not is_legal_unit_play_trigger(state, self_target, card)


def test_gloryseeker_buffs_itself_only_with_legion_active():
    """[Legion] gates the whole effect, so playing it first in a turn
    leaves it unbuffed."""
    state, card, action = play(TRIFARIAN_GLORYSEEKER, "base", ("buff",))
    first_card = resolve_unit_play_trigger_outcomes(state, action, card)[0]
    assert all(not u.buffed for u in first_card.players[0].base_units)

    import dataclasses as dc
    later = dc.replace(state, cards_played_this_turn=1)
    result = resolve_unit_play_trigger_outcomes(later, action, card)[0]
    assert any(u.buffed for u in result.players[0].base_units)


def test_peak_guardian_buffs_itself_and_its_neighbours():
    ally = make_unit(instance_id=5, might=2)
    enemy = make_unit(instance_id=6, controller=1, might=2)
    state, card, action = play(PEAK_GUARDIAN, "left", ("buff",),
                                board=frozenset({ally, enemy}))
    result = resolve_unit_play_trigger_outcomes(state, action, card)[0]
    assert unit_at(result, 5).buffed is True   # friendly neighbour
    assert unit_at(result, 6).buffed is False  # "friendly" excludes the enemy


def test_peak_guardian_played_to_base_buffs_only_itself():
    """"Then, IF I am at a battlefield" — played to Base, the second half
    simply doesn't happen."""
    ally = make_unit(instance_id=5, might=2)
    state, card, action = play(PEAK_GUARDIAN, "base", ("buff",), board=frozenset({ally}))
    result = resolve_unit_play_trigger_outcomes(state, action, card)[0]
    assert unit_at(result, 5).buffed is False
    assert any(u.buffed for u in result.players[0].base_units)
