"""Faithful Manufactor ("When you play me, play a 1 Might Recruit unit
token here") and Vanguard Captain ([Legion] "When you play me, play two
1 Might Recruit unit tokens here" — only if you've played another card
this turn). Both were sitting in OUR_UNIT_POOL-only (pre-placed, trigger
already spent) as a deliberate landmine: adding either to HAND_UNIT_POOL
before this trigger existed would have minted wrong puzzles — see
findings.md.
"""

from solver.engine.abilities import (
    FAITHFUL_MANUFACTOR,
    VANGUARD_CAPTAIN,
    is_legal_unit_play_trigger,
    resolve_unit_play_trigger_outcomes,
)
from solver.engine.actions import PlayUnit, generate_rune_payments
from solver.engine.card_pool import CARD_POOL, RECRUIT_TOKEN
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool
from solver.search import legal_actions

FAITHFUL_MANUFACTOR_CARD = CARD_POOL[FAITHFUL_MANUFACTOR]
VANGUARD_CAPTAIN_CARD = CARD_POOL[VANGUARD_CAPTAIN]


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


# --- Faithful Manufactor ---


def test_faithful_manufactor_mints_one_token_to_base():
    root = make_root(hand=(FAITHFUL_MANUFACTOR,), runes=("Fury", "Fury", "Fury"))
    payment = generate_rune_payments(root.players[0].runes, FAITHFUL_MANUFACTOR_CARD.energy_cost,
                                      FAITHFUL_MANUFACTOR_CARD.power_cost,
                                      FAITHFUL_MANUFACTOR_CARD.power_domain)[0]
    action = PlayUnit(card_id=FAITHFUL_MANUFACTOR, target_zone="base", rune_payment=payment,
                       trigger_params=("mint",))
    assert is_legal_unit_play_trigger(root, action, FAITHFUL_MANUFACTOR_CARD)

    outcomes = resolve_unit_play_trigger_outcomes(root, action, FAITHFUL_MANUFACTOR_CARD)
    assert len(outcomes) == 1
    base_units = outcomes[0].players[0].base_units
    assert len(base_units) == 2  # Manufactor + the token
    token = next(u for u in base_units if u.card_id == RECRUIT_TOKEN)
    assert token.might == 1
    assert token.is_token is True
    assert token.exhausted is True  # rule 143.4.a


def test_faithful_manufactor_only_the_triggered_form_is_a_legal_action():
    """Regression for the mandatory-trigger gap: legal_board_actions used
    to always offer the bare trigger_params=() PlayUnit for every hand
    card regardless of whether its trigger was optional — wrong for a
    card whose text isn't "you may." search.legal_actions() must withhold
    it, leaving exactly one PlayUnit candidate for this card_id/zone."""
    root = make_root(hand=(FAITHFUL_MANUFACTOR,), runes=("Fury", "Fury", "Fury"))
    cards = {FAITHFUL_MANUFACTOR: FAITHFUL_MANUFACTOR_CARD}
    play_unit_actions = [a for a in legal_actions(root, cards) if isinstance(a, PlayUnit)]
    assert len(play_unit_actions) == 1
    assert play_unit_actions[0].trigger_params == ("mint",)


# --- Vanguard Captain ---


def _vanguard_action(root):
    payment = generate_rune_payments(root.players[0].runes, VANGUARD_CAPTAIN_CARD.energy_cost,
                                      VANGUARD_CAPTAIN_CARD.power_cost,
                                      VANGUARD_CAPTAIN_CARD.power_domain)[0]
    return PlayUnit(card_id=VANGUARD_CAPTAIN, target_zone="base", rune_payment=payment,
                     trigger_params=("mint",))


def test_vanguard_captain_mints_nothing_as_the_first_card_played_this_turn():
    """Legion's condition fails: no other card played yet. The effect is
    conditional, not the trigger itself — the card still enters as a
    plain body, just with zero tokens, not an illegal action."""
    root = make_root(hand=(VANGUARD_CAPTAIN,), runes=("Fury", "Fury", "Fury", "Order"),
                      cards_played_this_turn=0)
    action = _vanguard_action(root)
    assert is_legal_unit_play_trigger(root, action, VANGUARD_CAPTAIN_CARD)
    outcomes = resolve_unit_play_trigger_outcomes(root, action, VANGUARD_CAPTAIN_CARD)
    assert len(outcomes) == 1
    assert len(outcomes[0].players[0].base_units) == 1  # just Vanguard Captain


def test_vanguard_captain_mints_two_tokens_after_another_card_this_turn():
    """Off-by-one check: apply_play_unit increments cards_played_this_turn
    for Vanguard Captain's OWN play before the effect runs, so "played
    another card" (one BEFORE this play) needs cards_played_this_turn > 1
    at resolution time, not > 0 — this fixture starts it at 1 (one prior
    card), which becomes 2 once Vanguard Captain's own play is counted."""
    root = make_root(hand=(VANGUARD_CAPTAIN,), runes=("Fury", "Fury", "Fury", "Order"),
                      cards_played_this_turn=1)
    action = _vanguard_action(root)
    outcomes = resolve_unit_play_trigger_outcomes(root, action, VANGUARD_CAPTAIN_CARD)
    base_units = outcomes[0].players[0].base_units
    assert len(base_units) == 3  # Vanguard Captain + 2 tokens
    tokens = [u for u in base_units if u.card_id == RECRUIT_TOKEN]
    assert len(tokens) == 2
    assert all(t.might == 1 and t.is_token for t in tokens)


def test_vanguard_captain_only_the_triggered_form_is_a_legal_action():
    root = make_root(hand=(VANGUARD_CAPTAIN,), runes=("Fury", "Fury", "Fury", "Order"))
    cards = {VANGUARD_CAPTAIN: VANGUARD_CAPTAIN_CARD}
    play_unit_actions = [a for a in legal_actions(root, cards) if isinstance(a, PlayUnit)]
    assert len(play_unit_actions) == 1
    assert play_unit_actions[0].trigger_params == ("mint",)
