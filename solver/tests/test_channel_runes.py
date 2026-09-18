""""Channel N runes exhausted" cards (RULING 1, project owner, 2026-09-18):
no Rune Deck exists in this engine, so a channelled rune's domain is
unknowable. It contributes Energy capacity only, never Power, via
state.add_runes, and "...exhausted" means it arrives with that Energy
already spent — real but narrow, since nothing is observable from it
unless something readies runes later the SAME turn (see
test_deathknell.py's Soaring Scout + Ekko interaction test for that case
worked all the way through).

This file covers the mandatory play-trigger shape (Stormclaw Ursine), the
per-buff-spent shape (Albus Ferros), and the Legend "observer" shape
(Relentless Storm).
"""

import dataclasses

from solver.engine.abilities import (
    ALBUS_FERROS,
    CATALYST_OF_AEONS,
    MOBILIZE,
    STORMCLAW_URSINE,
    is_legal_play_spell,
    is_legal_unit_play_trigger,
    resolve_spell_outcomes,
    resolve_unit_play_trigger_outcomes,
)
from solver.engine.actions import PlaySpell, PlayUnit, apply_play_unit, generate_rune_payments
from solver.engine.card_pool import card_def
from solver.engine import legends
from solver.engine.state import (
    BattlefieldState,
    GameState,
    LegendState,
    PlayerState,
    RunePool,
    UnitInstance,
)
from solver.search import apply, legal_actions

STORMCLAW_URSINE_CARD = card_def(STORMCLAW_URSINE)
ALBUS_FERROS_CARD = card_def(ALBUS_FERROS)
MOBILIZE_CARD = card_def(MOBILIZE)
CATALYST_OF_AEONS_CARD = card_def(CATALYST_OF_AEONS)
PLAYFUL_PHANTOM = "ogn-049-298"  # vanilla, 5 Might — HANDLED (no printed text)
PLAYFUL_PHANTOM_CARD = card_def(PLAYFUL_PHANTOM)
STALWART_PORO = "ogn-052-298"  # [Shield], 2 Might — HANDLED, not Mighty
STALWART_PORO_CARD = card_def(STALWART_PORO)


def make_root(hand, runes=(), cards_played_this_turn=0, base_units=frozenset(), legend=None):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=hand, runes=RunePool(available=runes), score=0,
                        legend=legend),
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


# --- Relentless Storm: Legend "observer" reaction to a Mighty unit's play ---


def test_relentless_storm_reaction_offered_and_declined_are_both_legal():
    legend = LegendState(card_id=legends.RELENTLESS_STORM, exhausted=False)
    runes = ("Fury",) * PLAYFUL_PHANTOM_CARD.energy_cost
    root = make_root(hand=(PLAYFUL_PHANTOM,), runes=runes, legend=legend)
    cards = {PLAYFUL_PHANTOM: PLAYFUL_PHANTOM_CARD}
    play_unit_actions = [a for a in legal_actions(root, cards) if isinstance(a, PlayUnit)]
    reaction_choices = {a.legend_reaction_params for a in play_unit_actions}
    assert reaction_choices == {(), ("channel",)}


def test_relentless_storm_reaction_exhausts_the_legend_and_channels_a_domain_less_rune():
    legend = LegendState(card_id=legends.RELENTLESS_STORM, exhausted=False)
    runes = ("Fury",) * PLAYFUL_PHANTOM_CARD.energy_cost
    root = make_root(hand=(PLAYFUL_PHANTOM,), runes=runes, legend=legend)
    payment = generate_rune_payments(root.players[0].runes, PLAYFUL_PHANTOM_CARD.energy_cost,
                                      PLAYFUL_PHANTOM_CARD.power_cost,
                                      PLAYFUL_PHANTOM_CARD.power_domain)[0]
    action = PlayUnit(card_id=PLAYFUL_PHANTOM, target_zone="base", rune_payment=payment,
                       legend_reaction_params=("channel",))
    is_legal, _ = legends.LEGEND_OBSERVER_PLAY_TRIGGERS[legends.RELENTLESS_STORM]
    assert is_legal(root, action, PLAYFUL_PHANTOM_CARD)

    cards = {PLAYFUL_PHANTOM: PLAYFUL_PHANTOM_CARD}
    result = apply(root, action, cards)
    assert result.players[0].legend.exhausted is True
    assert result.players[0].runes.available.count(None) == 1
    from solver.engine.state import energy_capacity
    assert energy_capacity(result.players[0].runes) == 0  # arrives already-exhausted


def test_relentless_storm_declining_leaves_legend_unexhausted():
    legend = LegendState(card_id=legends.RELENTLESS_STORM, exhausted=False)
    runes = ("Fury",) * PLAYFUL_PHANTOM_CARD.energy_cost
    root = make_root(hand=(PLAYFUL_PHANTOM,), runes=runes, legend=legend)
    payment = generate_rune_payments(root.players[0].runes, PLAYFUL_PHANTOM_CARD.energy_cost,
                                      PLAYFUL_PHANTOM_CARD.power_cost,
                                      PLAYFUL_PHANTOM_CARD.power_domain)[0]
    action = PlayUnit(card_id=PLAYFUL_PHANTOM, target_zone="base", rune_payment=payment)
    cards = {PLAYFUL_PHANTOM: PLAYFUL_PHANTOM_CARD}
    result = apply(root, action, cards)
    assert result.players[0].legend.exhausted is False
    assert result.players[0].runes.available.count(None) == 0


def test_relentless_storm_not_offered_for_a_non_mighty_unit():
    """Stalwart Poro is 2 Might — below the 5+ Mighty threshold — so the
    reaction must never appear as a legal choice for it."""
    legend = LegendState(card_id=legends.RELENTLESS_STORM, exhausted=False)
    runes = ("Fury",) * STALWART_PORO_CARD.energy_cost
    root = make_root(hand=(STALWART_PORO,), runes=runes, legend=legend)
    cards = {STALWART_PORO: STALWART_PORO_CARD}
    play_unit_actions = [a for a in legal_actions(root, cards) if isinstance(a, PlayUnit)]
    assert all(a.legend_reaction_params == () for a in play_unit_actions)


def test_relentless_storm_not_offered_when_already_exhausted():
    legend = LegendState(card_id=legends.RELENTLESS_STORM, exhausted=True)
    runes = ("Fury",) * PLAYFUL_PHANTOM_CARD.energy_cost
    root = make_root(hand=(PLAYFUL_PHANTOM,), runes=runes, legend=legend)
    cards = {PLAYFUL_PHANTOM: PLAYFUL_PHANTOM_CARD}
    play_unit_actions = [a for a in legal_actions(root, cards) if isinstance(a, PlayUnit)]
    assert all(a.legend_reaction_params == () for a in play_unit_actions)


def test_relentless_storm_not_offered_for_a_different_legend():
    legend = LegendState(card_id=legends.BOUNTY_HUNTER, exhausted=False)
    runes = ("Fury",) * PLAYFUL_PHANTOM_CARD.energy_cost
    root = make_root(hand=(PLAYFUL_PHANTOM,), runes=runes, legend=legend)
    cards = {PLAYFUL_PHANTOM: PLAYFUL_PHANTOM_CARD}
    play_unit_actions = [a for a in legal_actions(root, cards) if isinstance(a, PlayUnit)]
    assert all(a.legend_reaction_params == () for a in play_unit_actions)


def test_relentless_storm_then_ekko_makes_the_channeled_rune_real():
    """The mechanism this ruling exists for, worked all the way through
    search.legal_actions/apply — mirroring test_deathknell.py's Soaring
    Scout + Ekko test. The channelled rune is inert on its own (arrives
    already-exhausted, Energy-only) until Ekko's Deathknell readies it the
    same turn — isolated here by comparing the channelled line against the
    declined one, both followed by the same Ekko death: readying gives
    back everything either way (the 5 Fury runes spent on the card's own
    cost included), so the CHANNELLED line must end up exactly 1 Energy
    ahead of the declined one, not merely "some capacity"."""
    from solver.engine.deaths import EKKO_RECURRENT
    from solver.engine.actions import kill_unit
    from solver.engine.state import energy_capacity

    legend = LegendState(card_id=legends.RELENTLESS_STORM, exhausted=False)
    runes = ("Fury",) * PLAYFUL_PHANTOM_CARD.energy_cost
    ekko = UnitInstance(card_id=EKKO_RECURRENT, instance_id=1, controller=0, might=5,
                        keywords=frozenset({"Deathknell"}), exhausted=False, damage=0, is_token=False)
    root = make_root(hand=(PLAYFUL_PHANTOM,), runes=runes, legend=legend,
                     base_units=frozenset({ekko}))
    payment = generate_rune_payments(root.players[0].runes, PLAYFUL_PHANTOM_CARD.energy_cost,
                                      PLAYFUL_PHANTOM_CARD.power_cost,
                                      PLAYFUL_PHANTOM_CARD.power_domain)[0]
    cards = {PLAYFUL_PHANTOM: PLAYFUL_PHANTOM_CARD}

    channeled_action = PlayUnit(card_id=PLAYFUL_PHANTOM, target_zone="base", rune_payment=payment,
                                 legend_reaction_params=("channel",))
    declined_action = PlayUnit(card_id=PLAYFUL_PHANTOM, target_zone="base", rune_payment=payment)

    channeled_after_ekko = kill_unit(apply(root, channeled_action, cards), 1)
    declined_after_ekko = kill_unit(apply(root, declined_action, cards), 1)

    assert (energy_capacity(channeled_after_ekko.players[0].runes)
            == energy_capacity(declined_after_ekko.players[0].runes) + 1)
    assert channeled_after_ekko.players[0].runes.available.count(None) == 1
    assert declined_after_ekko.players[0].runes.available.count(None) == 0


# --- Mobilize / Catalyst of Aeons: "channel N exhausted, if you can't draw 1" ---
#
# The "if you can't" fallback is dead text in this engine: there is no
# Rune Deck to run out of, so channeling always succeeds (contrast "draw,"
# which fails because a modelled deck is EMPTY — a different reason, not
# available here since no deck exists as a concept for runes at all).


def test_mobilize_always_takes_the_channel_branch():
    root = make_root(hand=(MOBILIZE,), runes=("Fury", "Fury"))
    payment = generate_rune_payments(root.players[0].runes, MOBILIZE_CARD.energy_cost,
                                      MOBILIZE_CARD.power_cost, MOBILIZE_CARD.power_domain)[0]
    action = PlaySpell(card_id=MOBILIZE, params=(), rune_payment=payment)
    assert is_legal_play_spell(root, action, MOBILIZE_CARD)
    outcomes = resolve_spell_outcomes(root, action, MOBILIZE_CARD)
    assert len(outcomes) == 1
    assert outcomes[0].players[0].runes.available.count(None) == 1
    # Never drew — the only other reachable outcome would have added a
    # card to hand, which this spell's hand (now empty) can't distinguish
    # from "nothing happened," so the rune is the observable proof.
    assert outcomes[0].players[0].hand == ()


def test_catalyst_of_aeons_channels_two_domain_less_runes():
    root = make_root(hand=(CATALYST_OF_AEONS,), runes=("Fury",) * 4)
    payment = generate_rune_payments(root.players[0].runes, CATALYST_OF_AEONS_CARD.energy_cost,
                                      CATALYST_OF_AEONS_CARD.power_cost,
                                      CATALYST_OF_AEONS_CARD.power_domain)[0]
    action = PlaySpell(card_id=CATALYST_OF_AEONS, params=(), rune_payment=payment)
    assert is_legal_play_spell(root, action, CATALYST_OF_AEONS_CARD)
    outcomes = resolve_spell_outcomes(root, action, CATALYST_OF_AEONS_CARD)
    assert len(outcomes) == 1
    assert outcomes[0].players[0].runes.available.count(None) == 2
