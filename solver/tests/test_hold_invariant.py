"""The Hold invariant: mid-turn, every battlefield the turn player
controls has already scored for them this turn.

Held since the start of the turn means a Hold point in the Beginning
Phase; taken during the turn means a Conquer point. There is no third
way to be standing on a battlefield, and rule 471.1.b allows one point
per battlefield per player per turn — so control implies spent.

What it rules out is the revolving door: walk your last unit off a
battlefield you control (rule 468 makes it Uncontrolled), walk another
unit back in, and collect a second Conquer point on ground you never
lost. The scoring code already refused that when `scored_this_turn` was
seeded correctly, but nothing enforced the seeding, so both the
generator and two hand-authored puzzles produced positions where it
worked. Those puzzles (7 and 8) were withdrawn.
"""

import dataclasses

import pytest

from solver.engine import scoring
from solver.engine.actions import MoveUnit
from solver.engine.card_pool import CARD_POOL, LEGION_REARGUARD
from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    UnitInstance,
)
from solver.export import export_puzzle
from solver.generate import sample_position
from solver.search import apply

import random


def make_unit(instance_id, controller=0, might=2):
    return UnitInstance(card_id=LEGION_REARGUARD, instance_id=instance_id,
                         controller=controller, might=might, keywords=frozenset(),
                         exhausted=False, damage=0, is_token=False)


def make_state(left_ctrl=None, left_units=frozenset(), right_ctrl=None,
                right_units=frozenset(), base_units=frozenset(), score=6,
                scored_this_turn=frozenset()):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=(), runes=RunePool(available=()), score=score),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", left_ctrl, left_units, None),
            BattlefieldState("right", right_ctrl, right_units, None),
        ),
        scored_this_turn=scored_this_turn,
        cards_played_this_turn=0,
    )


# --- the invariant itself ---


def test_a_controlled_battlefield_missing_from_scored_this_turn_is_a_violation():
    state = make_state(left_ctrl=0, left_units=frozenset({make_unit(1)}))
    assert scoring.unseeded_holds(state) == frozenset({"left"})


def test_seeding_the_held_battlefield_satisfies_the_invariant():
    state = make_state(left_ctrl=0, left_units=frozenset({make_unit(1)}),
                        scored_this_turn=frozenset({"left"}))
    assert scoring.unseeded_holds(state) == frozenset()


def test_the_invariant_is_one_directional():
    """`scored_this_turn` may name battlefields we don't control — one
    conquered earlier this turn and since lost stays scored (rule
    471.1.b; puzzle 4 is built on that shape). Only the other direction
    is a violation."""
    state = make_state(right_ctrl=1, right_units=frozenset({make_unit(2, controller=1)}),
                        scored_this_turn=frozenset({"right"}))
    assert scoring.unseeded_holds(state) == frozenset()


def test_an_enemy_held_battlefield_is_not_ours_to_seed():
    state = make_state(left_ctrl=1, left_units=frozenset({make_unit(1, controller=1)}))
    assert scoring.unseeded_holds(state) == frozenset()


# --- the behaviour it exists to prevent ---


def test_the_revolving_door_scores_nothing_on_a_well_formed_position():
    """Walk our last unit off "left" (it goes Uncontrolled, rule 468),
    then walk another in. With the Hold correctly seeded, re-taking it
    scores nothing — this is the exact two-move line puzzles 7 and 8 were
    built on."""
    holder, spare = make_unit(1), make_unit(2)
    state = make_state(left_ctrl=0, left_units=frozenset({holder}),
                        base_units=frozenset({spare}),
                        scored_this_turn=frozenset({"left"}))
    cards = {LEGION_REARGUARD: CARD_POOL[LEGION_REARGUARD]}

    vacated = apply(state, MoveUnit(instance_id=1, from_zone="left", to_zone="base"), cards)
    assert vacated.battlefields[0].controller is None  # rule 468
    assert vacated.players[0].score == 6

    retaken = apply(vacated, MoveUnit(instance_id=2, from_zone="base", to_zone="left"), cards)
    assert retaken.battlefields[0].controller == 0
    assert retaken.players[0].score == 6  # no second point for the same battlefield


# --- enforcement at the boundary ---


def test_export_refuses_a_position_that_violates_the_invariant():
    """export_puzzle is the one gate every puzzle passes through, hand
    authored or generated, so the invariant is checked there rather than
    left to each author script's discretion — which is how puzzles 7 and
    8 shipped broken."""
    state = make_state(left_ctrl=0, left_units=frozenset({make_unit(1)}),
                        base_units=frozenset({make_unit(2)}))
    with pytest.raises(ValueError, match="scored_this_turn"):
        export_puzzle("violating", state, {LEGION_REARGUARD: CARD_POOL[LEGION_REARGUARD]})


# --- the generator cannot mint a violating position ---


@pytest.mark.parametrize("seed", range(150))
def test_sampled_positions_always_satisfy_the_invariant(seed):
    root, _ = sample_position(random.Random(seed))
    assert scoring.unseeded_holds(root) == frozenset()


def test_the_sampler_still_produces_conquered_then_lost_battlefields():
    """The half of scored_this_turn that ISN'T forced by the board — a
    battlefield conquered earlier this turn and since lost — has to stay
    reachable, or puzzle 4's shape becomes ungeneratable."""
    seen = False
    for seed in range(300):
        root, _ = sample_position(random.Random(seed))
        held = scoring.held_battlefields(root)
        if root.scored_this_turn - held:
            seen = True
            break
    assert seen, "sampler never produced a scored-but-not-held battlefield"
