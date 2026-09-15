from solver.author_puzzle_006 import BLITZCRANK_CARD, build_root
from solver.engine.abilities import BLITZCRANK_IMPASSIVE, resolve_unit_play_trigger_outcomes
from solver.engine.actions import PlayUnit, ResolveCombat
from solver.export import export_puzzle
from solver.search import legal_actions, solve

CARDS = {BLITZCRANK_IMPASSIVE: BLITZCRANK_CARD}


def test_puzzle_006_solves_by_redirecting_the_blocker():
    root = build_root()
    strategy = solve(root, CARDS, max_depth=4)
    assert strategy is not None
    actions = list(strategy.values())
    redirect_actions = [a for a in actions if isinstance(a, PlayUnit) and a.trigger_params]
    assert len(redirect_actions) == 1  # the winning line uses the redirect, not a decline
    assert redirect_actions[0].target_zone == "right"


def test_puzzle_006_redirect_empties_left():
    root = build_root()
    redirect_candidates = [
        a for a in legal_actions(root, CARDS)
        if isinstance(a, PlayUnit) and a.card_id == BLITZCRANK_IMPASSIVE and a.trigger_params
    ]
    assert redirect_candidates

    for action in redirect_candidates:
        outcomes = resolve_unit_play_trigger_outcomes(root, action, BLITZCRANK_CARD)
        for outcome in outcomes:
            left = outcome.battlefields[0]
            assert left.units == frozenset()  # blocker is gone (dead)
            assert left.controller is None  # "left" is open


def test_puzzle_006_is_unsolvable_without_tank():
    """The point of the re-authored puzzle, asserted directly.

    Dragging the blocker onto "right" makes it the Attacker and us the
    Defender, and its 3 damage would kill our 2-Might Rearguard — the only
    unit that can reach "left", since Blitzcrank enters exhausted the turn
    he's played. [Tank] forces that damage onto Blitzcrank, who at 5 Might
    survives it.

    Strip Tank from the same body and the identical line kills our own
    conqueror, so the puzzle stops having a solution at all. That margin
    IS the puzzle — which is what makes this version about Tank rather
    than merely compatible with it.
    """
    import dataclasses

    root = build_root()
    without_tank = {BLITZCRANK_IMPASSIVE: dataclasses.replace(
        BLITZCRANK_CARD, keywords=frozenset())}
    assert solve(root, CARDS, max_depth=4) is not None
    assert solve(root, without_tank, max_depth=4) is None


def test_puzzle_006_has_exactly_one_winning_line():
    from solver.search import count_winning_strategies

    assert count_winning_strategies(build_root(), CARDS, max_depth=4) == 1


def test_puzzle_006_direct_attack_on_the_blocker_is_not_the_solution():
    """Attacking the blocker head-on doesn't free "left" the way the
    redirect does — our attacker would have to fight through it there
    instead of walking into an empty battlefield, which is the trap this
    puzzle is built around."""
    root = build_root()
    strategy = solve(root, CARDS, max_depth=4)
    actions = list(strategy.values())
    assert not any(isinstance(a, ResolveCombat) and a.to_zone == "left" for a in actions)


def test_puzzle_006_exports_cleanly():
    """No adversarial edges, and that is now correct by design rather than
    a loss. The original version's fork — the opponent choosing whether to
    kill our fragile unit or Blitzcrank — was never legal Riftbound, since
    Blitzcrank prints [Tank]. This version gets its difficulty from Tank
    being load-bearing instead of from a fork that only existed because
    the keyword was unimplemented."""
    root = build_root()
    result = export_puzzle("puzzle-006-redirection", root, CARDS)
    assert "win" in result["terminal"].values()
    adversarial_edges = [
        e for edge_list in result["edges"].values() for e in edge_list if e["adversarial"]
    ]
    assert adversarial_edges == []
