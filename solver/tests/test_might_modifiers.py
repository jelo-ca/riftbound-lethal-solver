"""Temporary "+N Might this turn" modifiers.

A puzzle is a single turn, so "this turn" never expires inside one —
Primal Strength's +7 just raises `UnitInstance.might` directly (an
unconditional Might change IS Might, no separate bonus field — see
engine/traits.py's module docstring). What still needs checking is that
raising Might raises BOTH jobs it does: the damage a unit deals and the
damage needed to kill it.
"""

from solver.engine import abilities, combat
from solver.engine.abilities import PRIMAL_STRENGTH
from solver.engine.actions import PlaySpell, RunePayment
from solver.engine.battlefields import TRIFARIAN_WAR_CAMP
from solver.engine.cards import CardDef
from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    UnitInstance,
    canonical_key,
)

PRIMAL_STRENGTH_CARD = CardDef(card_id=PRIMAL_STRENGTH, card_type="Spell", energy_cost=4,
                                power_cost=1, power_domain="Body", keywords=frozenset())
PAYMENT = RunePayment(energy_runes=("Fury",) * 4, power_runes=("Body",))
RUNES = ("Fury", "Fury", "Fury", "Fury", "Body")


def make_unit(instance_id, controller=0, might=2, keywords=frozenset()):
    return UnitInstance(card_id="ogn-010-298", instance_id=instance_id, controller=controller,
                         might=might, keywords=keywords, exhausted=False, damage=0,
                         is_token=False)


def make_state(base_units=frozenset(), left_units=frozenset(), left_ctrl=None, hand=(),
               left_effect=None):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=hand, runes=RunePool(available=RUNES), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", left_ctrl, left_units, left_effect),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def _cast(target_id):
    return PlaySpell(card_id=PRIMAL_STRENGTH, params=(target_id,), rune_payment=PAYMENT)


def test_primal_strength_buff_raises_the_lethal_threshold_too():
    """The half that's easy to forget: a buffed unit is correspondingly
    harder to kill, because it's the same stat."""
    unit = make_unit(1, might=2)
    root = make_state(left_units=frozenset({unit}), left_ctrl=0, hand=(PRIMAL_STRENGTH,))
    buffed_state = abilities.resolve_spell_outcomes(root, _cast(1), PRIMAL_STRENGTH_CARD)[0]
    buffed = next(iter(buffed_state.battlefields[0].units))
    assert buffed.might == 9  # 2 printed +7 — no separate bonus field
    assert len(combat._apply_damage(buffed_state, "left", frozenset({buffed}), ((1, 8),))) == 1  # 8 < 9, survives
    assert combat._apply_damage(buffed_state, "left", frozenset({buffed}), ((1, 9),)) == frozenset()


def test_primal_strength_buff_stacks_with_trait_and_battlefield_bonuses():
    unit = make_unit(1, might=2, keywords=frozenset({"Assault"}))
    root = make_state(left_units=frozenset({unit}), left_ctrl=0, hand=(PRIMAL_STRENGTH,),
                       left_effect=TRIFARIAN_WAR_CAMP)
    buffed_state = abilities.resolve_spell_outcomes(root, _cast(1), PRIMAL_STRENGTH_CARD)[0]
    buffed = next(iter(buffed_state.battlefields[0].units))
    assert combat.effective_might(buffed_state, buffed, "left", "attacker") == 11  # 2 +7 +1(TWC) +1(Assault)
    assert combat.effective_might(buffed_state, buffed, "left", "defender") == 10  # Assault doesn't apply


def test_primal_strength_buff_is_part_of_the_canonical_key():
    """Otherwise the transposition table would treat a buffed unit as the
    same position as an unbuffed one."""
    plain = make_state(base_units=frozenset({make_unit(1)}))
    buffed = make_state(base_units=frozenset({make_unit(1, might=9)}))
    assert canonical_key(plain) != canonical_key(buffed)


# --- Primal Strength: "Give a unit +7 Might this turn" ---


def test_primal_strength_buffs_a_unit_at_a_battlefield():
    unit = make_unit(1, might=2)
    root = make_state(left_units=frozenset({unit}), left_ctrl=0, hand=(PRIMAL_STRENGTH,))
    action = _cast(1)
    assert abilities.is_legal_play_spell(root, action, PRIMAL_STRENGTH_CARD)

    result = abilities.resolve_spell_outcomes(root, action, PRIMAL_STRENGTH_CARD)[0]
    buffed = next(iter(result.battlefields[0].units))
    assert buffed.might == 9  # printed 2 + 7, folded directly into Might


def test_primal_strength_buffs_a_unit_at_base():
    unit = make_unit(1, might=2)
    root = make_state(base_units=frozenset({unit}), hand=(PRIMAL_STRENGTH,))
    result = abilities.resolve_spell_outcomes(root, _cast(1), PRIMAL_STRENGTH_CARD)[0]
    assert next(iter(result.players[0].base_units)).might == 9


def test_primal_strength_can_target_either_players_unit():
    """"Give a unit" — the text doesn't restrict it to friendlies, so an
    enemy unit is a legal (if usually unwise) target."""
    enemy = make_unit(1, controller=1, might=2)
    root = make_state(left_units=frozenset({enemy}), left_ctrl=1, hand=(PRIMAL_STRENGTH,))
    assert abilities.is_legal_play_spell(root, _cast(1), PRIMAL_STRENGTH_CARD)


def test_primal_strength_rejects_a_nonexistent_target():
    root = make_state(base_units=frozenset({make_unit(1)}), hand=(PRIMAL_STRENGTH,))
    assert not abilities.is_legal_play_spell(root, _cast(99), PRIMAL_STRENGTH_CARD)


def test_primal_strength_turns_a_losing_attack_into_a_winning_one():
    """The reason the card matters for puzzles: a 2-Might attacker loses
    to a 5-Might defender outright, but buffed to 9 it kills without
    dying — the buff changes BOTH sides of that exchange at once."""
    attacker = make_unit(1, might=2)
    defender = make_unit(2, controller=1, might=5)
    unbuffed_state = make_state(left_units=frozenset({attacker}), left_ctrl=0)
    assert combat.effective_might(unbuffed_state, attacker, "left", "attacker") == 2
    # Unbuffed: attacker can't reach lethal (needs 5), defender can (needs 2).
    assert combat._apply_damage(
        unbuffed_state, "left", frozenset({attacker}), ((1, 5),), "attacker") == frozenset()
    defender_state = make_state(left_units=frozenset({defender}), left_ctrl=1)
    assert len(combat._apply_damage(
        defender_state, "left", frozenset({defender}), ((2, 2),), "defender")) == 1

    buffed = make_unit(1, might=9)
    buffed_state = make_state(left_units=frozenset({buffed}), left_ctrl=0)
    assert combat.effective_might(buffed_state, buffed, "left", "attacker") == 9
    # Buffed: attacker survives the same 5 damage and now out-damages the defender.
    assert len(combat._apply_damage(
        buffed_state, "left", frozenset({buffed}), ((1, 5),), "attacker")) == 1
    assert combat._apply_damage(
        defender_state, "left", frozenset({defender}), ((2, 9),), "defender") == frozenset()
