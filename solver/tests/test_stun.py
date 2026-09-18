"""Stun (RULES ANSWER, project owner, 2026-09-18): a stunned unit's Might
is IGNORED when summing its SIDE's damage-dealing pool for the Combat
Damage Step — it contributes 0 to what its side deals out. It is NOT
removed from combat, stays alive/targetable, and its OWN death threshold
(how much damage kills IT) is completely unaffected — only the "how much
damage does my side deal" side of the ledger changes. See
combat.side_damage_pool, the one place a side's Might gets summed into an
assignable pool; traits.effective_might (a unit's own death threshold)
never reads `stunned` and must not start to.
"""

from solver import search
from solver.engine import abilities, combat
from solver.engine.abilities import LEONA_DETERMINED
from solver.engine.actions import EnterShowdown, ResolveAttackTrigger
from solver.engine.card_pool import card_def
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance

LEONA_CARD = card_def(LEONA_DETERMINED)


def make_unit(instance_id, controller=0, might=3, keywords=frozenset(), damage=0,
              exhausted=False, stunned=False, card_id="u"):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=keywords, exhausted=exhausted, damage=damage,
                         is_token=False, stunned=stunned)


def make_state(base_units=frozenset(), left_units=frozenset(), left_ctrl=None):
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
    )


# --- combat.side_damage_pool: the one place "stunned means 0" is encoded ---


def test_stunned_unit_contributes_zero_to_its_sides_pool():
    unit = make_unit(1, might=5, stunned=True)
    state = make_state(left_units=frozenset({unit}))
    assert combat.side_damage_pool(state, "left", frozenset({unit}), "attacker") == 0


def test_unstunned_unit_still_contributes_its_full_might():
    unit = make_unit(1, might=5)
    state = make_state(left_units=frozenset({unit}))
    assert combat.side_damage_pool(state, "left", frozenset({unit}), "attacker") == 5


def test_pool_sums_only_the_unstunned_members_of_a_mixed_side():
    stunned = make_unit(1, might=5, stunned=True)
    plain = make_unit(2, might=3)
    state = make_state(left_units=frozenset({stunned, plain}))
    assert combat.side_damage_pool(state, "left", frozenset({stunned, plain}), "attacker") == 3


# --- effective_might (a unit's own death threshold) is NEVER touched -----


def test_stunned_units_own_death_threshold_is_unaffected():
    """A stunned 5-Might unit still needs 5 damage to die: stun never
    touches effective_might's return value, only the pool sum feeding
    combat.side_damage_pool. If it incorrectly did, 4 damage would already
    be lethal (threshold 0), which this pins against."""
    unit = make_unit(1, might=5, stunned=True)
    state = make_state(left_units=frozenset({unit}))
    survivors = combat._apply_damage(state, "left", frozenset({unit}), ((1, 4),), "defender")
    assert len(survivors) == 1
    assert combat._apply_damage(state, "left", frozenset({unit}), ((1, 5),), "defender") == frozenset()


# --- end-to-end through the actual patched call site ----------------------


def test_stunned_defender_deals_zero_but_keeps_its_real_death_threshold():
    """The case that only passes if Stun is implemented on the deal-damage
    side ALONE. Attacker (Might 2) is deliberately WEAKER than the stunned
    defender's real Might (3): a wrong implementation that zeroed the
    defender's own Might (rather than only its contribution to its side's
    pool) would drop its death threshold to 0 and let this weaker attack
    kill it. Correct Stun leaves the threshold at 3 (survives Might-2
    damage) while ALSO making the defender's own side deal back exactly
    zero, since enumerate_combat_outcomes reads the defender's pool
    through combat.side_damage_pool.
    """
    attacker = make_unit(1, controller=0, might=2)
    defender = make_unit(2, controller=1, might=3, stunned=True)
    state = make_state(base_units=frozenset({attacker}), left_units=frozenset({defender}), left_ctrl=1)

    # Our own assignment options are capped by OUR pool (2, unaffected by
    # the defender's stun) against the defender's real Might (3) - so no
    # option can reach lethal.
    options = combat.our_assignment_options(state, attacker, "left")
    assert options == [((2, 2),)]  # partial hit only, 2 < 3 needed

    outcomes = combat.enumerate_combat_outcomes(state, attacker, "base", "left", our_assignment=((2, 2),))
    # The stunned defender's own pool is 0 (side_damage_pool), so there is
    # exactly one possible opponent response: assigning nothing.
    assert len(outcomes) == 1
    left = outcomes[0].battlefields[0]
    assert {u.instance_id for u in left.units} == {1, 2}  # both survive
    survivor = next(u for u in left.units if u.instance_id == 2)
    assert survivor.damage == 0  # healed post-combat, not dead
    mover = next(u for u in left.units if u.instance_id == 1)
    assert mover.damage == 0  # the stunned side dealt back exactly zero


# --- state significance: stunned must render and hash distinctly ---------


def test_stunned_field_is_part_of_the_canonical_key():
    from solver.engine.state import canonical_key

    plain = make_state(left_units=frozenset({make_unit(1, might=3)}))
    stunned = make_state(left_units=frozenset({make_unit(1, might=3, stunned=True)}))
    assert canonical_key(plain) != canonical_key(stunned)


def test_export_renders_stunned():
    from solver.export import render_unit

    assert render_unit(make_unit(1, stunned=True))["stunned"] is True
    assert render_unit(make_unit(1, stunned=False))["stunned"] is False


# --- Leona, Determined: "when I attack, stun an enemy unit here" ---------


def make_attacker(card_id, instance_id, might, controller=0, exhausted=False):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=frozenset(), exhausted=exhausted, damage=0,
                         is_token=False)


def make_filler(instance_id, controller=1, might=3, exhausted=False):
    return UnitInstance(card_id="u", instance_id=instance_id, controller=controller, might=might,
                         keywords=frozenset(), exhausted=exhausted, damage=0, is_token=False)


def test_leona_is_reachable_only_through_the_showdown_mechanism():
    """Same Rule Answer 1 as every other ATTACK_TRIGGERS entry: the atomic
    ResolveCombat path is built from the pre-trigger defender list, unsafe
    once the trigger can stun (and thus zero the pool of) one of those
    defenders before the Combat Damage Step."""
    from solver.engine.actions import ResolveCombat

    leona = make_attacker(LEONA_DETERMINED, 1, might=4)
    enemy = make_filler(2, might=3)
    state = make_state(base_units=frozenset({leona}), left_units=frozenset({enemy}), left_ctrl=1)
    actions = search.legal_actions(state, {LEONA_DETERMINED: LEONA_CARD})
    assert any(isinstance(a, EnterShowdown) for a in actions)
    assert not any(isinstance(a, ResolveCombat) for a in actions)


def test_leona_trigger_reachable_via_search_legal_actions():
    """Verifies reachability through the actual search machinery, not just
    the registry — the non-negotiable this whole cluster exists to honor."""
    leona = make_attacker(LEONA_DETERMINED, 1, might=4)
    enemy = make_filler(2, might=3)
    state = make_state(base_units=frozenset({leona}), left_units=frozenset({enemy}), left_ctrl=1)
    cards = {LEONA_DETERMINED: LEONA_CARD}

    enter = next(a for a in search.legal_actions(state, cards) if isinstance(a, EnterShowdown))
    entered = search.apply(state, enter, cards)
    assert entered.showdown.attack_trigger_resolved is False

    trigger = next(a for a in search.legal_actions(entered, cards)
                   if isinstance(a, ResolveAttackTrigger))
    assert trigger == ResolveAttackTrigger(instance_id=1, trigger_params=(2,))

    after_trigger = search.apply(entered, trigger, cards)
    left = next(bf for bf in after_trigger.battlefields if bf.battlefield_id == "left")
    stunned = next(u for u in left.units if u.instance_id == 2)
    assert stunned.stunned is True
    assert after_trigger.showdown.attack_trigger_resolved is True


def test_leona_stunned_enemy_deals_zero_combat_damage_but_still_dies_normally():
    """"It doesn't deal combat damage this turn" — the stunned defender
    keeps its own death threshold (dies to Leona's own damage exactly as
    it would unstunned) but its side's pool is zero, so Leona takes
    nothing back even though the defender's Might (3) would otherwise
    have been lethal to her (Might... here overkill-proofed at 4)."""
    leona = make_attacker(LEONA_DETERMINED, 1, might=4)
    enemy = make_filler(2, might=3)
    state = make_state(base_units=frozenset({leona}), left_units=frozenset({enemy}), left_ctrl=1)

    entered = combat.open_showdown(state, leona, "base", "left", has_pending_trigger=True)
    trigger_action = ResolveAttackTrigger(instance_id=1, trigger_params=(2,))
    assert abilities.is_legal_resolve_attack_trigger(entered, trigger_action)
    after_trigger = abilities.apply_attack_trigger(entered, trigger_action)

    left = next(bf for bf in after_trigger.battlefields if bf.battlefield_id == "left")
    stunned = next(u for u in left.units if u.instance_id == 2)
    assert stunned.stunned is True
    assert stunned.damage == 0  # stun doesn't itself deal damage

    # The stunned enemy's own side pool is zero — nothing left to assign
    # against Leona regardless of the enemy's real Might.
    assert combat.showdown_assignment_options(after_trigger, 1) == [()]

    # Leona assigns her full 4 to the (still-normal-threshold) enemy.
    resolved = combat.resolve_showdown(after_trigger, attacker_assignment=((2, 3),),
                                        defender_assignment=())
    survivors = resolved.battlefields[0].units
    assert {u.instance_id for u in survivors} == {1}  # enemy died to exactly its real Might
    assert next(iter(survivors)).damage == 0  # Leona took zero back
    assert resolved.battlefields[0].controller == 0
