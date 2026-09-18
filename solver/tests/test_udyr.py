"""Udyr, Wildman: "Spend my buff: Choose one you've not chosen this turn —
Deal 2 to a unit at a battlefield. Stun a unit at a battlefield. Ready me.
Give me [Ganking] this turn."

All four modes reuse existing primitives; the one new piece is
UnitInstance.modes_chosen_this_turn, which the "not chosen this turn"
restriction reads. His Stun mode also has to exercise the SAME Radiant
Dawn observer hook Leona's does (abilities._stun_buff_choice_active),
since Udyr's "stun A UNIT" is unrestricted-controller and could target a
friendly unit, unlike Leona's "an enemy unit" — the observer must only
fire when the stunned unit is actually an enemy.
"""

from solver import search
from solver.engine import abilities
from solver.engine.abilities import RADIANT_DAWN, UDYR_WILDMAN
from solver.engine.actions import ActivateAbility
from solver.engine.card_pool import card_def
from solver.engine.state import (
    BattlefieldState,
    GameState,
    LegendState,
    PlayerState,
    RunePool,
    UnitInstance,
)

UDYR_CARD = card_def(UDYR_WILDMAN)


def make_unit(card_id, instance_id, controller=0, might=6, keywords=frozenset(),
              buffed=False, exhausted=False, damage=0, modes_chosen_this_turn=frozenset()):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=keywords, exhausted=exhausted, damage=damage,
                         is_token=False, buffed=buffed, modes_chosen_this_turn=modes_chosen_this_turn)


def make_state(base_units=frozenset(), left_units=frozenset(), left_ctrl=None, legend=None):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=(), runes=RunePool(available=()), score=0,
                        legend=legend),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", left_ctrl, left_units, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


# --- reachability: each mode, through search.legal_actions -----------------


def test_no_buff_offers_nothing():
    udyr = make_unit(UDYR_WILDMAN, 1, buffed=False)
    state = make_state(base_units=frozenset({udyr}))
    actions = search.legal_actions(state, {UDYR_WILDMAN: UDYR_CARD})
    assert not any(isinstance(a, ActivateAbility) and a.ability_id == UDYR_WILDMAN for a in actions)


def test_all_four_modes_are_offered_when_buffed():
    udyr = make_unit(UDYR_WILDMAN, 1, buffed=True, exhausted=True)  # exhausted: Ready has something to do
    enemy = make_unit("u", 2, controller=1, might=3)
    state = make_state(base_units=frozenset({udyr}), left_units=frozenset({enemy}), left_ctrl=1)
    actions = [a for a in search.legal_actions(state, {UDYR_WILDMAN: UDYR_CARD})
               if isinstance(a, ActivateAbility) and a.ability_id == UDYR_WILDMAN]
    modes = {a.params[0] for a in actions}
    assert modes == {"deal2", "stun", "ready", "ganking"}


def test_deal_2_reaches_the_enemy_through_search_and_apply():
    udyr = make_unit(UDYR_WILDMAN, 1, buffed=True)
    enemy = make_unit("u", 2, controller=1, might=3)
    state = make_state(base_units=frozenset({udyr}), left_units=frozenset({enemy}), left_ctrl=1)
    cards = {UDYR_WILDMAN: UDYR_CARD}
    action = ActivateAbility(source_id=1, ability_id=UDYR_WILDMAN, params=("deal2", 2), rune_payment=None)
    assert action in search.legal_actions(state, cards)
    result = search.apply(state, action, cards)
    left = next(bf for bf in result.battlefields if bf.battlefield_id == "left")
    hit = next(u for u in left.units if u.instance_id == 2)
    assert hit.damage == 2
    udyr_after = next(u for u in result.players[0].base_units if u.instance_id == 1)
    assert udyr_after.buffed is False  # spent
    assert udyr_after.modes_chosen_this_turn == frozenset({"deal2"})


def test_ready_mode():
    udyr = make_unit(UDYR_WILDMAN, 1, buffed=True, exhausted=True)
    state = make_state(base_units=frozenset({udyr}))
    cards = {UDYR_WILDMAN: UDYR_CARD}
    action = ActivateAbility(source_id=1, ability_id=UDYR_WILDMAN, params=("ready",), rune_payment=None)
    assert action in search.legal_actions(state, cards)
    result = search.apply(state, action, cards)
    udyr_after = next(u for u in result.players[0].base_units if u.instance_id == 1)
    assert udyr_after.exhausted is False
    assert udyr_after.modes_chosen_this_turn == frozenset({"ready"})


def test_ganking_mode():
    udyr = make_unit(UDYR_WILDMAN, 1, buffed=True)
    state = make_state(base_units=frozenset({udyr}))
    cards = {UDYR_WILDMAN: UDYR_CARD}
    action = ActivateAbility(source_id=1, ability_id=UDYR_WILDMAN, params=("ganking",), rune_payment=None)
    assert action in search.legal_actions(state, cards)
    result = search.apply(state, action, cards)
    udyr_after = next(u for u in result.players[0].base_units if u.instance_id == 1)
    assert "Ganking" in udyr_after.keywords
    assert udyr_after.modes_chosen_this_turn == frozenset({"ganking"})


def test_stun_mode_without_radiant_dawn():
    udyr = make_unit(UDYR_WILDMAN, 1, buffed=True)
    enemy = make_unit("u", 2, controller=1, might=3)
    state = make_state(base_units=frozenset({udyr}), left_units=frozenset({enemy}), left_ctrl=1)
    cards = {UDYR_WILDMAN: UDYR_CARD}
    action = ActivateAbility(source_id=1, ability_id=UDYR_WILDMAN, params=("stun", 2), rune_payment=None)
    assert action in search.legal_actions(state, cards)
    result = search.apply(state, action, cards)
    left = next(bf for bf in result.battlefields if bf.battlefield_id == "left")
    assert next(u for u in left.units if u.instance_id == 2).stunned is True


# --- "not chosen this turn" restriction -------------------------------------


def test_a_mode_already_chosen_this_turn_is_not_offered_again():
    """Direct restriction check: Udyr starts already re-buffed with "deal2"
    already recorded as chosen (simulating a second buff mid-turn) — that
    mode must not be offered a second time, but the other three still are."""
    udyr = make_unit(UDYR_WILDMAN, 1, buffed=True, modes_chosen_this_turn=frozenset({"deal2"}))
    enemy = make_unit("u", 2, controller=1, might=3)
    state = make_state(base_units=frozenset({udyr}), left_units=frozenset({enemy}), left_ctrl=1)
    actions = [a for a in search.legal_actions(state, {UDYR_WILDMAN: UDYR_CARD})
               if isinstance(a, ActivateAbility) and a.ability_id == UDYR_WILDMAN]
    modes = {a.params[0] for a in actions}
    assert modes == {"stun", "ready", "ganking"}


def test_a_re_buffed_udyr_can_pick_a_second_distinct_mode_end_to_end():
    """End-to-end through a REAL second buff source (Pit Rookie's "when you
    play me, buff another friendly unit" play trigger), proving the
    restriction is exercised by real cards, not just direct state
    construction: Udyr picks "ready" first, gets re-buffed by Pit Rookie,
    and can then pick a different mode but never "ready" again."""
    import dataclasses as _dc

    from solver.engine.abilities import PIT_ROOKIE, resolve_unit_play_trigger_outcomes
    from solver.engine.actions import PlayUnit, RunePayment
    from solver.engine.card_pool import card_def as _card_def

    udyr = make_unit(UDYR_WILDMAN, 1, buffed=True, exhausted=True)
    enemy = make_unit("u", 2, controller=1, might=3)  # gives "deal2"/"stun" a target
    state = make_state(base_units=frozenset({udyr}), left_units=frozenset({enemy}), left_ctrl=1)
    cards = {UDYR_WILDMAN: UDYR_CARD}

    # Udyr readies himself, spending his starting buff and recording "ready".
    ready_action = ActivateAbility(source_id=1, ability_id=UDYR_WILDMAN, params=("ready",), rune_payment=None)
    state = search.apply(state, ready_action, cards)
    udyr_after = next(u for u in state.players[0].base_units if u.instance_id == 1)
    assert udyr_after.buffed is False and udyr_after.modes_chosen_this_turn == frozenset({"ready"})

    # Put Pit Rookie in hand with enough runes, then play it to base,
    # choosing its trigger to re-buff Udyr (instance_id 1).
    pit_card = _card_def(PIT_ROOKIE)
    player = state.players[0]
    state = _dc.replace(state, players=(
        _dc.replace(player, hand=(PIT_ROOKIE,), runes=RunePool(available=("Fury",) * 8)),
        state.players[1],
    ))
    payment = RunePayment(energy_runes=("Fury",) * pit_card.energy_cost,
                          power_runes=(pit_card.power_domain,) * pit_card.power_cost)
    play_action = PlayUnit(card_id=PIT_ROOKIE, target_zone="base", rune_payment=payment,
                            trigger_params=(1,))
    state = resolve_unit_play_trigger_outcomes(state, play_action, pit_card)[0]
    udyr_after = next(u for u in state.players[0].base_units if u.instance_id == 1)
    assert udyr_after.buffed is True  # re-buffed mid-turn

    actions = [a for a in search.legal_actions(state, {**cards, PIT_ROOKIE: pit_card})
               if isinstance(a, ActivateAbility) and a.ability_id == UDYR_WILDMAN]
    modes = {a.params[0] for a in actions}
    assert modes == {"deal2", "stun", "ganking"}  # "ready" excluded, already chosen
    assert "ready" not in modes


# --- Radiant Dawn coupling: only an ENEMY stun qualifies --------------------


def test_udyr_stunning_an_enemy_offers_radiant_dawns_buff_choice():
    udyr = make_unit(UDYR_WILDMAN, 1, buffed=True)
    ally = make_unit("u", 3, controller=0, might=1)
    enemy = make_unit("u", 2, controller=1, might=3)
    legend = LegendState(card_id=RADIANT_DAWN)
    state = make_state(base_units=frozenset({udyr, ally}), left_units=frozenset({enemy}),
                        left_ctrl=1, legend=legend)
    actions = [a for a in search.legal_actions(state, {UDYR_WILDMAN: UDYR_CARD})
               if isinstance(a, ActivateAbility) and a.ability_id == UDYR_WILDMAN
               and a.params[0] == "stun"]
    param_sets = {a.params for a in actions}
    # One candidate per friendly unit (ally, Udyr himself) to receive the
    # buff — the plain 2-tuple stun-only form must be gone (mandatory once
    # active).
    assert param_sets == {("stun", 2, 1), ("stun", 2, 3)}

    chosen = next(a for a in actions if a.params == ("stun", 2, 3))
    result = search.apply(state, chosen, {UDYR_WILDMAN: UDYR_CARD})
    left = next(bf for bf in result.battlefields if bf.battlefield_id == "left")
    assert next(u for u in left.units if u.instance_id == 2).stunned is True
    ally_after = next(u for u in result.players[0].base_units if u.instance_id == 3)
    assert ally_after.buffed is True


def test_udyr_stunning_a_friendly_unit_does_not_trigger_radiant_dawn():
    """Udyr's "stun A UNIT" is unrestricted — he CAN stun his own side.
    Radiant Dawn only watches for ENEMY stuns, so that choice must stay a
    plain 2-tuple even with the observer present."""
    udyr = make_unit(UDYR_WILDMAN, 1, buffed=True)
    ally = make_unit("u", 3, controller=0, might=1)
    legend = LegendState(card_id=RADIANT_DAWN)
    # Both stand at "left" (self-controlled) — "a unit at a battlefield"
    # excludes Base, so this is where stun targets have to live.
    state = make_state(left_units=frozenset({udyr, ally}), left_ctrl=0, legend=legend)
    actions = [a for a in search.legal_actions(state, {UDYR_WILDMAN: UDYR_CARD})
               if isinstance(a, ActivateAbility) and a.ability_id == UDYR_WILDMAN
               and a.params[0] == "stun"]
    param_sets = {a.params for a in actions}
    # Both possible stun targets (Udyr himself, or the ally) are friendly,
    # so neither qualifies for the buff choice.
    assert param_sets == {("stun", 1), ("stun", 3)}
