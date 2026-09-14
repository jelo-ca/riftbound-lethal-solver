"""Puzzle 7 "Feint": a fight entered only to be abandoned.

Yasuo is stranded on "left" under Vilemaw's Lair, which denies his exit
to base for spell-granted moves as well as Standard Moves. "left" was
already Scored this turn by Hold, so re-taking it is worth nothing and
the only point on the board is his own move trigger — which needs three
moves. The middle one is bought by attacking "right" and escaping the
showdown before damage.
"""

import dataclasses

from solver.author_puzzle_007 import build_root
from solver.engine import scoring
from solver.engine.abilities import RIDE_THE_WIND, YASUO_WINDRIDER
from solver.engine.actions import EnterShowdown, MoveUnit, PlaySpell, ResolveShowdown
from solver.engine.card_pool import CARD_POOL, LEGION_REARGUARD
from solver.export import export_puzzle, resolve_action_outcomes
from solver.engine.state import canonical_key
from solver.search import solve

CARDS = {cid: CARD_POOL[cid] for cid in (RIDE_THE_WIND, YASUO_WINDRIDER, LEGION_REARGUARD)}
MAX_DEPTH = 8


def walk(root, strategy):
    """The states along the recommended line, root first."""
    states, state = [root], root
    while canonical_key(state) in strategy:
        state = resolve_action_outcomes(state, strategy[canonical_key(state)], CARDS)[0]
        states.append(state)
    return states


def test_puzzle_007_root_satisfies_the_hold_invariant():
    """We control "left", so Hold Scored it during the Beginning Phase and
    it must be seeded. Getting this wrong is what got the first puzzles 7
    and 8 withdrawn — both let a unit walk off ground it controlled and
    back on for a second point."""
    root = build_root()
    assert scoring.unseeded_holds(root) == frozenset()
    assert root.scored_this_turn == frozenset({"left"})
    assert root.players[0].score == 7


def test_puzzle_007_solves_by_entering_a_showdown_and_leaving_it():
    root = build_root()
    strategy = solve(root, CARDS, max_depth=MAX_DEPTH)
    assert strategy is not None
    types = [type(a) for a in strategy.values()]
    assert EnterShowdown in types
    assert ResolveShowdown in types
    assert PlaySpell in types


def test_puzzle_007_scores_only_on_the_move_trigger():
    """The point of the reframing. Re-taking "left" is worth nothing —
    it was Scored this turn already — so the score sits at 7 through the
    whole line and moves to 8 only on Yasuo's third move. A solver that
    thought the Conquer paid would win a move early."""
    root = build_root()
    strategy = solve(root, CARDS, max_depth=MAX_DEPTH)
    scores = [s.players[0].score for s in walk(root, strategy)]
    assert scores == [7, 7, 7, 7, 8]


def test_puzzle_007_final_move_is_yasuos_third():
    root = build_root()
    strategy = solve(root, CARDS, max_depth=MAX_DEPTH)
    final = walk(root, strategy)[-1]
    left = next(bf for bf in final.battlefields if bf.battlefield_id == "left")
    yasuo = next(u for u in left.units if u.card_id == YASUO_WINDRIDER)
    assert yasuo.moved_this_turn == 3


def test_puzzle_007_escapes_before_damage_so_the_guard_survives():
    """The feint: the showdown resolves with no attacker, so the Might-4
    guard takes nothing and keeps "right". Nothing dies in this puzzle."""
    root = build_root()
    strategy = solve(root, CARDS, max_depth=MAX_DEPTH)
    final = walk(root, strategy)[-1]
    right = next(bf for bf in final.battlefields if bf.battlefield_id == "right")
    assert right.controller == 1
    assert [u.damage for u in right.units] == [0]


def test_puzzle_007_needs_vilemaws_lair_or_it_collapses_to_puzzle_3():
    """Without the battlefield effect Yasuo can just walk off "left" and
    be pulled back, which is puzzle 3's three-step trick. The effect is
    the entire reason the showdown detour is forced."""
    root = build_root()
    full = solve(root, CARDS, max_depth=MAX_DEPTH)

    battlefields = list(root.battlefields)
    battlefields[0] = dataclasses.replace(battlefields[0], effect_id=None)
    without = solve(dataclasses.replace(root, battlefields=tuple(battlefields)),
                    CARDS, max_depth=MAX_DEPTH)

    assert without is not None
    assert len(without) < len(full)
    assert not any(isinstance(a, EnterShowdown) for a in without.values())
    assert all(isinstance(a, (MoveUnit, PlaySpell)) for a in without.values())


def test_puzzle_007_ride_the_wind_is_affordable_exactly_once():
    """It is both the escape and the middle move, so there is no spare
    tempo anywhere in the line."""
    root = build_root()
    assert root.players[0].hand == (RIDE_THE_WIND,)
    assert sorted(root.players[0].runes.available) == ["Chaos", "Fury", "Fury"]
    assert solve(root, CARDS, max_depth=MAX_DEPTH) is not None
    stripped = dataclasses.replace(
        root, players=(dataclasses.replace(root.players[0], hand=()), root.players[1]))
    assert solve(stripped, CARDS, max_depth=MAX_DEPTH) is None


def test_puzzle_007_exports_cleanly():
    root = build_root()
    result = export_puzzle("puzzle-007-feint", root, CARDS)
    assert "win" in result["terminal"].values()
    assert len(result["solution"]) == 4
