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


def test_puzzle_006_redirect_empties_left_regardless_of_opponent_choice():
    """The whole lesson: no matter which of our two units at "right" the
    opponent's redirected blocker targets, "left" ends up open and our
    separate attacker can still win. This is the AND-node's job, proven
    here through a real authored puzzle rather than a synthetic scenario.
    """
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
            assert left.units == frozenset()  # blocker is gone (dead) either way
            assert left.controller is None  # "left" is open


def test_puzzle_006_direct_attack_on_the_blocker_is_not_the_solution():
    """Attacking the blocker head-on doesn't free "left" the way the
    redirect does — our attacker would have to fight through it there
    instead of walking into an empty battlefield, which is the trap this
    puzzle is built around."""
    root = build_root()
    strategy = solve(root, CARDS, max_depth=4)
    actions = list(strategy.values())
    assert not any(isinstance(a, ResolveCombat) and a.to_zone == "left" for a in actions)


def test_puzzle_006_lost_its_adversarial_edge_when_tank_was_implemented():
    """DESIGN INVALIDATED — this puzzle needs re-authoring or withdrawing.

    Puzzle 6 "Redirection" was built around one thing: redirecting an
    enemy onto ground we hold creates a genuine adversarial fork, because
    the enemy chooses whether to kill our fragile ally or our Blitzcrank.
    This test asserted that fork existed, and passed for as long as the
    engine ignored [Tank].

    Blitzcrank prints [Tank] — "I must be assigned combat damage first" —
    so the enemy never actually had that choice. The fork was an artifact
    of the missing rule, and implementing Tank correctly deletes it. The
    puzzle still solves, but it no longer demonstrates what its own design
    docstring says it demonstrates.

    Asserting the collapse rather than deleting the test, so the loss
    can't be mistaken for a puzzle that was always this way. Precedent:
    puzzles 7 and 8 were withdrawn when the Hold invariant was enforced.
    """
    root = build_root()
    result = export_puzzle("puzzle-006-redirection", root, CARDS)
    assert "win" in result["terminal"].values()  # still solvable
    adversarial_edges = [
        e for edge_list in result["edges"].values() for e in edge_list if e["adversarial"]
    ]
    assert adversarial_edges == []
