"""Puzzle 7 "Feint": a fight entered only to be abandoned.

Yasuo needs three moves for his trigger. Vilemaw's Lair denies the
obvious route (puzzle 3's walk-in / Ride The Wind back / walk-in again),
because its restriction binds spell-granted moves too. So the middle
move has to be bought by attacking the one other battlefield and
escaping the showdown before damage.
"""

import dataclasses

from solver.author_puzzle_007 import build_root
from solver.engine import scoring
from solver.engine.abilities import RIDE_THE_WIND, YASUO_WINDRIDER
from solver.engine.actions import EnterShowdown, MoveUnit, PlaySpell, ResolveShowdown
from solver.engine.card_pool import CARD_POOL, FAITHFUL_MANUFACTOR, VANGUARD_CAPTAIN
from solver.export import export_puzzle
from solver.search import solve

CARDS = {cid: CARD_POOL[cid] for cid in
         (RIDE_THE_WIND, YASUO_WINDRIDER, FAITHFUL_MANUFACTOR, VANGUARD_CAPTAIN)}
MAX_DEPTH = 6


def test_puzzle_007_root_satisfies_the_hold_invariant():
    """We control nothing at the root, so nothing is pre-seeded. Puzzles 7
    and 8 were previously withdrawn for getting this wrong."""
    root = build_root()
    assert scoring.unseeded_holds(root) == frozenset()
    assert root.scored_this_turn == frozenset()


def test_puzzle_007_solves_by_entering_a_showdown_and_leaving_it():
    root = build_root()
    strategy = solve(root, CARDS, max_depth=MAX_DEPTH)
    assert strategy is not None
    types = [type(a) for a in strategy.values()]
    assert EnterShowdown in types
    assert ResolveShowdown in types
    assert PlaySpell in types


def test_puzzle_007_escapes_before_damage_so_the_guard_survives():
    """The feint: the showdown resolves with no attacker, so the Might-4
    guard takes nothing and keeps "right". Winning by killing it is not
    what happens here."""
    root = build_root()
    result = export_puzzle("puzzle-007-feint", root, CARDS)
    win_hashes = [h for h, kind in result["terminal"].items() if kind == "win"]
    assert win_hashes
    for h in win_hashes:
        right = next(bf for bf in result["nodes"][h]["battlefields"]
                      if bf["battlefield_id"] == "right")
        if right["controller"] == 1:
            assert [u["damage"] for u in right["units"]] == [0]
            break
    else:
        raise AssertionError("expected a win where the opponent still holds 'right'")


def test_puzzle_007_needs_vilemaws_lair_or_it_collapses_to_puzzle_3():
    """Without the battlefield effect there is a strictly shorter line —
    walk in, Ride The Wind back to base, walk in again — which is puzzle
    3's trick. The effect is the entire reason the showdown detour is
    forced."""
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
    """It is both the escape and the middle move; a second copy would open
    other lines entirely."""
    root = build_root()
    assert root.players[0].hand == (RIDE_THE_WIND,)
    assert sorted(root.players[0].runes.available) == ["Chaos", "Fury", "Fury"]
