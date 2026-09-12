from solver.engine.abilities import RIDE_THE_WIND, is_legal_play_spell
from solver.engine.actions import PlaySpell, RunePayment
from solver.engine.cards import CardDef
from solver.engine.scoring import is_winning
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from solver.search import apply, legal_actions, solve

RIDE_THE_WIND_CARD = CardDef(card_id=RIDE_THE_WIND, card_type="Spell", energy_cost=2,
                              power_cost=1, power_domain="Chaos", keywords=frozenset())


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

    new_state = apply(root, action, {RIDE_THE_WIND: RIDE_THE_WIND_CARD})
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

    final_state = apply(root, action, cards)
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
    new_state = apply(root, action, {RIDE_THE_WIND: RIDE_THE_WIND_CARD})
    assert new_state.battlefields[1].controller == 0
    assert not next(iter(new_state.battlefields[1].units)).exhausted
