"""Kai'Sa, Evolutionary — the UNIT-keyed counterpart to
test_conquer_choice.py's Zaun Warrens: "when I conquer, you may play a
spell from your trash with Energy cost less than your points, without
paying its Energy cost. Then recycle it. (Must still pay Power cost.)"

Reuses GameState.pending_conquer_choice/ResolveConquerTrigger (engine/
conquer.py) for the UNIT-keyed grammar instead of the BATTLEFIELD-keyed
one, and Soulgorger/Spectral Matron's trash-replay pattern aimed at a
spell (abilities.kaisa_evolutionary_candidates/_effect) instead of a
unit. Every reachability test goes through search.legal_actions/apply,
not a direct call into abilities.py — same reachability discipline as
every other cluster in this codebase.
"""

from solver import search
from solver.engine import scoring
from solver.engine.abilities import KAISA_EVOLUTIONARY, RIDE_THE_WIND
from solver.engine.actions import MoveUnit
from solver.engine.card_pool import card_def
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


def make_state(base_units=frozenset(), trash=(), score=0,
                left_units=frozenset(), left_ctrl=None,
                right_units=frozenset(), right_ctrl=None, runes=(),
                scored_this_turn=frozenset()):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=(), runes=RunePool(available=runes),
                        score=score, trash=trash),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", left_ctrl, left_units, None),
            BattlefieldState("right", right_ctrl, right_units, None),
        ),
        scored_this_turn=scored_this_turn,
        cards_played_this_turn=0,
    )


def _conquer_with_kaisa(score, runes=("Chaos",)):
    """Kai'Sa moves from base into the open "left" battlefield (a plain
    conquer, no combat), with a second friendly unit sitting at "right"
    for Ride The Wind (in trash) to have something of its own to move."""
    kaisa = make_unit(KAISA_EVOLUTIONARY, 1, exhausted=False)
    mover = make_unit(CHAFF, 2, controller=0, exhausted=False)
    state = make_state(base_units=frozenset({kaisa}), right_units=frozenset({mover}),
                        right_ctrl=0, trash=(RIDE_THE_WIND,), score=score, runes=runes)
    cards = {RIDE_THE_WIND: card_def(RIDE_THE_WIND)}
    move = next(a for a in search.legal_actions(state, cards)
                if isinstance(a, MoveUnit) and a.instance_id == 1 and a.to_zone == "left")
    return search.apply(state, move, cards), cards


def test_conquering_with_kaisa_opens_a_pending_choice_through_legal_actions():
    pending_state, cards = _conquer_with_kaisa(score=3)

    assert pending_state.pending_conquer_choice is not None
    assert pending_state.pending_conquer_choice.kind == "unit"
    assert pending_state.pending_conquer_choice.key == KAISA_EVOLUTIONARY

    candidates = search.legal_actions(pending_state, cards)
    assert any(a.params == () for a in candidates), "declining must stay legal (\"you may\")"
    # Ride The Wind can move EITHER friendly unit now on the board (Kai'Sa
    # herself included) to several destinations, so several replay
    # candidates are legal — the one that matters here is moving the
    # OTHER unit (instance_id 2) from "right" to "base".
    matches = [a for a in candidates
               if a.params and a.params[0] == RIDE_THE_WIND and a.params[1] == (2, "base")]
    assert len(matches) == 1
    card_id, spell_params, payment = matches[0].params
    assert card_id == RIDE_THE_WIND
    assert spell_params == (2, "base")


def test_declining_kaisa_leaves_the_trash_spell_untouched():
    pending_state, cards = _conquer_with_kaisa(score=3)
    decline = next(a for a in search.legal_actions(pending_state, cards) if a.params == ())
    result = search.apply(pending_state, decline, cards)

    assert result.pending_conquer_choice is None
    assert result.players[0].trash == (RIDE_THE_WIND,)  # still there
    assert result.players[0].base_units == frozenset()  # Kai'Sa is the one who moved
    mover_now = next(u for u in result.battlefields[1].units if u.instance_id == 2)
    assert mover_now.card_id == CHAFF and mover_now.exhausted is False  # never touched


def test_resolving_kaisa_replays_the_spell_and_recycles_it_out_of_trash():
    pending_state, cards = _conquer_with_kaisa(score=3)
    replay = next(a for a in search.legal_actions(pending_state, cards)
                  if a.params and a.params[0] == RIDE_THE_WIND and a.params[1] == (2, "base"))
    result = search.apply(pending_state, replay, cards)

    assert result.pending_conquer_choice is None
    assert RIDE_THE_WIND not in result.players[0].trash  # recycled, not left behind
    # Ride The Wind's own effect: mover relocated (2 -> base) and readied.
    assert not any(u.instance_id == 2 for u in result.battlefields[1].units)
    moved = next(u for u in result.players[0].base_units if u.instance_id == 2)
    assert moved.exhausted is False
    # Its Chaos Power was actually spent (Energy is waived, Power is not).
    assert result.players[0].runes.power_spent == ("Chaos",)


def test_kaisa_ineligible_when_energy_cost_is_not_below_score():
    """Ride The Wind costs 2 Energy. Kai'Sa's own conquest grants a point
    first (score reaches 2 by the time the trigger checks it, since
    scoring.resolve_control_change fires it after resolve_conquer), and 2
    is not STRICTLY less than 2 — so it must not be offered at all."""
    pending_state, cards = _conquer_with_kaisa(score=1)
    candidates = search.legal_actions(pending_state, cards)
    assert [a.params for a in candidates] == [()]  # decline is the only option


def test_kaisa_reachable_through_a_full_solve():
    """End-to-end via search.solve(): Kai'Sa's own conquest reaches
    Victory Score outright, so the choice-bearing trigger fires on the
    very last action of the line — declining it (trigger_params == ())
    must still be a legal way to finish, exercised through solve() rather
    than a hand-picked action."""
    kaisa = make_unit(KAISA_EVOLUTIONARY, 1, exhausted=False)
    state = make_state(base_units=frozenset({kaisa}), score=7,
                        right_ctrl=0, scored_this_turn=frozenset({"right"}))
    cards = {}
    strategy = search.solve(state, cards, max_depth=2)
    assert strategy is not None

    current = state
    for _ in range(len(strategy) + 1):
        if scoring.is_winning(current):
            break
        action = strategy[canonical_key(current)]
        current = search.apply(current, action, cards)
    assert current.players[0].score >= 8
