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


def make_unit(instance_id=1, controller=0, might=3, buffed=False, exhausted=False):
    return UnitInstance(card_id="u", instance_id=instance_id, controller=controller,
                         might=might, keywords=frozenset(), exhausted=exhausted, damage=0,
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


# --- "while I'm buffed, I have X" ---

from solver.engine.traits import BILGEWATER_BULLY, WIZENED_ELDER, resolved_traits  # noqa: E402


def buffed_unit(card_id, instance_id=1, might=4, buffed=False):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=0, might=might,
                         keywords=frozenset(), exhausted=False, damage=0, is_token=False,
                         buffed=buffed)


def test_wizened_elder_gains_an_extra_might_only_while_buffed():
    """+1 from the buff itself, +1 more from its own text, so a buff is
    worth two Might on this card specifically."""
    plain = make_state(frozenset({buffed_unit(WIZENED_ELDER, might=4)}))
    assert combat.effective_might(plain, unit_at(plain), "left") == 4

    buffed = apply_buff(plain, 1)
    assert combat.effective_might(buffed, unit_at(buffed), "left") == 6


def test_bilgewater_bully_gains_ganking_only_while_buffed():
    plain = make_state(frozenset({buffed_unit(BILGEWATER_BULLY, might=6)}))
    assert "Ganking" not in resolved_traits(plain, unit_at(plain), "left")

    buffed = apply_buff(plain, 1)
    assert "Ganking" in resolved_traits(buffed, unit_at(buffed), "left")


def test_a_conditional_grant_unlocks_a_move_that_was_illegal():
    """The point of the conditional being real rather than cosmetic:
    battlefield-to-battlefield movement needs [Ganking] (rule 810), so
    buffing the Bully changes what it may legally do."""
    from solver.engine.actions import is_legal_destination

    plain = make_state(frozenset({buffed_unit(BILGEWATER_BULLY, might=6)}))
    assert not is_legal_destination(plain, unit_at(plain), "left", "right")

    buffed = apply_buff(plain, 1)
    assert is_legal_destination(buffed, unit_at(buffed), "left", "right")


def test_an_unbuffed_card_without_a_conditional_is_unaffected():
    plain = make_state(frozenset({buffed_unit("u", might=4)}))
    assert combat.effective_might(plain, unit_at(plain), "left") == 4


# --- Wildclaw Shaman: "you may spend a buff to buff me and ready me" ---

from solver.engine.abilities import (  # noqa: E402
    WILDCLAW_SHAMAN,
    is_legal_unit_play_trigger,
)
from solver.search import legal_actions  # noqa: E402


def test_wildclaw_shaman_can_decline():
    state, card, action = play(WILDCLAW_SHAMAN, "left", ())
    result = resolve_unit_play_trigger_outcomes(state, action, card)[0]
    played = max((u.instance_id for u in result.battlefields[0].units))
    assert unit_at(result, played).buffed is False
    assert unit_at(result, played).exhausted is True  # rule 143.4.a, no Accelerate paid


def test_wildclaw_shaman_spends_a_buff_to_buff_and_ready_itself():
    ally = make_unit(instance_id=5, might=2, buffed=True)
    state, card, action = play(WILDCLAW_SHAMAN, "left", (5,), board=frozenset({ally}))
    assert is_legal_unit_play_trigger(state, action, card)

    result = resolve_unit_play_trigger_outcomes(state, action, card)[0]
    assert unit_at(result, 5).buffed is False  # spent as the cost
    played = max(u.instance_id for u in result.battlefields[0].units if u.instance_id != 5)
    assert unit_at(result, played).buffed is True
    assert unit_at(result, played).exhausted is False  # "and ready me"


def test_wildclaw_shaman_cannot_spend_an_unbuffed_units_buff():
    """"Spend a buff" needs one to exist — an unbuffed ally is not a legal
    choice, only a declined trigger is."""
    ally = make_unit(instance_id=5, might=2, buffed=False)
    state, card, action = play(WILDCLAW_SHAMAN, "left", (5,), board=frozenset({ally}))
    assert not is_legal_unit_play_trigger(state, action, card)


def test_wildclaw_shaman_trigger_appears_in_legal_actions():
    """Confirms the optional trigger is reachable through the real action
    space, not just through resolve_unit_play_trigger_outcomes directly."""
    ally = make_unit(instance_id=5, might=2, buffed=True)
    state, card, _ = play(WILDCLAW_SHAMAN, "left", (), board=frozenset({ally}))
    cards = {WILDCLAW_SHAMAN: card}
    actions = [a for a in legal_actions(state, cards)
               if getattr(a, "card_id", None) == WILDCLAW_SHAMAN]
    assert any(a.trigger_params == (5,) for a in actions), \
        "spending the ally's buff should be an offered move"
    assert any(a.trigger_params == () for a in actions), "declining stays legal too"


# --- Lee Sin, Centered: "Other buffed friendly units at my battlefield
# have +2 Might" ---

from solver.engine.traits import (  # noqa: E402
    BUFF_MIGHT_AURA_SOURCES,
    LEE_SIN_CENTERED,
)


def enemy_unit(instance_id, might=3, buffed=False, card_id="e"):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=1, might=might,
                         keywords=frozenset(), exhausted=False, damage=0, is_token=False,
                         buffed=buffed)


def test_lee_sin_centered_buffs_other_buffed_units_at_his_battlefield():
    lee_sin = buffed_unit(LEE_SIN_CENTERED, instance_id=1, might=6)
    ally = buffed_unit("ally", instance_id=2, might=3, buffed=True)
    state = make_state(frozenset({lee_sin, ally}))
    assert combat.effective_might(state, unit_at(state, 2), "left") == 6  # 3 + 1 buff + 2 aura


def test_lee_sin_centered_does_not_buff_himself():
    """"OTHER buffed friendly units" — even if Lee Sin himself is buffed."""
    lee_sin = buffed_unit(LEE_SIN_CENTERED, instance_id=1, might=6, buffed=True)
    state = make_state(frozenset({lee_sin}))
    assert combat.effective_might(state, unit_at(state, 1), "left") == 7  # 6 + his own buff only


def test_lee_sin_centered_does_not_affect_an_unbuffed_ally():
    lee_sin = buffed_unit(LEE_SIN_CENTERED, instance_id=1, might=6)
    ally = buffed_unit("ally", instance_id=2, might=3, buffed=False)
    state = make_state(frozenset({lee_sin, ally}))
    assert combat.effective_might(state, unit_at(state, 2), "left") == 3


def test_lee_sin_centered_does_not_reach_another_battlefield():
    ally = buffed_unit("ally", instance_id=2, might=3, buffed=True)
    lee_sin = buffed_unit(LEE_SIN_CENTERED, instance_id=1, might=6)
    state = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, frozenset({lee_sin}), None),
            BattlefieldState("right", 0, frozenset({ally}), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    assert combat.effective_might(state, ally, "right") == 4  # buff only, no aura


def test_lee_sin_centered_does_not_buff_a_buffed_enemy():
    lee_sin = buffed_unit(LEE_SIN_CENTERED, instance_id=1, might=6)
    foe = enemy_unit(2, might=3, buffed=True)
    state = make_state(frozenset({lee_sin, foe}))
    assert combat.effective_might(state, foe, "left") == 4  # buff only


def test_buff_might_aura_registry_has_the_expected_source():
    assert BUFF_MIGHT_AURA_SOURCES[LEE_SIN_CENTERED] == 2


# --- Sett, Kingpin: "+1 Might for each buffed friendly unit at my
# battlefield" ---

from solver.engine.traits import SETT_KINGPIN  # noqa: E402


def test_sett_kingpin_counts_buffed_friendly_units_at_his_battlefield():
    sett = buffed_unit(SETT_KINGPIN, instance_id=1, might=5)
    ally_a = buffed_unit("a", instance_id=2, might=2, buffed=True)
    ally_b = buffed_unit("b", instance_id=3, might=2, buffed=True)
    state = make_state(frozenset({sett, ally_a, ally_b}))
    assert combat.effective_might(state, unit_at(state, 1), "left") == 7  # 5 + 2 buffed allies


def test_sett_kingpin_counts_his_own_buff_too():
    """The text doesn't say "other" — a buffed Sett counts himself."""
    sett = buffed_unit(SETT_KINGPIN, instance_id=1, might=5, buffed=True)
    state = make_state(frozenset({sett}))
    assert combat.effective_might(state, unit_at(state, 1), "left") == 7  # +1 buff, +1 count-of-1


def test_sett_kingpin_ignores_a_buffed_enemy():
    sett = buffed_unit(SETT_KINGPIN, instance_id=1, might=5)
    foe = enemy_unit(2, might=2, buffed=True)
    state = make_state(frozenset({sett, foe}))
    assert combat.effective_might(state, unit_at(state, 1), "left") == 5


def test_sett_kingpin_gets_no_bonus_at_base():
    sett = buffed_unit(SETT_KINGPIN, instance_id=1, might=5)
    state = make_state(base_units=frozenset({sett}))
    unit = next(iter(state.players[0].base_units))
    assert combat.effective_might(state, unit, "base") == 5


# --- Overt Operation: "For each friendly unit, you may spend its buff to
# ready it. Then buff all friendly units." ---

from solver.engine.abilities import (  # noqa: E402
    OVERT_OPERATION,
    is_legal_play_spell,
    resolve_spell_outcomes,
)
from solver.engine.actions import PlaySpell, RunePayment  # noqa: E402


def cast_overt_operation(state, params):
    card = card_def(OVERT_OPERATION)
    payment = RunePayment(energy_runes=("Fury",) * card.energy_cost,
                          power_runes=(card.power_domain,) * card.power_cost)
    action = PlaySpell(card_id=OVERT_OPERATION, params=params, rune_payment=payment)
    assert is_legal_play_spell(state, action, card)
    return resolve_spell_outcomes(state, action, card)[0]


def make_spell_state(left_units=frozenset(), base_units=frozenset(),
                      runes=("Body",) * 12, hand=(OVERT_OPERATION,)):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=hand, runes=RunePool(available=runes), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0 if left_units else None, left_units, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def test_overt_operation_buffs_every_friendly_unit_with_no_spending():
    a = make_unit(instance_id=1, might=2, buffed=False)
    b = make_unit(instance_id=2, might=2, buffed=False)
    state = make_spell_state(left_units=frozenset({a, b}))
    result = cast_overt_operation(state, ())
    assert unit_at(result, 1).buffed is True
    assert unit_at(result, 2).buffed is True


def test_overt_operation_can_spend_a_subset_to_ready_them():
    a = make_unit(instance_id=1, might=2, buffed=True, exhausted=True)
    b = make_unit(instance_id=2, might=2, buffed=True, exhausted=True)
    state = make_spell_state(left_units=frozenset({a, b}))
    result = cast_overt_operation(state, (1,))
    # 1's buff was spent to ready it, then re-buffed by "buff all" since it
    # no longer has one; 2 was never touched by the spend, only by the buff.
    assert unit_at(result, 1).exhausted is False
    assert unit_at(result, 1).buffed is True
    assert unit_at(result, 2).exhausted is True
    assert unit_at(result, 2).buffed is True


def test_overt_operation_cannot_spend_an_unbuffed_units_buff():
    a = make_unit(instance_id=1, might=2, buffed=False)
    state = make_spell_state(left_units=frozenset({a}))
    card = card_def(OVERT_OPERATION)
    payment = RunePayment(energy_runes=("Fury",) * card.energy_cost,
                          power_runes=(card.power_domain,) * card.power_cost)
    action = PlaySpell(card_id=OVERT_OPERATION, params=(1,), rune_payment=payment)
    assert not is_legal_play_spell(state, action, card)


def test_overt_operation_appears_in_legal_actions():
    a = make_unit(instance_id=1, might=2, buffed=True)
    state = make_spell_state(left_units=frozenset({a}))
    cards = {OVERT_OPERATION: card_def(OVERT_OPERATION)}
    actions = legal_actions(state, cards)
    spell_actions = [a for a in actions if isinstance(a, PlaySpell) and a.card_id == OVERT_OPERATION]
    assert any(a.params == () for a in spell_actions)
    assert any(a.params == (1,) for a in spell_actions)
