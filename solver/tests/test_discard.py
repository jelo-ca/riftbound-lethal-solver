"""The generic discard mechanism (actions.discard_from_hand) and its first
exercising card, Chemtech Enforcer ("When you play me, discard 1.") — a
card leaving hand for trash by discard, same zone transition a resolved
spell or a dying unit already get, but reachable as a real cost/effect
rather than a side effect of something else.
"""

from solver.engine import card_pool
from solver.engine.abilities import (
    CHEMTECH_ENFORCER,
    SCRAPYARD_CHAMPION,
    is_legal_unit_play_trigger,
    resolve_unit_play_trigger_outcomes,
)
from solver.engine.actions import PlayUnit, generate_rune_payments
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool
from solver.search import legal_actions

CHEMTECH_ENFORCER_CARD = card_pool.card_def(CHEMTECH_ENFORCER)
SCRAPYARD_CHAMPION_CARD = card_pool.card_def(SCRAPYARD_CHAMPION)


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


# --- Chemtech Enforcer: the mandatory single-card discard shape -----------


def _chemtech_action(root, discard_id):
    payment = generate_rune_payments(root.players[0].runes, CHEMTECH_ENFORCER_CARD.energy_cost,
                                      CHEMTECH_ENFORCER_CARD.power_cost,
                                      CHEMTECH_ENFORCER_CARD.power_domain)[0]
    return PlayUnit(card_id=CHEMTECH_ENFORCER, target_zone="base", rune_payment=payment,
                     trigger_params=(discard_id,))


def test_chemtech_enforcer_discards_the_chosen_card_and_bumps_the_counter():
    root = make_root(hand=(CHEMTECH_ENFORCER, "ogn-172-298"), runes=("Fury", "Fury"))
    action = _chemtech_action(root, "ogn-172-298")
    assert is_legal_unit_play_trigger(root, action, CHEMTECH_ENFORCER_CARD)

    outcomes = resolve_unit_play_trigger_outcomes(root, action, CHEMTECH_ENFORCER_CARD)
    assert len(outcomes) == 1
    result = outcomes[0]
    assert result.players[0].hand == ()
    assert result.players[0].trash == ("ogn-172-298",)
    assert result.cards_discarded_this_turn == 1


def test_chemtech_enforcer_cannot_discard_a_card_not_in_hand():
    root = make_root(hand=(CHEMTECH_ENFORCER,), runes=("Fury", "Fury"))
    action = _chemtech_action(root, "ogn-172-298")  # not in hand
    assert not is_legal_unit_play_trigger(root, action, CHEMTECH_ENFORCER_CARD)


def test_chemtech_enforcer_only_the_triggered_form_is_a_legal_action():
    """Same regression shape as Faithful Manufactor's: 'discard 1' is not
    'you may,' so the bare trigger_params=() PlayUnit must not survive as
    a legal action once a real discard candidate exists — proves the
    mechanism is reachable end-to-end through search.legal_actions, not
    just through the registry directly."""
    root = make_root(hand=(CHEMTECH_ENFORCER, "ogn-172-298"), runes=("Fury", "Fury"))
    cards = {CHEMTECH_ENFORCER: CHEMTECH_ENFORCER_CARD}
    play_unit_actions = [a for a in legal_actions(root, cards) if isinstance(a, PlayUnit)]
    assert len(play_unit_actions) == 1
    assert play_unit_actions[0].trigger_params == ("ogn-172-298",)


def test_chemtech_enforcer_unplayable_with_an_empty_post_play_hand():
    """No candidate to discard means no legal triggered form — and since
    the trigger is mandatory, no legal PlayUnit at all. Same convention
    already accepted for Harnessed Dragon/Riptide Rex against a target-
    less board (see abilities.py's MANDATORY_PLAY_TRIGGERS comment)."""
    root = make_root(hand=(CHEMTECH_ENFORCER,), runes=("Fury", "Fury"))
    cards = {CHEMTECH_ENFORCER: CHEMTECH_ENFORCER_CARD}
    play_unit_actions = [a for a in legal_actions(root, cards) if isinstance(a, PlayUnit)]
    assert play_unit_actions == []


# --- Scrapyard Champion: Legion-gated two-card discard ---------------------


def _scrapyard_action(root, trigger_params):
    payment = generate_rune_payments(root.players[0].runes, SCRAPYARD_CHAMPION_CARD.energy_cost,
                                      SCRAPYARD_CHAMPION_CARD.power_cost,
                                      SCRAPYARD_CHAMPION_CARD.power_domain)[0]
    return PlayUnit(card_id=SCRAPYARD_CHAMPION, target_zone="base", rune_payment=payment,
                     trigger_params=trigger_params)


def test_scrapyard_champion_skips_the_discard_when_legion_fails():
    root = make_root(hand=(SCRAPYARD_CHAMPION, "a", "b"), runes=("Fury", "Fury", "Fury", "Fury", "Fury"),
                      cards_played_this_turn=0)
    action = _scrapyard_action(root, ("skip",))
    assert is_legal_unit_play_trigger(root, action, SCRAPYARD_CHAMPION_CARD)
    outcomes = resolve_unit_play_trigger_outcomes(root, action, SCRAPYARD_CHAMPION_CARD)
    assert outcomes[0].players[0].hand == ("a", "b")
    assert outcomes[0].cards_discarded_this_turn == 0


def test_scrapyard_champion_discards_two_distinct_cards_when_legion_holds():
    root = make_root(hand=(SCRAPYARD_CHAMPION, "a", "b"), runes=("Fury", "Fury", "Fury", "Fury", "Fury"),
                      cards_played_this_turn=1)  # +1 for Scrapyard Champion's own play = 2, Legion holds
    action = _scrapyard_action(root, ("discard", "a", "b"))
    assert is_legal_unit_play_trigger(root, action, SCRAPYARD_CHAMPION_CARD)
    outcomes = resolve_unit_play_trigger_outcomes(root, action, SCRAPYARD_CHAMPION_CARD)
    result = outcomes[0]
    assert result.players[0].hand == ()
    assert sorted(result.players[0].trash) == ["a", "b"]
    assert result.cards_discarded_this_turn == 2


def test_scrapyard_champion_cannot_discard_the_same_card_twice():
    root = make_root(hand=(SCRAPYARD_CHAMPION, "a"), runes=("Fury", "Fury", "Fury", "Fury", "Fury"),
                      cards_played_this_turn=1)
    action = _scrapyard_action(root, ("discard", "a", "a"))
    assert not is_legal_unit_play_trigger(root, action, SCRAPYARD_CHAMPION_CARD)
