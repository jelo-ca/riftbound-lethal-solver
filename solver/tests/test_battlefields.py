from solver import search
from solver.engine import combat
from solver.engine.abilities import BACK_ALLEY_BAR, apply_move_triggers
from solver.engine.battlefields import TRIFARIAN_WAR_CAMP, VILEMAWS_LAIR, WINDSWEPT_HILLOCK
from solver.engine.actions import (
    MoveUnit,
    effective_keywords,
    is_legal_ability_move_destination,
    is_legal_destination,
    is_legal_move_unit,
)
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance


def make_unit(instance_id, controller=0, might=2, keywords=frozenset(), exhausted=False):
    return UnitInstance(card_id="ogn-010-298", instance_id=instance_id, controller=controller,
                         might=might, keywords=keywords, exhausted=exhausted, damage=0, is_token=False)


def make_state(left_effect=None, right_effect=None, left_units=frozenset(), left_ctrl=None):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", left_ctrl, left_units, left_effect),
            BattlefieldState("right", None, frozenset(), right_effect),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


# --- Windswept Hillock: "Units here have [Ganking]" ---


def test_windswept_hillock_grants_ganking_for_a_battlefield_to_battlefield_move():
    unit = make_unit(1, keywords=frozenset())  # no Ganking of its own
    state = make_state(left_effect=WINDSWEPT_HILLOCK, left_units=frozenset({unit}), left_ctrl=0)
    assert "Ganking" in effective_keywords(state, unit, "left")
    assert is_legal_destination(state, unit, "left", "right")


def test_without_the_hillock_the_same_move_is_illegal():
    unit = make_unit(1, keywords=frozenset())
    state = make_state(left_units=frozenset({unit}), left_ctrl=0)
    assert "Ganking" not in effective_keywords(state, unit, "left")
    assert not is_legal_destination(state, unit, "left", "right")


def test_hillock_ganking_only_applies_while_the_unit_is_actually_there():
    """The grant is positional — a unit at Base doesn't get it just
    because a Hillock exists somewhere on the board."""
    unit = make_unit(1, keywords=frozenset())
    state = make_state(right_effect=WINDSWEPT_HILLOCK, left_units=frozenset({unit}), left_ctrl=0)
    assert "Ganking" not in effective_keywords(state, unit, "left")
    assert not is_legal_destination(state, unit, "left", "right")


def test_hillock_granted_ganking_shows_up_in_move_legality():
    unit = make_unit(1, keywords=frozenset())
    state = make_state(left_effect=WINDSWEPT_HILLOCK, left_units=frozenset({unit}), left_ctrl=0)
    action = MoveUnit(instance_id=1, from_zone="left", to_zone="right")
    assert is_legal_move_unit(state, action)


# --- Vilemaw's Lair: "Units can't move from here to base" ---


def test_vilemaws_lair_blocks_a_standard_move_to_base():
    unit = make_unit(1)
    state = make_state(left_effect=VILEMAWS_LAIR, left_units=frozenset({unit}), left_ctrl=0)
    assert not is_legal_destination(state, unit, "left", "base")


def test_vilemaws_lair_blocks_a_spell_granted_move_to_base():
    """The text restricts movement itself, not one particular way of
    moving - so Ride The Wind/Charm can't route around it either."""
    state = make_state(left_effect=VILEMAWS_LAIR)
    assert not is_legal_ability_move_destination(state, "left", "base")


def test_vilemaws_lair_still_allows_moving_to_the_other_battlefield():
    unit = make_unit(1, keywords=frozenset({"Ganking"}))
    state = make_state(left_effect=VILEMAWS_LAIR, left_units=frozenset({unit}), left_ctrl=0)
    assert is_legal_destination(state, unit, "left", "right")


def test_an_ordinary_battlefield_still_allows_moving_to_base():
    unit = make_unit(1)
    state = make_state(left_units=frozenset({unit}), left_ctrl=0)
    assert is_legal_destination(state, unit, "left", "base")
    assert is_legal_ability_move_destination(state, "left", "base")


# --- Trifarian War Camp: "Units here have +1 Might (this includes attackers)" ---


def test_war_camp_raises_might_for_both_damage_dealt_and_toughness():
    unit = make_unit(1, might=3)
    state = make_state(left_effect=TRIFARIAN_WAR_CAMP, left_units=frozenset({unit}), left_ctrl=0)
    assert combat.effective_might(state, unit, "left", "attacker") == 4
    assert combat.effective_might(state, unit, "left", "defender") == 4
    # 3 damage no longer kills a 3-Might unit standing here.
    assert len(combat._apply_damage(state, "left", frozenset({unit}), ((1, 3),), "defender")) == 1
    assert combat._apply_damage(state, "left", frozenset({unit}), ((1, 4),), "defender") == frozenset()


def test_war_camp_bonus_is_positional_and_applies_outside_combat_too():
    """Unlike Assault/Shield, the battlefield's bonus isn't conditional on
    a combat role - a unit standing here is +1 Might against direct
    effect damage as well."""
    unit = make_unit(1, might=3)
    state = make_state(left_effect=TRIFARIAN_WAR_CAMP, left_units=frozenset({unit}), left_ctrl=0)
    assert combat.effective_might(state, unit, "left", None) == 4
    assert len(combat._apply_damage(state, "left", frozenset({unit}), ((1, 3),), None)) == 1


def test_war_camp_stacks_with_a_keyword_bonus():
    unit = make_unit(1, might=3, keywords=frozenset({"Assault"}))
    state = make_state(left_effect=TRIFARIAN_WAR_CAMP, left_units=frozenset({unit}), left_ctrl=0)
    assert combat.effective_might(state, unit, "left", "attacker") == 5
    assert combat.effective_might(state, unit, "left", "defender") == 4


# --- Back-Alley Bar: "When a unit moves from here, give it +1 Might this turn" ---


def test_back_alley_bar_buffs_a_unit_moving_out_reachable_via_legal_actions():
    """Real end-to-end reachability, not just a direct apply_move_triggers
    call: the plain Standard Move to base is one of search.legal_actions's
    offered actions, and running it through search.apply produces the
    +1 Might."""
    unit = make_unit(1, might=2)
    state = make_state(left_effect=BACK_ALLEY_BAR, left_units=frozenset({unit}), left_ctrl=0)
    action = MoveUnit(instance_id=1, from_zone="left", to_zone="base")
    assert action in search.legal_actions(state, {})
    new_state = search.apply(state, action, {})
    moved = next(u for u in new_state.players[0].base_units if u.instance_id == 1)
    assert moved.might == 3


def test_without_the_bar_the_same_move_grants_nothing():
    unit = make_unit(1, might=2)
    state = make_state(left_units=frozenset({unit}), left_ctrl=0)
    action = MoveUnit(instance_id=1, from_zone="left", to_zone="base")
    new_state = search.apply(state, action, {})
    moved = next(u for u in new_state.players[0].base_units if u.instance_id == 1)
    assert moved.might == 2


def test_bar_only_fires_for_a_move_from_the_bar_itself():
    """Positional, like every other battlefield effect here — a unit
    moving from the OTHER battlefield gets nothing even though a Bar
    exists somewhere on the board."""
    unit = make_unit(1, might=2)
    state = make_state(right_effect=BACK_ALLEY_BAR, left_units=frozenset({unit}), left_ctrl=0)
    action = MoveUnit(instance_id=1, from_zone="left", to_zone="base")
    new_state = search.apply(state, action, {})
    moved = next(u for u in new_state.players[0].base_units if u.instance_id == 1)
    assert moved.might == 2


def test_bar_buffs_either_controllers_mover():
    """Printed text names no controller ("a unit," not "a friendly unit"),
    unlike Reaver's Row/Fortified Position's "friendly" clauses — so an
    enemy unit moving away from the Bar is buffed exactly the same as our
    own. Exercised directly against apply_move_triggers (the shared choke
    point every move path already routes through) rather than through
    legal_actions, since this engine's action space never generates a
    Standard Move for the opponent's own units — the controller-agnostic
    reading is a fact about the trigger's text, not about whose turn it
    is."""
    enemy_unit = make_unit(1, controller=1, might=2)
    state = make_state(left_effect=BACK_ALLEY_BAR, left_units=frozenset({enemy_unit}), left_ctrl=1)
    result = apply_move_triggers(state, 1, "left")
    moved = next(u for u in result.battlefields[0].units if u.instance_id == 1)
    assert moved.might == 3
