""""Channel N runes exhausted" cards (RULING 1, project owner, 2026-09-18):
no Rune Deck exists in this engine, so a channelled rune's domain is
unknowable. It contributes Energy capacity only, never Power, via
state.add_runes, and "...exhausted" means it arrives with that Energy
already spent — real but narrow, since nothing is observable from it
unless something readies runes later the SAME turn (see
test_deathknell.py's Soaring Scout + Ekko interaction test for that case
worked all the way through).

This file covers the mandatory play-trigger shape (Stormclaw Ursine) and
the per-buff-spent shape (Albus Ferros).
"""

import dataclasses

from solver.engine.abilities import (
    ALBUS_FERROS,
    STORMCLAW_URSINE,
    is_legal_unit_play_trigger,
    resolve_unit_play_trigger_outcomes,
)
from solver.engine.actions import PlayUnit, generate_rune_payments
from solver.engine.card_pool import card_def
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from solver.search import legal_actions

STORMCLAW_URSINE_CARD = card_def(STORMCLAW_URSINE)
ALBUS_FERROS_CARD = card_def(ALBUS_FERROS)


def make_root(hand, runes=(), cards_played_this_turn=0, base_units=frozenset()):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=hand, runes=RunePool(available=runes), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=cards_played_this_turn,
    )


# --- Stormclaw Ursine: "[Tank] When you play me, channel 1 rune exhausted." ---


def test_stormclaw_ursine_channels_a_domain_less_rune_on_play():
    runes = ("Fury",) * STORMCLAW_URSINE_CARD.energy_cost
    root = make_root(hand=(STORMCLAW_URSINE,), runes=runes)
    payment = generate_rune_payments(root.players[0].runes, STORMCLAW_URSINE_CARD.energy_cost,
                                      STORMCLAW_URSINE_CARD.power_cost,
                                      STORMCLAW_URSINE_CARD.power_domain)[0]
    action = PlayUnit(card_id=STORMCLAW_URSINE, target_zone="base", rune_payment=payment,
                       trigger_params=("channel",))
    assert is_legal_unit_play_trigger(root, action, STORMCLAW_URSINE_CARD)

    outcomes = resolve_unit_play_trigger_outcomes(root, action, STORMCLAW_URSINE_CARD)
    assert len(outcomes) == 1
    pool = outcomes[0].players[0].runes
    assert pool.available.count(None) == 1
    from solver.engine.state import energy_capacity
    # The 7 Fury runes are fully spent on the card's own cost, and the
    # channelled rune arrives already-exhausted, so total capacity is
    # unaffected by this trigger on its own.
    assert energy_capacity(pool) == 0


def test_stormclaw_ursine_only_the_triggered_form_is_a_legal_action():
    """Mandatory, same regression shape as Faithful Manufactor
    (test_token_triggers.py): "play it WITHOUT channelling" was never
    actually a legal choice, so legal_actions() must withhold the bare
    trigger_params=() PlayUnit."""
    runes = ("Fury",) * STORMCLAW_URSINE_CARD.energy_cost
    root = make_root(hand=(STORMCLAW_URSINE,), runes=runes)
    cards = {STORMCLAW_URSINE: STORMCLAW_URSINE_CARD}
    play_unit_actions = [a for a in legal_actions(root, cards) if isinstance(a, PlayUnit)]
    assert len(play_unit_actions) == 1
    assert play_unit_actions[0].trigger_params == ("channel",)


# --- Albus Ferros: "spend any number of buffs, channel 1 rune exhausted each" ---


def _buffed_unit(instance_id, controller=0):
    return UnitInstance(card_id="tok", instance_id=instance_id, controller=controller,
                        might=1, keywords=frozenset(), exhausted=False, damage=0,
                        is_token=True, buffed=True)


def test_albus_ferros_declining_is_legal_and_channels_nothing():
    """"Any number" includes zero — not mandatory, unlike Stormclaw Ursine."""
    buffed = _buffed_unit(5)
    runes = ("Fury",) * ALBUS_FERROS_CARD.energy_cost
    root = make_root(hand=(ALBUS_FERROS,), runes=runes, base_units=frozenset({buffed}))
    payment = generate_rune_payments(root.players[0].runes, ALBUS_FERROS_CARD.energy_cost,
                                      ALBUS_FERROS_CARD.power_cost, ALBUS_FERROS_CARD.power_domain)[0]
    action = PlayUnit(card_id=ALBUS_FERROS, target_zone="base", rune_payment=payment, trigger_params=())
    assert is_legal_unit_play_trigger(root, action, ALBUS_FERROS_CARD)
    outcomes = resolve_unit_play_trigger_outcomes(root, action, ALBUS_FERROS_CARD)
    assert outcomes[0].players[0].runes.available.count(None) == 0
    assert next(u for u in outcomes[0].players[0].base_units if u.instance_id == 5).buffed


def test_albus_ferros_spending_two_buffs_channels_two_domain_less_runes():
    buffed_a, buffed_b = _buffed_unit(5), _buffed_unit(6)
    runes = ("Fury",) * ALBUS_FERROS_CARD.energy_cost
    root = make_root(hand=(ALBUS_FERROS,), runes=runes, base_units=frozenset({buffed_a, buffed_b}))
    payment = generate_rune_payments(root.players[0].runes, ALBUS_FERROS_CARD.energy_cost,
                                      ALBUS_FERROS_CARD.power_cost, ALBUS_FERROS_CARD.power_domain)[0]
    action = PlayUnit(card_id=ALBUS_FERROS, target_zone="base", rune_payment=payment,
                       trigger_params=(5, 6))
    assert is_legal_unit_play_trigger(root, action, ALBUS_FERROS_CARD)
    outcomes = resolve_unit_play_trigger_outcomes(root, action, ALBUS_FERROS_CARD)
    result_units = outcomes[0].players[0].base_units
    assert not next(u for u in result_units if u.instance_id == 5).buffed
    assert not next(u for u in result_units if u.instance_id == 6).buffed
    assert outcomes[0].players[0].runes.available.count(None) == 2


def test_albus_ferros_cannot_spend_a_buff_he_does_not_have():
    root = make_root(hand=(ALBUS_FERROS,), runes=("Fury",) * ALBUS_FERROS_CARD.energy_cost)
    payment = generate_rune_payments(root.players[0].runes, ALBUS_FERROS_CARD.energy_cost,
                                      ALBUS_FERROS_CARD.power_cost, ALBUS_FERROS_CARD.power_domain)[0]
    # No buffed unit at all on the board — instance_id 5 doesn't exist.
    action = PlayUnit(card_id=ALBUS_FERROS, target_zone="base", rune_payment=payment,
                       trigger_params=(5,))
    assert not is_legal_unit_play_trigger(root, action, ALBUS_FERROS_CARD)


def test_albus_ferros_appears_in_legal_actions_with_every_buff_subset():
    buffed_a, buffed_b = _buffed_unit(5), _buffed_unit(6)
    root = make_root(hand=(ALBUS_FERROS,), runes=("Fury",) * ALBUS_FERROS_CARD.energy_cost,
                     base_units=frozenset({buffed_a, buffed_b}))
    cards = {ALBUS_FERROS: ALBUS_FERROS_CARD}
    play_unit_actions = [a for a in legal_actions(root, cards) if isinstance(a, PlayUnit)]
    subsets = {a.trigger_params for a in play_unit_actions}
    assert subsets == {(), (5,), (6,), (5, 6)}
