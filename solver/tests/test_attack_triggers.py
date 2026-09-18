""""When I attack" triggers (coverage.py's ATTACK_TRIGGERS cluster).

RULES ANSWER (project owner, 2026-09-17): if an attack trigger kills the
defender before the Combat Damage Step, that defender is removed from
combat entirely and deals no combat damage. These tests exist to prove the
restructuring that makes that true — that combat.showdown_assignment_
options (and therefore resolve_showdown) only ever sees units still
actually standing at the battlefield, never the pre-trigger list — rather
than just exercising the individual card effects in isolation.
"""

import dataclasses

from solver import search
from solver.engine import abilities, combat
from solver.engine.abilities import (
    ANIVIA_PRIMAL,
    CRACKSHOT_CORSAIR,
    DUNE_DRAKE,
    YASUO_REMORSEFUL,
)
from solver.engine.actions import EnterShowdown, ResolveAttackTrigger, ResolveCombat
from solver.engine.card_pool import card_def
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance

YASUO_CARD = card_def(YASUO_REMORSEFUL)
ANIVIA_CARD = card_def(ANIVIA_PRIMAL)


def make_filler(instance_id, controller=1, might=3, exhausted=False, damage=0):
    """A plain enemy body with no registered mechanics of its own — only
    the ATTACKER's card_id needs to be real for these tests."""
    return UnitInstance(card_id="u", instance_id=instance_id, controller=controller, might=might,
                         keywords=frozenset(), exhausted=exhausted, damage=damage, is_token=False)


def make_attacker(card_id, instance_id, might, controller=0, exhausted=False):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller, might=might,
                         keywords=frozenset(), exhausted=exhausted, damage=0, is_token=False)


def make_state(base_units=frozenset(), left_units=frozenset(), left_ctrl=None, showdown=None):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=(), runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", left_ctrl, left_units, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
        showdown=showdown,
    )


# --- forcing the showdown, and withholding the atomic path ---


def test_attack_trigger_card_never_gets_an_atomic_resolve_combat():
    """Rule Answer 1: the atomic ResolveCombat path is built from the
    PRE-trigger defender list, which is unsafe the moment a registered
    trigger could kill one of those defenders first. A mover with an
    entry in ATTACK_TRIGGERS must always go through EnterShowdown instead
    — even with no [Action]/[Reaction] card in hand, unlike every other
    combat-triggering move."""
    yasuo = make_attacker(YASUO_REMORSEFUL, 1, might=6)
    enemy = make_filler(2, might=3)
    state = make_state(base_units=frozenset({yasuo}), left_units=frozenset({enemy}), left_ctrl=1)
    actions = search.legal_actions(state, {YASUO_REMORSEFUL: YASUO_CARD})
    assert any(isinstance(a, EnterShowdown) for a in actions)
    assert not any(isinstance(a, ResolveCombat) for a in actions)


def test_entering_the_showdown_leaves_the_trigger_pending():
    yasuo = make_attacker(YASUO_REMORSEFUL, 1, might=6)
    enemy = make_filler(2, might=3)
    state = make_state(base_units=frozenset({yasuo}), left_units=frozenset({enemy}), left_ctrl=1)
    entered = search.apply(state, EnterShowdown(instance_id=1, from_zone="base", to_zone="left"),
                            {YASUO_REMORSEFUL: YASUO_CARD})
    assert entered.showdown is not None
    assert entered.showdown.attack_trigger_resolved is False


def test_pending_trigger_is_the_only_legal_action_in_the_showdown():
    """No spell, no ResolveShowdown — nothing else is legal until the
    mandatory trigger has fired."""
    yasuo = make_attacker(YASUO_REMORSEFUL, 1, might=6)
    enemy = make_filler(2, might=3)
    state = combat.open_showdown(
        make_state(base_units=frozenset({yasuo}), left_units=frozenset({enemy}), left_ctrl=1),
        yasuo, "base", "left", has_pending_trigger=True,
    )
    actions = search.legal_actions(state, {YASUO_REMORSEFUL: YASUO_CARD})
    assert actions and all(isinstance(a, ResolveAttackTrigger) for a in actions)
    assert actions == [ResolveAttackTrigger(instance_id=1, trigger_params=(2,))]


# --- the core rule: a defender killed by the trigger deals zero damage ---


def test_defender_killed_by_attack_trigger_deals_zero_combat_damage():
    """Yasuo, Remorseful (Might 6) attacks a Might-6 defender. His trigger
    ("deal damage equal to my Might to an enemy unit here") deals exactly
    6 — enough to kill it (rule: lethal damage is non-zero damage >= Might)
    — BEFORE the Combat Damage Step. If the engine incorrectly still let
    that dead defender contribute its own Might-6 to the damage-assignment
    pool, Yasuo (Might 6) would take 6 back and die too: a mutual kill.
    The correct rule removes the defender from combat entirely once it
    dies to the trigger, so it deals 0 combat damage and Yasuo survives
    untouched.
    """
    yasuo = make_attacker(YASUO_REMORSEFUL, 1, might=6)
    defender = make_filler(2, might=6)
    state = make_state(base_units=frozenset({yasuo}), left_units=frozenset({defender}), left_ctrl=1)

    entered = combat.open_showdown(state, yasuo, "base", "left", has_pending_trigger=True)
    assert entered.showdown.attack_trigger_resolved is False

    trigger_action = ResolveAttackTrigger(instance_id=1, trigger_params=(2,))
    assert abilities.is_legal_resolve_attack_trigger(entered, trigger_action)
    after_trigger = abilities.apply_attack_trigger(entered, trigger_action)

    left = next(bf for bf in after_trigger.battlefields if bf.battlefield_id == "left")
    assert {u.instance_id for u in left.units} == {1}  # the defender is dead and gone
    assert after_trigger.showdown.attack_trigger_resolved is True

    # Damage assignment now sees only the survivors of the trigger.
    defender_side_assignment = combat.showdown_assignment_options(after_trigger, 1)
    assert defender_side_assignment == [()]  # nothing left on that side to assign with

    resolved = combat.resolve_showdown(after_trigger, attacker_assignment=(), defender_assignment=())
    survivors = resolved.battlefields[0].units
    assert {u.instance_id for u in survivors} == {1}
    assert next(iter(survivors)).damage == 0  # Yasuo took the zero damage the dead defender owed
    assert resolved.battlefields[0].controller == 0  # Yasuo's controller holds it uncontested


def test_search_never_offers_a_losing_line_where_the_dead_defender_still_hits_back():
    """End-to-end version of the same fact, through search.legal_actions/
    apply rather than calling combat.py's building blocks directly — proves
    the restructuring is actually wired into the action space a real
    solve() would walk, not just correct if called by hand."""
    yasuo = make_attacker(YASUO_REMORSEFUL, 1, might=6)
    defender = make_filler(2, might=6)
    state = make_state(base_units=frozenset({yasuo}), left_units=frozenset({defender}), left_ctrl=1)
    cards = {YASUO_REMORSEFUL: YASUO_CARD}

    enter = next(a for a in search.legal_actions(state, cards) if isinstance(a, EnterShowdown))
    entered = search.apply(state, enter, cards)

    trigger = next(a for a in search.legal_actions(entered, cards) if isinstance(a, ResolveAttackTrigger))
    assert trigger.trigger_params == (2,)
    after_trigger = search.apply(entered, trigger, cards)

    outcomes = search.resolve_showdown_outcomes(
        after_trigger, next(a for a in search.legal_actions(after_trigger, cards)
                             if a.__class__.__name__ == "ResolveShowdown"))
    assert len(outcomes) == 1
    final = outcomes[0]
    survivors = final.battlefields[0].units
    assert {u.instance_id for u in survivors} == {1}
    assert next(iter(survivors)).damage == 0


# --- Anivia, Primal: "deal 3 to all enemy units here" (no target choice) ---


def test_anivia_wipes_multiple_defenders_before_assignment():
    anivia = make_attacker(ANIVIA_PRIMAL, 1, might=8)
    left_enemy = make_filler(2, might=3)
    right_enemy = make_filler(3, might=3)
    state = make_state(base_units=frozenset({anivia}),
                        left_units=frozenset({left_enemy, right_enemy}), left_ctrl=1)
    entered = combat.open_showdown(state, anivia, "base", "left", has_pending_trigger=True)

    candidates = abilities.ATTACK_TRIGGERS[ANIVIA_PRIMAL][2](entered, 1)
    assert candidates == [("all",)]

    after_trigger = abilities.apply_attack_trigger(
        entered, ResolveAttackTrigger(instance_id=1, trigger_params=("all",)))
    left = next(bf for bf in after_trigger.battlefields if bf.battlefield_id == "left")
    assert {u.instance_id for u in left.units} == {1}  # both 3-Might defenders died to the 3 damage
    assert after_trigger.showdown.attack_trigger_resolved is True
    assert combat.showdown_assignment_options(after_trigger, 1) == [()]


def test_anivia_does_not_kill_units_that_survive_the_3_damage():
    anivia = make_attacker(ANIVIA_PRIMAL, 1, might=8)
    tough_enemy = make_filler(2, might=5)
    state = make_state(base_units=frozenset({anivia}), left_units=frozenset({tough_enemy}), left_ctrl=1)
    entered = combat.open_showdown(state, anivia, "base", "left", has_pending_trigger=True)
    after_trigger = abilities.apply_attack_trigger(
        entered, ResolveAttackTrigger(instance_id=1, trigger_params=("all",)))
    left = next(bf for bf in after_trigger.battlefields if bf.battlefield_id == "left")
    survivor = next(u for u in left.units if u.instance_id == 2)
    assert survivor.damage == 3  # marked, not healed — the Combat Damage Step hasn't happened yet


# --- Crackshot Corsair: flat 1 damage, single target ---


def test_crackshot_corsair_deals_exactly_one():
    corsair = make_attacker(CRACKSHOT_CORSAIR, 1, might=3)
    enemy = make_filler(2, might=2)
    state = make_state(base_units=frozenset({corsair}), left_units=frozenset({enemy}), left_ctrl=1)
    entered = combat.open_showdown(state, corsair, "base", "left", has_pending_trigger=True)
    after_trigger = abilities.apply_attack_trigger(
        entered, ResolveAttackTrigger(instance_id=1, trigger_params=(2,)))
    left = next(bf for bf in after_trigger.battlefields if bf.battlefield_id == "left")
    survivor = next(u for u in left.units if u.instance_id == 2)
    assert survivor.damage == 1  # not enough to kill a Might-2 body on its own


# --- Dune Drake: conditional self-buff, no target ---


def test_dune_drake_buffs_itself_against_a_ready_enemy():
    drake = make_attacker(DUNE_DRAKE, 1, might=5)
    ready_enemy = make_filler(2, might=1, exhausted=False)
    state = make_state(base_units=frozenset({drake}), left_units=frozenset({ready_enemy}), left_ctrl=1)
    entered = combat.open_showdown(state, drake, "base", "left", has_pending_trigger=True)
    after_trigger = abilities.apply_attack_trigger(
        entered, ResolveAttackTrigger(instance_id=1, trigger_params=("buff",)))
    left = next(bf for bf in after_trigger.battlefields if bf.battlefield_id == "left")
    drake_after = next(u for u in left.units if u.instance_id == 1)
    assert drake_after.might == 7  # +2, unconditional Might raise per traits.py's rule


def test_dune_drake_does_nothing_against_an_exhausted_enemy():
    drake = make_attacker(DUNE_DRAKE, 1, might=5)
    tapped_enemy = make_filler(2, might=1, exhausted=True)
    state = make_state(base_units=frozenset({drake}), left_units=frozenset({tapped_enemy}), left_ctrl=1)
    entered = combat.open_showdown(state, drake, "base", "left", has_pending_trigger=True)
    after_trigger = abilities.apply_attack_trigger(
        entered, ResolveAttackTrigger(instance_id=1, trigger_params=("buff",)))
    left = next(bf for bf in after_trigger.battlefields if bf.battlefield_id == "left")
    drake_after = next(u for u in left.units if u.instance_id == 1)
    assert drake_after.might == 5  # condition failed — the trigger still "happened," but did nothing


# --- state significance ---


def test_attack_trigger_resolved_is_part_of_the_canonical_key():
    """Two boards differing only in whether the mandatory trigger has
    fired offer different legal actions, so they must not collide in the
    transposition table — the same lesson moved_this_turn already
    encodes for a different field."""
    from solver.engine.state import ShowdownState, canonical_key

    pending = make_state(left_units=frozenset({make_filler(2)}), left_ctrl=1,
                          showdown=ShowdownState("left", 0, attack_trigger_resolved=False))
    resolved = make_state(left_units=frozenset({make_filler(2)}), left_ctrl=1,
                           showdown=ShowdownState("left", 0, attack_trigger_resolved=True))
    assert canonical_key(pending) != canonical_key(resolved)
