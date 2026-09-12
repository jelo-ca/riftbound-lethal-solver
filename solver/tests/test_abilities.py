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
    # Ganking is needed here under the current conservative assumption
    # that spell-granted moves obey the same Battlefield->Battlefield
    # restriction as a Standard Move — see the open question in
    # design/07-scope-and-cut-list.md. Without it, the solver still finds
    # a valid (longer) solution relaying through Base instead.
    exhausted_conqueror = make_unit(1, exhausted=True, keywords=frozenset({"Ganking"}))
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
    solution = solve(root, cards, max_depth=4)
    assert solution is not None
    assert len(solution) == 1
    assert isinstance(solution[0], PlaySpell)

    final_state = apply(root, solution[0], cards)
    assert is_winning(final_state)
    assert final_state.players[0].score == 8


def test_extra_innings_shape_without_ganking_relays_through_base():
    """Same shape, no Ganking: Ride The Wind can't hop the unit directly
    Battlefield->Battlefield under the current conservative assumption, so
    the solver correctly finds the longer relay instead — left->base
    (Ride The Wind readies it), then base->right (a normal Standard Move,
    now legal since the unit is readied). Still wins, just in 2 actions.
    """
    exhausted_conqueror = make_unit(1, exhausted=True)  # no Ganking
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(RIDE_THE_WIND,),
                        runes=RunePool(available=("Fury", "Fury", "Chaos")), score=7),
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
    solution = solve(root, cards, max_depth=4)
    assert solution is not None
    assert len(solution) == 2

    final_state = apply(root, solution[0], cards)
    final_state = apply(final_state, solution[1], {})
    assert is_winning(final_state)
