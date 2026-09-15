"""[Deathknell] — "When I die, get the effect."

The hook is the real work: units are removed in three places inside
combat.py plus actions.kill_unit's Base path, and nothing fired on any
of them before. Kog'Maw, Caustic is the card that makes it matter — a
1-Might body that deals 4 to everything at its battlefield when it dies,
which turns "kill your own unit" into a real line (Vengeance can target
your own units).
"""

from solver.engine import combat
from solver.engine.actions import kill_unit
from solver.engine.card_pool import CARD_POOL, KOGMAW_CAUSTIC, MACHINE_EVANGEL, RECRUIT_TOKEN
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance


def make_unit(instance_id, card_id="plain", controller=0, might=3, damage=0, keywords=frozenset()):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=keywords, exhausted=False, damage=damage,
                         is_token=False)


def kogmaw(instance_id, controller=0, damage=0):
    return make_unit(instance_id, card_id=KOGMAW_CAUSTIC, controller=controller, might=1,
                      damage=damage, keywords=frozenset({"Deathknell"}))


def make_state(left_units=frozenset(), left_ctrl=None, base_units=frozenset()):
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


def units_at(state, index=0):
    return {u.instance_id: u for u in state.battlefields[index].units}


# --- the hook fires from every death path ---


def test_deathknell_fires_when_killed_outright():
    """Vengeance's path — a removal, not a damage amount."""
    victim = kogmaw(1)
    bystander = make_unit(2, might=5)
    state = make_state(frozenset({victim, bystander}), left_ctrl=0)
    result = kill_unit(state, 1)
    assert 1 not in units_at(result)  # Kog'Maw gone
    assert units_at(result)[2].damage == 4  # and it hit the survivor on the way out


def test_deathknell_fires_from_direct_effect_damage():
    """Caitlyn's path, via combat.deal_damage_to_unit."""
    victim = kogmaw(1)
    bystander = make_unit(2, might=5)
    state = make_state(frozenset({victim, bystander}), left_ctrl=0)
    result = combat.deal_damage_to_unit(state, "left", 1, 1)  # 1 damage kills a 1-Might body
    assert 1 not in units_at(result)
    assert units_at(result)[2].damage == 4


def test_deathknell_fires_when_it_dies_in_combat():
    """apply_combat's path — and the case that matters most: a defender
    that SURVIVED the combat damage still dies to the extra 4."""
    defender = kogmaw(1, controller=1)
    attacker = make_unit(2, controller=0, might=4)
    state = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset({attacker}), hand=(), runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 1, frozenset({defender}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    result = combat.apply_combat(state, attacker, "base", "left",
                                  attacker_assignment=((1, 1),), defender_assignment=())
    # Kog'Maw died to the attack, then its Deathknell killed the 4-Might
    # attacker standing on the same battlefield.
    assert result.battlefields[0].units == frozenset()
    assert result.battlefields[0].controller is None


def test_deathknell_at_base_finds_no_battlefield_and_does_not_crash():
    """"all units at my battlefield" — a unit dying at Base has none."""
    victim = kogmaw(1)
    state = make_state(base_units=frozenset({victim}))
    result = kill_unit(state, 1)
    assert result.players[0].base_units == frozenset()


def test_a_unit_without_deathknell_triggers_nothing():
    victim = make_unit(1, might=1)
    bystander = make_unit(2, might=5)
    state = make_state(frozenset({victim, bystander}), left_ctrl=0)
    result = kill_unit(state, 1)
    assert units_at(result)[2].damage == 0


# --- the effects themselves ---


def test_kogmaw_hits_friendly_units_too():
    """"all units at my battlefield" — the text doesn't restrict it."""
    victim = kogmaw(1, controller=0)
    friend = make_unit(2, controller=0, might=5)
    enemy = make_unit(3, controller=1, might=5)
    state = make_state(frozenset({victim, friend, enemy}))
    result = kill_unit(state, 1)
    assert units_at(result)[2].damage == 4
    assert units_at(result)[3].damage == 4


def test_kogmaw_does_not_reach_the_other_battlefield():
    victim = kogmaw(1)
    elsewhere = make_unit(2, might=5)
    state = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, frozenset({victim}), None),
            BattlefieldState("right", 0, frozenset({elsewhere}), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    result = kill_unit(state, 1)
    assert units_at(result, 1)[2].damage == 0


def test_machine_evangel_mints_three_tokens_into_base():
    """"into your base" — not "here", so where it died doesn't matter."""
    victim = make_unit(1, card_id=MACHINE_EVANGEL, might=4, keywords=frozenset({"Deathknell"}))
    state = make_state(frozenset({victim}), left_ctrl=0)
    result = kill_unit(state, 1)
    tokens = [u for u in result.players[0].base_units if u.card_id == RECRUIT_TOKEN]
    assert len(tokens) == 3
    assert all(t.might == 1 and t.is_token for t in tokens)


# --- cascades ---


def test_one_deathknell_sets_off_another():
    """Kog'Maw A dies, its 4 damage kills Kog'Maw B, and B's own
    Deathknell fires in turn — hitting what's left."""
    a = kogmaw(1)
    b = kogmaw(2)
    tough = make_unit(3, might=9)
    state = make_state(frozenset({a, b, tough}), left_ctrl=0)
    result = kill_unit(state, 1)
    assert 1 not in units_at(result)
    assert 2 not in units_at(result)  # B died to A's blast
    # Hit twice: once by A's Deathknell, once by B's.
    assert units_at(result)[3].damage == 8


def test_a_cascade_that_clears_the_battlefield_leaves_it_uncontrolled():
    a = kogmaw(1)
    b = kogmaw(2)
    state = make_state(frozenset({a, b}), left_ctrl=0)
    result = kill_unit(state, 1)
    assert result.battlefields[0].units == frozenset()
    assert result.battlefields[0].controller is None


# --- tripwire ---


def test_no_pool_card_has_reaction_speed():
    """Each Deathknell resolution is a point where the rules allow a
    [Reaction]-speed play, and engine/deaths.py does NOT model that
    window — it resolves cascades atomically instead, because no card in
    the pool has Reaction speed so the window can never be observed.

    This test is the tripwire on that assumption. If it fails, someone
    added a Reaction card and the Deathknell window (and the showdown
    handling around it) needs materialising for real — see deaths.py's
    KNOWN GAP note. Do not just delete this test.
    """
    reaction_cards = [cid for cid, card in CARD_POOL.items() if card.speed == "Reaction"]
    assert reaction_cards == []
