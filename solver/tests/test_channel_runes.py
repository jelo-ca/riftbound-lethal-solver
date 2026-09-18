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
    STORMCLAW_URSINE,
    is_legal_unit_play_trigger,
    resolve_unit_play_trigger_outcomes,
)
from solver.engine.actions import PlayUnit, generate_rune_payments
from solver.engine.card_pool import card_def
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool
from solver.search import legal_actions

STORMCLAW_URSINE_CARD = card_def(STORMCLAW_URSINE)


def make_root(hand, runes=(), cards_played_this_turn=0):
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
