from solver.engine.abilities import (
    BLITZCRANK_IMPASSIVE,
    CAITLYN_PATROLLING,
    RIDE_THE_WIND,
    VENGEANCE,
    ZAUNITE_BOUNCER,
    is_legal_activate_ability,
    is_legal_play_spell,
    is_legal_unit_play_trigger,
    resolve_spell_outcomes,
    resolve_unit_play_trigger_outcomes,
)
from solver.engine.actions import ActivateAbility, PlaySpell, PlayUnit, RunePayment
from solver.engine.cards import CardDef
from solver.engine.scoring import is_winning
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from solver.search import apply, legal_actions, solve

RIDE_THE_WIND_CARD = CardDef(card_id=RIDE_THE_WIND, card_type="Spell", energy_cost=2,
                              power_cost=1, power_domain="Chaos", keywords=frozenset())
VENGEANCE_CARD = CardDef(card_id=VENGEANCE, card_type="Spell", energy_cost=4,
                          power_cost=2, power_domain="Order", keywords=frozenset())
ZAUNITE_BOUNCER_CARD = CardDef(card_id=ZAUNITE_BOUNCER, card_type="Unit", energy_cost=4,
                                power_cost=2, power_domain="Chaos", might=2, keywords=frozenset())


def make_unit(instance_id, controller=0, might=2, exhausted=False, keywords=frozenset()):
    return UnitInstance(
        card_id="ogn-010-298", instance_id=instance_id, controller=controller,
        might=might, keywords=keywords, exhausted=exhausted, damage=0, is_token=False,
    )


def test_ride_the_wind_moves_an_exhausted_unit_and_readies_it():
    """The whole point of the card: unlike a Standard Move, it doesn't
    require the unit to already be unexhausted."""
    exhausted_unit = make_unit(1, exhausted=True)
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset({exhausted_unit}), hand=(RIDE_THE_WIND,),
                        runes=RunePool(available=("Fury", "Fury", "Chaos")), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    action = PlaySpell(
        card_id=RIDE_THE_WIND,
        params=(1, "left"),
        rune_payment=RunePayment(energy_runes=("Fury", "Fury"), power_runes=("Chaos",)),
    )
    assert is_legal_play_spell(root, action, RIDE_THE_WIND_CARD)

    outcomes = resolve_spell_outcomes(root, action, RIDE_THE_WIND_CARD)
    assert len(outcomes) == 1
    new_state = outcomes[0]
    moved = next(iter(new_state.battlefields[0].units))
    assert moved.exhausted is False  # readied, not just moved
    assert new_state.battlefields[0].controller == 0  # established control
    assert RIDE_THE_WIND not in new_state.players[0].hand
    assert new_state.players[0].runes.available == ()


def test_ride_the_wind_appears_in_legal_actions_when_affordable():
    exhausted_unit = make_unit(1, exhausted=True)
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset({exhausted_unit}), hand=(RIDE_THE_WIND,),
                        runes=RunePool(available=("Fury", "Fury", "Chaos")), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    cards = {RIDE_THE_WIND: RIDE_THE_WIND_CARD}
    actions = legal_actions(root, cards)
    spell_actions = [a for a in actions if isinstance(a, PlaySpell)]
    assert len(spell_actions) > 0
    assert all(a.card_id == RIDE_THE_WIND for a in spell_actions)


def test_extra_innings_shape_solver_finds_the_hidden_extra_action():
    """'Extra Innings' (08-puzzle-concepts.md #4): at 7 points, one unit
    already conquered 'left' this turn and is now exhausted — normally
    stuck, since a Standard Move requires the unit not be exhausted. Ride
    The Wind moves it to 'right' (an open battlefield) AND readies it in
    the same action, establishing control there too. Since 'left' stays
    in scored_this_turn even after losing control (rule 471.1.b, per
    puzzle 2's validated behavior), this Scores both battlefields this
    turn and wins the Final Point — solvable in exactly 1 action.
    """
    # No Ganking needed: confirmed that spell-granted moves (Ride The
    # Wind, Charm) are NOT bound by Ganking's Battlefield->Battlefield
    # restriction — that's specific to a unit's own Standard Move (rule
    # 810). A spell states explicitly if it's restricted to Base.
    exhausted_conqueror = make_unit(1, exhausted=True)
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(
                base_units=frozenset(),
                hand=(RIDE_THE_WIND,),
                runes=RunePool(available=("Fury", "Fury", "Chaos")),
                score=7,
            ),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, frozenset({exhausted_conqueror}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset({"left"}),
        cards_played_this_turn=0,
    )
    cards = {RIDE_THE_WIND: RIDE_THE_WIND_CARD}
    strategy = solve(root, cards, max_depth=4)
    assert strategy is not None
    assert len(strategy) == 1
    action = next(iter(strategy.values()))
    assert isinstance(action, PlaySpell)

    final_state = resolve_spell_outcomes(root, action, RIDE_THE_WIND_CARD)[0]
    assert is_winning(final_state)
    assert final_state.players[0].score == 8


def test_ride_the_wind_battlefield_to_battlefield_does_not_require_ganking():
    """Confirmed: spell-granted "Move" effects default to any destination
    (including Battlefield->Battlefield) with no Ganking requirement —
    that restriction is specific to a unit's own Standard Move. A unit
    with no keywords at all can still be Ride The Wind'd directly from one
    battlefield to another.
    """
    unit = make_unit(1, exhausted=True, keywords=frozenset())  # no Ganking
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(RIDE_THE_WIND,),
                        runes=RunePool(available=("Fury", "Fury", "Chaos")), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, frozenset({unit}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    action = PlaySpell(
        card_id=RIDE_THE_WIND,
        params=(1, "right"),
        rune_payment=RunePayment(energy_runes=("Fury", "Fury"), power_runes=("Chaos",)),
    )
    assert is_legal_play_spell(root, action, RIDE_THE_WIND_CARD)
    new_state = resolve_spell_outcomes(root, action, RIDE_THE_WIND_CARD)[0]
    assert new_state.battlefields[1].controller == 0
    assert not next(iter(new_state.battlefields[1].units)).exhausted


# --- Caitlyn - Patrolling: "Exhaust: Deal damage equal to my Might to a unit at a battlefield" ---


def make_caitlyn(instance_id, exhausted=False, might=3):
    return UnitInstance(card_id=CAITLYN_PATROLLING, instance_id=instance_id, controller=0,
                         might=might, keywords=frozenset(), exhausted=exhausted, damage=0, is_token=False)


def test_caitlyn_kills_a_weaker_enemy_unit():
    caitlyn = make_caitlyn(1)
    target = UnitInstance("enemy", 2, controller=1, might=3, keywords=frozenset(),
                           exhausted=False, damage=0, is_token=False)
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset({caitlyn, target}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    action = ActivateAbility(source_id=1, ability_id=CAITLYN_PATROLLING, params=(2,), rune_payment=None)
    assert is_legal_activate_ability(root, action)

    new_state = apply(root, action, {})
    left_units = {u.instance_id: u for u in new_state.battlefields[0].units}
    assert 2 not in left_units  # target died
    assert left_units[1].exhausted is True  # Caitlyn paid her Exhaust cost


def test_caitlyn_cannot_activate_from_base():
    caitlyn = make_caitlyn(1)
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset({caitlyn}), hand=(), runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    action = ActivateAbility(source_id=1, ability_id=CAITLYN_PATROLLING, params=(1,), rune_payment=None)
    assert not is_legal_activate_ability(root, action)  # "only while I'm at a battlefield"


def test_caitlyn_cannot_activate_while_exhausted():
    caitlyn = make_caitlyn(1, exhausted=True)
    target = UnitInstance("enemy", 2, controller=1, might=3, keywords=frozenset(),
                           exhausted=False, damage=0, is_token=False)
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset({caitlyn, target}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    action = ActivateAbility(source_id=1, ability_id=CAITLYN_PATROLLING, params=(2,), rune_payment=None)
    assert not is_legal_activate_ability(root, action)


def test_caitlyn_killing_last_enemy_makes_battlefield_uncontrolled():
    caitlyn = make_caitlyn(1)
    target = UnitInstance("enemy", 2, controller=1, might=3, keywords=frozenset(),
                           exhausted=False, damage=0, is_token=False)
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 1, frozenset({caitlyn, target}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    action = ActivateAbility(source_id=1, ability_id=CAITLYN_PATROLLING, params=(2,), rune_payment=None)
    new_state = apply(root, action, {})
    # Caitlyn (controller 0) and the dead target's controller (1) leaves a
    # mixed-then-single-controller board: only Caitlyn (0) remains.
    assert new_state.battlefields[0].controller == 0


# --- Vengeance: "Kill a unit" (any unit, any controller, Base or battlefield) ---


def _vengeance_action(target_id):
    return PlaySpell(
        card_id=VENGEANCE, params=(target_id,),
        rune_payment=RunePayment(energy_runes=("Fury",) * 4, power_runes=("Order", "Order")),
    )


def test_vengeance_kills_an_enemy_unit_at_a_battlefield():
    target = UnitInstance("enemy", 2, controller=1, might=5, keywords=frozenset(),
                           exhausted=False, damage=0, is_token=False)
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(VENGEANCE,),
                        runes=RunePool(available=("Fury", "Fury", "Fury", "Fury", "Order", "Order")), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 1, frozenset({target}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    action = _vengeance_action(2)
    assert is_legal_play_spell(root, action, VENGEANCE_CARD)
    new_state = resolve_spell_outcomes(root, action, VENGEANCE_CARD)[0]
    assert new_state.battlefields[0].units == frozenset()
    assert new_state.battlefields[0].controller is None


def test_vengeance_can_kill_your_own_unit():
    own_unit = make_unit(1, might=10)  # even a huge Might doesn't save it - not damage-based
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(VENGEANCE,),
                        runes=RunePool(available=("Fury", "Fury", "Fury", "Fury", "Order", "Order")), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, frozenset({own_unit}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    action = _vengeance_action(1)
    assert is_legal_play_spell(root, action, VENGEANCE_CARD)
    new_state = resolve_spell_outcomes(root, action, VENGEANCE_CARD)[0]
    assert new_state.battlefields[0].units == frozenset()


def test_vengeance_can_kill_a_unit_sitting_at_base():
    based_unit = make_unit(1)
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset({based_unit}), hand=(VENGEANCE,),
                        runes=RunePool(available=("Fury", "Fury", "Fury", "Fury", "Order", "Order")), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    action = _vengeance_action(1)
    assert is_legal_play_spell(root, action, VENGEANCE_CARD)
    new_state = resolve_spell_outcomes(root, action, VENGEANCE_CARD)[0]
    assert new_state.players[0].base_units == frozenset()


def test_vengeance_rejects_a_nonexistent_target():
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(VENGEANCE,),
                        runes=RunePool(available=("Fury", "Fury", "Fury", "Fury", "Order", "Order")), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    assert not is_legal_play_spell(root, _vengeance_action(99), VENGEANCE_CARD)


# --- Zaunite Bouncer: "When you play me, return another unit at a battlefield to its owner's hand" ---


def _play_zaunite_bouncer(trigger_params=()):
    return PlayUnit(
        card_id=ZAUNITE_BOUNCER, target_zone="base",
        rune_payment=RunePayment(energy_runes=("Fury",) * 4, power_runes=("Chaos", "Chaos")),
        trigger_params=trigger_params,
    )


def _zaunite_root(other_units=frozenset()):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(ZAUNITE_BOUNCER,),
                        runes=RunePool(available=("Fury", "Fury", "Fury", "Fury", "Chaos", "Chaos")), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", 1 if other_units else None, other_units, None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def test_zaunite_bouncer_returns_an_enemy_unit_to_its_owners_hand():
    enemy = UnitInstance("enemy-card", 5, controller=1, might=4, keywords=frozenset(),
                          exhausted=False, damage=0, is_token=False)
    root = _zaunite_root(frozenset({enemy}))
    action = _play_zaunite_bouncer(trigger_params=(5,))
    assert is_legal_unit_play_trigger(root, action, ZAUNITE_BOUNCER_CARD)
    outcomes = resolve_unit_play_trigger_outcomes(root, action, ZAUNITE_BOUNCER_CARD)
    assert len(outcomes) == 1
    new_state = outcomes[0]
    assert not any(u.instance_id == 5 for u in new_state.battlefields[1].units)
    assert "enemy-card" in new_state.players[1].hand


def test_zaunite_bouncer_ignores_tank():
    tank = UnitInstance("tank-card", 5, controller=1, might=4, keywords=frozenset({"Tank"}),
                         exhausted=False, damage=0, is_token=False)
    root = _zaunite_root(frozenset({tank}))
    action = _play_zaunite_bouncer(trigger_params=(5,))
    assert is_legal_unit_play_trigger(root, action, ZAUNITE_BOUNCER_CARD)


def test_zaunite_bouncer_can_target_a_friendly_unit():
    friendly = make_unit(5, controller=0)
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(ZAUNITE_BOUNCER,),
                        runes=RunePool(available=("Fury", "Fury", "Fury", "Fury", "Chaos", "Chaos")), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", 0, frozenset({friendly}), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    action = _play_zaunite_bouncer(trigger_params=(5,))
    assert is_legal_unit_play_trigger(root, action, ZAUNITE_BOUNCER_CARD)
    outcomes = resolve_unit_play_trigger_outcomes(root, action, ZAUNITE_BOUNCER_CARD)
    assert len(outcomes) == 1
    assert "ogn-010-298" in outcomes[0].players[0].hand


def test_zaunite_bouncer_cannot_target_itself():
    root = _zaunite_root()
    # Predict Zaunite Bouncer's own about-to-be-assigned instance_id (1,
    # since the board is otherwise empty) and confirm targeting it is illegal.
    action = _play_zaunite_bouncer(trigger_params=(1,))
    assert not is_legal_unit_play_trigger(root, action, ZAUNITE_BOUNCER_CARD)


def test_zaunite_bouncer_decline_is_legal():
    root = _zaunite_root()
    action = _play_zaunite_bouncer()
    assert is_legal_unit_play_trigger(root, action, ZAUNITE_BOUNCER_CARD)


def test_caitlyn_appears_in_legal_actions_when_usable():
    caitlyn = make_caitlyn(1)
    target = UnitInstance("enemy", 2, controller=1, might=3, keywords=frozenset(),
                           exhausted=False, damage=0, is_token=False)
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset({caitlyn, target}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    actions = legal_actions(root, {})
    ability_actions = [a for a in actions if isinstance(a, ActivateAbility)]
    assert any(a.source_id == 1 and a.params == (2,) for a in ability_actions)
