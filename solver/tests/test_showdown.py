"""Showdowns: the window between moving into an occupied battlefield and
the Combat Damage Step.

It exists because card speeds make it observable. Slow cards — anything
without a marker, which is every unit and every registered ability —
can't be played there; [Action]/[Reaction] ones can. Standard Moves are
excluded entirely: a unit can neither join nor leave a showdown by
moving, only by being moved by a card.
"""

import dataclasses

from solver.engine import abilities, combat
from solver.engine.abilities import PRIMAL_STRENGTH, RIDE_THE_WIND, VENGEANCE
from solver.engine.actions import (
    ActivateAbility,
    EnterShowdown,
    MoveUnit,
    PlaySpell,
    ResolveCombat,
    RunePayment,
    ResolveShowdown,
)
from solver.engine.cards import CardDef
from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    ShowdownState,
    UnitInstance,
    canonical_key,
)
from solver.search import legal_actions

RIDE_THE_WIND_CARD = CardDef(card_id=RIDE_THE_WIND, card_type="Spell", energy_cost=2,
                              power_cost=1, power_domain="Chaos", keywords=frozenset(),
                              speed="Action")
VENGEANCE_CARD = CardDef(card_id=VENGEANCE, card_type="Spell", energy_cost=4, power_cost=2,
                          power_domain="Order", keywords=frozenset())  # Slow (no marker)
PRIMAL_STRENGTH_CARD = CardDef(card_id=PRIMAL_STRENGTH, card_type="Spell", energy_cost=4,
                                power_cost=1, power_domain="Body", keywords=frozenset(),
                                speed="Action")


def make_unit(instance_id, controller=0, might=3, keywords=frozenset(), exhausted=False):
    return UnitInstance(card_id="ogn-010-298", instance_id=instance_id, controller=controller,
                         might=might, keywords=keywords, exhausted=exhausted, damage=0,
                         is_token=False)


def make_state(hand=(), runes=(), base_units=frozenset(), left_units=frozenset(),
                left_ctrl=None, showdown=None):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=hand, runes=RunePool(available=runes), score=0),
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


# --- when the window is materialised at all ---


def test_no_action_speed_card_means_combat_stays_atomic():
    """A showdown whose only legal action is "resolve" isn't a decision,
    so it's folded away and combat looks exactly as it did before
    showdowns existed. Vengeance is Slow, so holding it changes nothing."""
    ours = make_unit(1)
    enemy = make_unit(2, controller=1)
    state = make_state(hand=(VENGEANCE,), runes=("Fury",) * 4 + ("Order", "Order"),
                        base_units=frozenset({ours}), left_units=frozenset({enemy}), left_ctrl=1)
    actions = legal_actions(state, {VENGEANCE: VENGEANCE_CARD})
    assert any(isinstance(a, ResolveCombat) for a in actions)
    assert not any(isinstance(a, EnterShowdown) for a in actions)


def test_an_action_speed_card_in_hand_materialises_the_window():
    ours = make_unit(1)
    enemy = make_unit(2, controller=1)
    state = make_state(hand=(RIDE_THE_WIND,), runes=("Fury", "Fury", "Chaos"),
                        base_units=frozenset({ours}), left_units=frozenset({enemy}), left_ctrl=1)
    actions = legal_actions(state, {RIDE_THE_WIND: RIDE_THE_WIND_CARD})
    assert any(isinstance(a, EnterShowdown) for a in actions)
    assert not any(isinstance(a, ResolveCombat) for a in actions)


def test_an_unaffordable_action_card_does_not_materialise_the_window():
    """Playability, not mere presence — no runes means no showdown play,
    so the window would be an empty formality."""
    ours = make_unit(1)
    enemy = make_unit(2, controller=1)
    state = make_state(hand=(RIDE_THE_WIND,), runes=(),
                        base_units=frozenset({ours}), left_units=frozenset({enemy}), left_ctrl=1)
    actions = legal_actions(state, {RIDE_THE_WIND: RIDE_THE_WIND_CARD})
    assert any(isinstance(a, ResolveCombat) for a in actions)
    assert not any(isinstance(a, EnterShowdown) for a in actions)


def _battlefield_to_battlefield_state(attacker_keywords):
    """Our unit standing on "right", an enemy holding "left" — so the only
    way to start a fight is a Battlefield-to-Battlefield move."""
    attacker = make_unit(1, keywords=attacker_keywords)
    enemy = make_unit(2, controller=1)
    state = make_state(hand=(RIDE_THE_WIND,), runes=("Fury", "Fury", "Chaos"),
                        left_units=frozenset({enemy}), left_ctrl=1)
    return dataclasses.replace(state, battlefields=(
        state.battlefields[0],
        dataclasses.replace(state.battlefields[1], controller=0, units=frozenset({attacker})),
    ))


def test_entering_a_showdown_battlefield_to_battlefield_still_needs_ganking():
    """EnterShowdown is derived from the ResolveCombat candidates rather
    than generated independently, so it inherits every Standard Move zone
    rule — including rule 810: Battlefield-to-Battlefield needs [Ganking].
    Without it the attack isn't a legal move, so there is nothing to open
    a window on (and no atomic ResolveCombat either)."""
    state = _battlefield_to_battlefield_state(frozenset())
    actions = legal_actions(state, {RIDE_THE_WIND: RIDE_THE_WIND_CARD})
    assert not any(isinstance(a, (EnterShowdown, ResolveCombat)) for a in actions)


def test_ganking_lets_a_battlefield_to_battlefield_attack_open_a_showdown():
    """The same board with [Ganking] — this is puzzle 8's opening move,
    where it is the stranded unit's only legal exit."""
    state = _battlefield_to_battlefield_state(frozenset({"Ganking"}))
    actions = legal_actions(state, {RIDE_THE_WIND: RIDE_THE_WIND_CARD})
    entries = [a for a in actions if isinstance(a, EnterShowdown)]
    assert [(a.from_zone, a.to_zone) for a in entries] == [("right", "left")]


# --- the action space inside an open showdown ---


def _open_showdown_state():
    ours = make_unit(1)
    enemy = make_unit(2, controller=1)
    state = make_state(hand=(RIDE_THE_WIND, VENGEANCE),
                        runes=("Fury",) * 6 + ("Chaos", "Order", "Order"),
                        base_units=frozenset({ours}), left_units=frozenset({enemy}), left_ctrl=1)
    mover = next(iter(state.players[0].base_units))
    return combat.open_showdown(state, mover, "base", "left")


def test_showdown_leaves_the_battlefield_contested_with_no_damage_yet():
    state = _open_showdown_state()
    assert state.showdown == ShowdownState(battlefield_id="left", attacker_controller=0)
    left = state.battlefields[0]
    assert {u.instance_id for u in left.units} == {1, 2}
    assert left.controller is None  # Contested
    assert all(u.damage == 0 for u in left.units)


def test_slow_cards_are_locked_out_of_a_showdown_but_action_ones_are_not():
    state = _open_showdown_state()
    cards = {RIDE_THE_WIND: RIDE_THE_WIND_CARD, VENGEANCE: VENGEANCE_CARD}
    spells = [a for a in legal_actions(state, cards) if isinstance(a, PlaySpell)]
    assert spells, "the Action-speed spell should be playable here"
    assert all(s.card_id == RIDE_THE_WIND for s in spells)
    assert not any(s.card_id == VENGEANCE for s in spells)  # Slow


def test_standard_moves_are_unavailable_during_a_showdown():
    """Confirmed rule: units can neither join nor leave a showdown via a
    Standard Move — only a card can move them."""
    state = _open_showdown_state()
    actions = legal_actions(state, {RIDE_THE_WIND: RIDE_THE_WIND_CARD})
    assert not any(isinstance(a, (MoveUnit, ResolveCombat, EnterShowdown)) for a in actions)


def test_abilities_are_locked_out_of_a_showdown_being_slow_by_default():
    state = _open_showdown_state()
    actions = legal_actions(state, {RIDE_THE_WIND: RIDE_THE_WIND_CARD})
    assert not any(isinstance(a, ActivateAbility) for a in actions)


def test_resolving_is_always_available_inside_a_showdown():
    state = _open_showdown_state()
    actions = legal_actions(state, {RIDE_THE_WIND: RIDE_THE_WIND_CARD})
    assert any(isinstance(a, ResolveShowdown) for a in actions)


# --- what the window actually buys ---


def test_a_unit_can_dodge_out_of_a_showdown_and_take_no_damage():
    """The line with no pre-move equivalent: attack, then use an
    [Action] spell to pull the attacker out before damage. It survives a
    fight it would otherwise have lost, and the enemy is untouched."""
    state = _open_showdown_state()
    dodge = PlaySpell(card_id=RIDE_THE_WIND, params=(1, "right"),
                       rune_payment=RunePayment(energy_runes=("Fury", "Fury"),
                                                 power_runes=("Chaos",)))
    after = abilities.resolve_spell_outcomes(state, dodge, RIDE_THE_WIND_CARD)[0]

    left = next(bf for bf in after.battlefields if bf.battlefield_id == "left")
    right = next(bf for bf in after.battlefields if bf.battlefield_id == "right")
    assert {u.instance_id for u in left.units} == {2}  # only the enemy remains
    assert {u.instance_id for u in right.units} == {1}  # ours escaped
    assert all(u.damage == 0 for u in right.units)


def test_resolve_showdown_reads_participants_from_the_live_board():
    """Damage is dealt by whoever is standing there at resolve time, not
    by whoever entered — that's the whole point of allowing joins and
    dodges mid-showdown."""
    state = _open_showdown_state()
    # Our attacker leaves; the showdown now has no attackers at all.
    left = next(bf for bf in state.battlefields if bf.battlefield_id == "left")
    without_ours = frozenset(u for u in left.units if u.controller != 0)
    state = dataclasses.replace(
        state,
        battlefields=tuple(
            dataclasses.replace(bf, units=without_ours) if bf.battlefield_id == "left" else bf
            for bf in state.battlefields
        ),
    )
    assert combat.showdown_assignment_options(state, 0) == [()]
    resolved = combat.resolve_showdown(state, (), ())
    assert resolved.showdown is None
    assert {u.instance_id for u in resolved.battlefields[0].units} == {2}
    assert resolved.battlefields[0].controller == 1  # enemy holds it unopposed


def test_showdown_is_part_of_the_canonical_key():
    plain = make_state(left_units=frozenset({make_unit(2, controller=1)}), left_ctrl=1)
    mid = make_state(left_units=frozenset({make_unit(2, controller=1)}), left_ctrl=1,
                      showdown=ShowdownState("left", 0))
    assert canonical_key(plain) != canonical_key(mid)
