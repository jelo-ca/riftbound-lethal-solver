from solver import search
from solver.engine import combat
from solver.engine.actions import ResolveCombat
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance


def make_unit(instance_id, controller=0, might=3, keywords=frozenset(), damage=0, exhausted=False):
    return UnitInstance(
        card_id="u", instance_id=instance_id, controller=controller, might=might,
        keywords=keywords, exhausted=exhausted, damage=damage, is_token=False,
    )


# --- unit_combat_might: Assault/Shield bonuses ---


def test_might_no_keywords_is_base_might():
    unit = make_unit(1, might=3)
    assert combat.unit_combat_might(unit, "attacker") == 3
    assert combat.unit_combat_might(unit, "defender") == 3


def test_assault_bonus_only_while_attacking():
    unit = make_unit(1, might=3, keywords=frozenset({"Assault"}))
    assert combat.unit_combat_might(unit, "attacker") == 4
    assert combat.unit_combat_might(unit, "defender") == 3


def test_assault_numbered_bonus():
    unit = make_unit(1, might=3, keywords=frozenset({"Assault 2"}))
    assert combat.unit_combat_might(unit, "attacker") == 5


def test_shield_bonus_only_while_defending():
    unit = make_unit(1, might=3, keywords=frozenset({"Shield 2"}))
    assert combat.unit_combat_might(unit, "defender") == 5
    assert combat.unit_combat_might(unit, "attacker") == 3


# --- enumerate_assignments: lethal-first rule ---


def test_enumerate_single_target_partial_hit():
    target = make_unit(1, might=3)
    options = combat.enumerate_assignments(frozenset({target}), pool=2)
    assert options == [((1, 2),)]


def test_enumerate_lethal_first_pdf_example():
    # rule 465.2.c's own example: 5 damage across four 3-Might units must
    # fully lethal one (3) before a second can be touched at all, which
    # then takes the remainder (2) - never spread 3 ways. A "stop after
    # the first lethal hit" option is also valid (the leftover 2 is free
    # overkill, doesn't change who dies - see design/09-combat-resolution.md),
    # so options may total less than the full pool; what must never happen
    # is more than one unit receiving a non-lethal (<3) amount.
    targets = frozenset({make_unit(i, might=3) for i in range(1, 5)})
    options = combat.enumerate_assignments(targets, pool=5)
    assert options  # at least one valid way to assign
    for option in options:
        total = sum(amount for _, amount in option)
        assert total <= 5
        partial_hits = [amount for _, amount in option if 0 < amount < 3]
        assert len(partial_hits) <= 1  # at most one unit ever gets less than lethal


def test_enumerate_death_sets_pool_kills_exactly_one_of_two():
    u1, u2 = make_unit(1, might=3), make_unit(2, might=3)
    options = combat.enumerate_assignments(frozenset({u1, u2}), pool=3)
    death_sets = set()
    for option in options:
        dead = frozenset(uid for uid, amt in option if amt >= 3)
        death_sets.add(dead)
    assert death_sets == {frozenset({1}), frozenset({2})}  # exactly one dies, attacker's choice


def test_enumerate_zero_pool_is_noop():
    target = make_unit(1, might=3)
    assert combat.enumerate_assignments(frozenset({target}), pool=0) == [()]


def test_enumerate_empty_targets():
    assert combat.enumerate_assignments(frozenset(), pool=5) == [()]


# --- apply_combat: deterministic outcomes ---


def make_combat_state(defenders, mover):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset({mover}), hand=(), runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 1, defenders, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def test_apply_combat_attacker_wins():
    defender = make_unit(1, controller=1, might=2)
    mover = make_unit(2, controller=0, might=3)
    state = make_combat_state(frozenset({defender}), mover)
    result = combat.apply_combat(state, mover, "base", "left",
                                  attacker_assignment=((1, 2),), defender_assignment=())
    left = result.battlefields[0]
    assert left.controller == 0  # attacker took it
    assert len(left.units) == 1
    assert next(iter(left.units)).instance_id == 2


def test_apply_combat_attacker_dies():
    defender = make_unit(1, controller=1, might=3)
    mover = make_unit(2, controller=0, might=2)
    state = make_combat_state(frozenset({defender}), mover)
    result = combat.apply_combat(state, mover, "base", "left",
                                  attacker_assignment=(), defender_assignment=((2, 3),))
    left = result.battlefields[0]
    assert left.controller == 1  # defender retains
    assert next(iter(left.units)).instance_id == 1


def test_apply_combat_both_survive_stays_contested():
    defender = make_unit(1, controller=1, might=5)
    mover = make_unit(2, controller=0, might=5)
    state = make_combat_state(frozenset({defender}), mover)
    result = combat.apply_combat(state, mover, "base", "left",
                                  attacker_assignment=((1, 2),), defender_assignment=((2, 2),))
    left = result.battlefields[0]
    assert left.controller is None  # rule 190.6: stays Contested/uncontrolled
    assert len(left.units) == 2


def test_apply_combat_survivors_heal_fully():
    # Both sides take non-lethal damage and survive; damage must clear
    # once this combat resolves, not persist to the next one.
    defender = make_unit(1, controller=1, might=5)
    mover = make_unit(2, controller=0, might=5, damage=3)  # pre-existing damage from an earlier combat
    state = make_combat_state(frozenset({defender}), mover)
    result = combat.apply_combat(state, mover, "base", "left",
                                  attacker_assignment=((1, 2),), defender_assignment=((2, 1),))
    left = result.battlefields[0]
    assert {u.instance_id: u.damage for u in left.units} == {1: 0, 2: 0}


def test_apply_combat_exhausted_after_flag():
    defender = make_unit(1, controller=1, might=1)
    mover = make_unit(2, controller=0, might=3)
    state = make_combat_state(frozenset({defender}), mover)
    result = combat.apply_combat(state, mover, "base", "left",
                                  attacker_assignment=((1, 1),), defender_assignment=(),
                                  exhausted_after=False)
    moved = next(iter(result.battlefields[0].units))
    assert moved.exhausted is False


# --- The AND-node itself: proof the mechanism actually enforces adversarial correctness ---


def test_and_node_rejects_when_opponent_can_deny_the_win():
    """Synthetic scenario (bypasses legal_actions()/is_legal_resolve_combat
    — spell-triggered 'we are defender' combat generation isn't wired up
    yet, see actions.ResolveCombat's docstring): a genuine 2-unit opponent
    choice where picking the WRONG branch (from our perspective) denies
    the win. This is the case the whole AND-node exists for — a naive "OR"
    implementation would incorrectly accept this move by only checking one
    branch.

    Setup: we already hold "left" (2 defenders) and Scored it via Hold
    this turn. The opponent attacks with one unit; we kill it regardless
    of which defender they target. One defender (Ganking) can reach the
    open "right" in one hop to win the Final Point; the other needs two
    hops (left->base->right). With only 1 action of budget left after
    combat, the opponent can deny the win by killing the Ganking unit.
    """
    ganking_defender = make_unit(1, might=3, keywords=frozenset({"Ganking"}))
    plain_defender = make_unit(2, might=3)
    mover = make_unit(3, controller=1, might=3)

    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset({mover}), hand=(), runes=RunePool(available=()), score=7),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, frozenset({ganking_defender, plain_defender}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset({"left"}),  # Held this turn, pre-resolved
        cards_played_this_turn=0,
    )

    our_assignment = ((mover.instance_id, 3),)  # kill the attacker
    action = ResolveCombat(instance_id=mover.instance_id, from_zone="base", to_zone="left",
                            our_assignment=our_assignment)

    # 1 for the combat action + 1 for a follow-up: enough for the Ganking
    # survivor's 1-hop win, NOT enough for the plain survivor's 2-hop win.
    result = search._resolve_combat_search(root, action, remaining=2, cards={}, ttable={})
    assert result is None  # the opponent kills the Ganking defender and denies the win


def test_and_node_accepts_when_every_opponent_response_still_wins():
    """Same shape, but both defenders have Ganking this time — a Standard
    Move always exhausts its unit (rule 145.1), so a 2-hop relay
    (left->base->right) is never legal in one turn regardless of Ganking;
    the only way for EITHER survivor to reach "right" is a direct 1-hop,
    which needs Ganking on both. With both possible opponent choices now
    leaving a winning 1-hop survivor, the AND-node should validate this
    action and return a strategy covering both branches.
    """
    defender_a = make_unit(1, might=3, keywords=frozenset({"Ganking"}))
    defender_b = make_unit(2, might=3, keywords=frozenset({"Ganking"}))
    mover = make_unit(3, controller=1, might=3)

    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset({mover}), hand=(), runes=RunePool(available=()), score=7),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, frozenset({defender_a, defender_b}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset({"left"}),
        cards_played_this_turn=0,
    )

    our_assignment = ((mover.instance_id, 3),)
    action = ResolveCombat(instance_id=mover.instance_id, from_zone="base", to_zone="left",
                            our_assignment=our_assignment)

    result = search._resolve_combat_search(root, action, remaining=2, cards={}, ttable={})
    assert result is not None
    # defender_a and defender_b are identical apart from instance_id, which
    # canonical_key excludes by design (design/02-state-model.md) - so both
    # opponent branches correctly collapse to the same board state. Still
    # proves the AND-node checked and accepted both branches (root's action
    # plus the one shared post-branch follow-up).
    assert len(result) >= 2
