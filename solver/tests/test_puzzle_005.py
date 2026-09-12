from solver.author_puzzle_005 import build_root
from solver.engine.abilities import CAITLYN_PATROLLING
from solver.engine.actions import ActivateAbility, ResolveCombat
from solver.engine.scoring import is_winning
from solver.export import export_puzzle
from solver.search import apply, legal_actions, solve


def test_puzzle_005_solves_in_two_actions():
    root = build_root()
    strategy = solve(root, cards={}, max_depth=4)
    assert strategy is not None
    assert len(strategy) == 2
    actions = list(strategy.values())
    assert any(isinstance(a, ActivateAbility) for a in actions)
    assert any(a.to_zone == "right" for a in actions if hasattr(a, "to_zone"))


def test_puzzle_005_the_trap_direct_attack_cannot_win():
    """The whole point: attacking the tough defender directly (Might 3 vs
    our Might 2) loses our attacker for nothing and leaves 'right'
    uncontested — no path to 8 remains from there.
    """
    root = build_root()
    attacker = next(iter(root.players[0].base_units))
    resolve_combat_actions = [
        a for a in legal_actions(root, {})
        if isinstance(a, ResolveCombat) and a.instance_id == attacker.instance_id
    ]
    assert len(resolve_combat_actions) == 1  # single defender, no real assignment choice
    action = resolve_combat_actions[0]

    from solver.search import _resolve_combat_search
    result = _resolve_combat_search(root, action, remaining=3, cards={}, ttable={})
    assert result is None  # no winning continuation after the bad trade


def test_puzzle_005_caitlyn_clears_the_way_and_wins():
    root = build_root()
    caitlyn = next(iter(root.battlefields[0].units))
    defender = next(iter(root.battlefields[1].units))

    ability_action = ActivateAbility(source_id=caitlyn.instance_id, ability_id=CAITLYN_PATROLLING,
                                      params=(defender.instance_id,), rune_payment=None)
    state = apply(root, ability_action, {})
    assert state.battlefields[1].controller is None  # defender dead, "right" now open
    assert not is_winning(state)

    attacker = next(iter(state.players[0].base_units))
    from solver.engine.actions import MoveUnit
    state = apply(state, MoveUnit(instance_id=attacker.instance_id, from_zone="base", to_zone="right"), {})
    assert is_winning(state)
    assert state.players[0].score == 8


def test_puzzle_005_exports_cleanly():
    root = build_root()
    result = export_puzzle("puzzle-005-clear-the-way", root, cards={})
    assert len(result["solution"]) == 2
    assert "win" in result["terminal"].values()
    assert "dead_end" in result["terminal"].values()  # the direct-attack trap is a real dead end
