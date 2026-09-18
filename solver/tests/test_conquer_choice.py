"""Choice-bearing [Conquer] triggers — GameState.pending_conquer_choice's
fan-out generalization (engine/conquer.py), exercised end to end via Zaun
Warrens, the BATTLEFIELD-keyed "when you conquer here" grammar. See
conquer.py's module docstring for why the choice is modelled as a pending
marker + ResolveConquerTrigger action instead of a list-returning
resolve_control_change, and test_kaisa_evolutionary.py for the UNIT-keyed
counterpart this same machinery supports.

Every reachability test below goes through search.legal_actions/
search.apply, not a direct call into conquer.py's internals — "registered
but unreachable" is this codebase's most common self-inflicted bug (see
test_conquer.py's own module docstring).
"""

from solver import search
from solver.engine import scoring
from solver.engine.actions import MoveUnit, ResolveConquerTrigger
from solver.engine.conquer import ZAUN_WARRENS
from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    UnitInstance,
    canonical_key,
)

CHAFF = "chaff-unit"  # a plain body with no registered mechanics of its own


def make_unit(card_id, instance_id, controller=0, might=3, exhausted=False):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=frozenset(), exhausted=exhausted, damage=0,
                         is_token=False)


def make_state(base_units=frozenset(), hand=(), trash=(), score=0,
                left_units=frozenset(), left_ctrl=None, left_effect=None,
                right_units=frozenset(), right_ctrl=None,
                runes=(), scored_this_turn=frozenset()):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=hand, runes=RunePool(available=runes),
                        score=score, trash=trash),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", left_ctrl, left_units, left_effect),
            BattlefieldState("right", right_ctrl, right_units, None),
        ),
        scored_this_turn=scored_this_turn,
        cards_played_this_turn=0,
    )


# --- Zaun Warrens: BATTLEFIELD-keyed, mandatory, discard-choice ------------


def test_conquering_zaun_warrens_opens_a_pending_choice_through_legal_actions():
    """MoveUnit into an open battlefield printing Zaun Warrens' effect —
    search.apply (not a direct conquer.py call) must leave the resulting
    state pending rather than resolving the discard on its own."""
    mover = make_unit(CHAFF, 1, exhausted=False)
    state = make_state(base_units=frozenset({mover}), hand=("hand-a", "hand-b"),
                        left_effect=ZAUN_WARRENS)
    cards = {}

    move = next(a for a in search.legal_actions(state, cards)
                if isinstance(a, MoveUnit) and a.instance_id == 1 and a.to_zone == "left")
    result = search.apply(state, move, cards)

    assert result.battlefields[0].controller == 0  # the move itself still landed
    assert result.pending_conquer_choice is not None
    assert result.pending_conquer_choice.kind == "battlefield"
    assert result.pending_conquer_choice.key == ZAUN_WARRENS

    # Nothing else is offered while pending — same gating as an open
    # showdown's mandatory attack trigger.
    pending_actions = search.legal_actions(result, cards)
    assert all(isinstance(a, ResolveConquerTrigger) for a in pending_actions)
    assert {a.params for a in pending_actions} == {("hand-a",), ("hand-b",)}


def test_resolving_the_discard_choice_moves_the_card_to_trash_and_clears_pending():
    mover = make_unit(CHAFF, 1, exhausted=False)
    state = make_state(base_units=frozenset({mover}), hand=("hand-a", "hand-b"),
                        left_effect=ZAUN_WARRENS)
    cards = {}
    move = next(a for a in search.legal_actions(state, cards)
                if isinstance(a, MoveUnit) and a.to_zone == "left")
    pending_state = search.apply(state, move, cards)

    choice = next(a for a in search.legal_actions(pending_state, cards) if a.params == ("hand-a",))
    result = search.apply(pending_state, choice, cards)

    assert result.pending_conquer_choice is None
    assert result.players[0].hand == ("hand-b",)
    assert result.players[0].trash == ("hand-a",)  # discard lands in trash, not the Main Deck


def test_zaun_warrens_against_an_empty_hand_resolves_immediately_no_dead_end():
    """A mandatory discard against zero cards must fizzle, not strand the
    line with no legal continuation — real Riftbound discards "as many as
    possible," and zero is a well-defined answer here."""
    mover = make_unit(CHAFF, 1, exhausted=False)
    state = make_state(base_units=frozenset({mover}), hand=(), left_effect=ZAUN_WARRENS)
    cards = {}
    move = next(a for a in search.legal_actions(state, cards)
                if isinstance(a, MoveUnit) and a.to_zone == "left")
    result = search.apply(state, move, cards)

    assert result.pending_conquer_choice is None  # resolved on the spot, no pending window
    assert result.players[0].hand == ()
    assert result.players[0].trash == ()


def test_zaun_warrens_is_reachable_through_a_full_solve():
    """End-to-end: a Final-Point conquest (rule 476 needs every battlefield
    Scored this turn) that must pass through the pending-choice machinery
    to be found at all, exercised via search.solve() rather than a
    hand-picked action sequence. "right" is seeded as already-Held so only
    "left" (Zaun Warrens) needs a fresh Conquer this turn."""
    mover = make_unit(CHAFF, 1, exhausted=False, might=1)
    state = make_state(base_units=frozenset({mover}), hand=("spare",),
                        left_effect=ZAUN_WARRENS, score=7,
                        right_ctrl=0, scored_this_turn=frozenset({"right"}))
    cards = {}
    strategy = search.solve(state, cards, max_depth=4)
    assert strategy is not None
    # Replay it and confirm it actually crosses the line, discard included.
    current = state
    for _ in range(len(strategy) + 1):
        if scoring.is_winning(current):
            break
        key = canonical_key(current)
        action = strategy[key]
        current = search.apply(current, action, cards)
    assert current.players[0].score >= 8
