"""The coverage ledger and the refusal it drives.

The property under test is "the engine never bluffs": for any board, it
either answers correctly or names the cards it can't reason about. With
298 Origins cards and a couple of dozen modelled, an engine that silently
treats unknown text as absent gives wrong answers that look exactly like
right ones.
"""

import json

from solver.engine import card_names, coverage
from solver.engine.card_pool import CARD_POOL, card_def
from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    UnitInstance,
)
from solver.lethal import find_lethal

VOLIBEAR = "ogn-041-298"  # [Deflect 2] + "when I attack, deal 5 damage split among enemies"
STALWART_PORO = "ogn-052-298"  # handled: plain [Shield]


def make_unit(card_id, instance_id=1, controller=0, might=3):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=frozenset(), exhausted=False, damage=0,
                         is_token=False)


def make_state(base_units=frozenset(), hand=(), left_units=frozenset(), left_effect=None):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=hand, runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, left_units, left_effect),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


# --- ledger integrity ---


def test_every_ledger_entry_is_a_real_printing():
    """A typo or a renamed printing would silently clear the wrong card,
    which is worse than not clearing it at all."""
    cache = json.loads(coverage.card_names.CACHE_PATH.read_text(encoding="utf-8"))
    listed = (list(coverage.HANDLED) + list(coverage.INERT_FOR_LETHAL)
              + list(coverage.CONDITIONALLY_CLEARED))
    for card_id in listed:
        assert card_id in cache, f"{card_id} is in the ledger but not in the card cache"


# --- board-conditional inertness ---


def test_vision_is_inert_on_its_own():
    """No Main Deck, so looking at its top card does nothing observable."""
    state = make_state(left_units=frozenset({make_unit("ogn-171-298", 1)}))  # Mystic Poro
    assert coverage.blocking_cards(state) == []


def test_vision_becomes_blocking_next_to_karma():
    """Karma, Channeler is the one card that triggers on recycling, which
    would turn a Vision into a Might buff — so the same card stops being
    inert purely because of what else is on the board."""
    state = make_state(
        left_units=frozenset({make_unit("ogn-171-298", 1), make_unit(coverage.KARMA_CHANNELER, 2)}))
    reasons = coverage.blocking_cards(state)
    assert any("ogn-171-298" in r for r in reasons), "Mystic Poro should block beside Karma"


def test_conditional_inertness_defaults_to_blocking_without_a_board():
    """classify() with no board can't verify the condition, so it must
    take the unsafe-to-assume side."""
    assert coverage.classify("ogn-171-298") == "blocking"
    assert coverage.classify("ogn-171-298", present={"ogn-171-298"}) == "inert"


def test_no_card_is_both_handled_and_inert():
    assert not set(coverage.HANDLED) & set(coverage.INERT_FOR_LETHAL)


def test_blocking_is_the_default_for_an_unlisted_card():
    """The fail-safe direction: a card nobody has classified refuses,
    rather than being quietly assumed harmless."""
    assert coverage.classify("ogn-999-298") == "blocking"
    assert coverage.classify(VOLIBEAR) == "blocking"


def test_being_in_card_pool_does_not_clear_a_card(monkeypatch):
    """Faithful Manufactor sat in CARD_POOL with a trigger that did
    nothing. Membership means "the engine has stats for it", not "the
    engine understands it", so the ledger must not be derived from it.

    Caitlyn, Blitzcrank and Taric were the live proof of this until
    [Tank] and "assigned combat damage last" were implemented — the
    ledger flagged all three as blocking while they sat in CARD_POOL
    looking done, and that is exactly what it exists to do. They are now
    cleared on their merits.

    The principle still has to hold, so it is exercised directly: drop a
    card out of HANDLED and it must go straight back to blocking even
    though CARD_POOL is untouched. If classify() ever started consulting
    CARD_POOL, this would wrongly report handled.
    """
    victim = "ogn-052-298"  # Stalwart Poro, in both CARD_POOL and HANDLED
    assert victim in CARD_POOL and coverage.classify(victim) == "handled"
    monkeypatch.delitem(coverage.HANDLED, victim)
    assert victim in CARD_POOL
    assert coverage.classify(victim) == "blocking"


def test_being_a_registered_legend_ability_does_not_clear_it(monkeypatch):
    """The Legend-side analogue: Yasuo, Unforgiven's ability has been a
    complete, tested, legal_actions-reachable legends.LEGEND_ABILITIES
    entry since before this session and is STILL "blocking" here — nobody
    has written its coverage ledger entry yet, which is exactly the state
    the ledger is supposed to be able to represent. Blind Monk must be
    cleared on its own ledger entry, not because legends.py can run it."""
    from solver.engine import legends

    assert legends.is_legend_ability(legends.YASUO_UNFORGIVEN)
    assert coverage.classify(legends.YASUO_UNFORGIVEN) == "blocking"

    victim = "ogn-257-298"  # Blind Monk
    assert legends.is_legend_ability(victim) and coverage.classify(victim) == "handled"
    monkeypatch.delitem(coverage.HANDLED, victim)
    assert legends.is_legend_ability(victim)  # legends.py is untouched
    assert coverage.classify(victim) == "blocking"


def test_every_handled_card_has_stats_available():
    """Nothing should be cleared as handled that the engine has no stats
    for — that's a different flavour of the same lie. A card in HAND with
    no CardDef is silently skipped by action generation, so the line that
    plays it is never considered and the result is indistinguishable from
    no such line existing.

    Stats may come from the hand-written pool OR be derived from the card
    cache; what matters is that something can describe it.

    Legends are the one structural exception: a Legend is never drawn or
    played from hand (legends.py's own docstring — LegendState carries a
    bare card_id, no cost fields at all, since it starts in its own zone
    as part of the puzzle's initial position) and its ability's
    reachability runs through player.legend directly in search.py, not
    through the cards/CardDef table this test exists to guard. So the
    exact failure mode this test checks for — "skipped by action
    generation because nothing could describe it" — cannot happen to one,
    and CardType has no Legend representation for card_def() to produce
    regardless (see card_data.py's REPRESENTABLE_TYPES)."""
    cache = json.loads(coverage.card_names.CACHE_PATH.read_text(encoding="utf-8"))
    for card_id in coverage.HANDLED:
        if cache.get(card_id, {}).get("type") == "Legend":
            continue
        assert card_def(card_id) is not None, \
            f"{card_id} cleared as handled but nothing can supply its stats"


def test_find_lethal_builds_its_own_card_table():
    """Correctness, not convenience: a card in hand with no CardDef is
    silently skipped by action generation, so the line that plays it is
    never considered and the answer looks identical to no line existing.
    Asking about a board must not require hand-assembling stats."""
    from solver.engine.card_pool import cards_for_board

    blazing_scorcher = "ogn-001-298"  # cleared, but NOT in the hand-written pool
    state = make_state(hand=(blazing_scorcher,))
    assert blazing_scorcher not in CARD_POOL
    assert blazing_scorcher in cards_for_board(state)
    assert find_lethal(state).outcome == "no_lethal"  # answered, not refused


def test_a_generated_card_def_does_not_clear_the_card():
    """Stats and understanding are separate. Volibear's numbers derive
    cleanly from the cache, and he still refuses — otherwise the wiring
    would have quietly turned the whole set 'handled'."""
    assert card_def(VOLIBEAR) is not None
    assert coverage.classify(VOLIBEAR) == "blocking"


# --- what the board scan sees ---


def test_scan_finds_cards_in_every_zone():
    state = make_state(base_units=frozenset({make_unit("a", 1)}), hand=("b",),
                        left_units=frozenset({make_unit("c", 2)}), left_effect="d")
    assert coverage.card_ids_present(state) >= {"a", "b", "c", "d"}


def test_the_synthetic_opponent_body_is_not_treated_as_an_unmodelled_card():
    """generate.py's "generic-opponent" is a stat-stick the engine invents,
    not a printing — it has no text to miss."""
    state = make_state(left_units=frozenset({make_unit("generic-opponent", 1, controller=1)}))
    assert coverage.blocking_cards(state) == []


# --- the refusal itself ---


def test_a_board_with_an_unmodelled_card_is_unanswerable_and_names_it():
    state = make_state(left_units=frozenset({make_unit(VOLIBEAR, 1, controller=1, might=9)}))
    answer = find_lethal(state, {})
    assert answer.outcome == "unanswerable"
    assert any(VOLIBEAR in reason for reason in answer.blocking)
    assert any("deal 5" in reason.lower() for reason in answer.blocking), \
        "the refusal should quote the card's own text, not just its id"


def test_an_unanswerable_board_is_falsy():
    """`if find_lethal(...)` must never be satisfied by a board the engine
    couldn't actually reason about."""
    state = make_state(left_units=frozenset({make_unit(VOLIBEAR, 1, controller=1, might=9)}))
    assert not find_lethal(state, {})


def test_a_fully_modelled_board_gets_a_real_answer():
    state = make_state(base_units=frozenset({make_unit(STALWART_PORO, 1)}))
    answer = find_lethal(state, {})
    assert answer.outcome == "no_lethal"  # nothing to attack, no score
    assert answer.blocking == ()


def test_no_lethal_and_unanswerable_are_not_conflated():
    modelled = make_state(base_units=frozenset({make_unit(STALWART_PORO, 1)}))
    unmodelled = make_state(base_units=frozenset({make_unit(VOLIBEAR, 1, might=9)}))
    assert find_lethal(modelled, {}).outcome == "no_lethal"
    assert find_lethal(unmodelled, {}).outcome == "unanswerable"


def test_ignore_unmodelled_forces_an_answer():
    """The opt-out the hand-authored puzzles need, since their positions
    were built against the engine's own subset."""
    state = make_state(base_units=frozenset({make_unit(VOLIBEAR, 1, might=9)}))
    assert find_lethal(state, {}, ignore_unmodelled=True).outcome == "no_lethal"
