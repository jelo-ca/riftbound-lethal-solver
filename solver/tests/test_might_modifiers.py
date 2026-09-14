"""Temporary "+N Might this turn" modifiers.

A puzzle is a single turn, so "this turn" never expires inside one — the
modifier needs no duration tracking, just a field. What it DOES need is
to behave like Might everywhere, since Might is one stat doing two jobs:
raising it raises both the damage a unit deals and the damage needed to
kill it.
"""

from solver.engine import abilities, combat
from solver.engine.abilities import PRIMAL_STRENGTH
from solver.engine.actions import PlaySpell, RunePayment
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


def make_unit(instance_id, controller=0, might=2, keywords=frozenset(), might_bonus=0):
    return UnitInstance(card_id="ogn-010-298", instance_id=instance_id, controller=controller,
                         might=might, keywords=keywords, exhausted=False, damage=0,
                         is_token=False, might_bonus=might_bonus)


def make_state(base_units=frozenset(), left_units=frozenset(), left_ctrl=None, hand=()):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=hand, runes=RunePool(available=RUNES), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", left_ctrl, left_units, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def test_might_bonus_raises_damage_dealt():
    unit = make_unit(1, might=2, might_bonus=7)
    assert combat.effective_might(unit) == 9


def test_might_bonus_raises_the_lethal_threshold_too():
    """The half that's easy to forget: a buffed unit is correspondingly
    harder to kill, because it's the same stat."""
    unit = make_unit(1, might=2, might_bonus=7)
    assert len(combat._apply_damage(frozenset({unit}), ((1, 8),))) == 1  # 8 < 9, survives
    assert combat._apply_damage(frozenset({unit}), ((1, 9),)) == frozenset()


def test_might_bonus_stacks_with_keyword_and_battlefield_bonuses():
    from solver.engine.battlefields import TRIFARIAN_WAR_CAMP
    unit = make_unit(1, might=2, keywords=frozenset({"Assault"}), might_bonus=7)
    assert combat.effective_might(unit, "attacker", TRIFARIAN_WAR_CAMP) == 11  # 2 +7 +1 +1
    assert combat.effective_might(unit, "defender", TRIFARIAN_WAR_CAMP) == 10  # Assault doesn't apply


def test_might_bonus_is_part_of_the_canonical_key():
    """Otherwise the transposition table would treat a buffed unit as the
    same position as an unbuffed one."""
    plain = make_state(base_units=frozenset({make_unit(1)}))
    buffed = make_state(base_units=frozenset({make_unit(1, might_bonus=7)}))
    assert canonical_key(plain) != canonical_key(buffed)


# --- Primal Strength: "Give a unit +7 Might this turn" ---


def _cast(target_id):
    return PlaySpell(card_id=PRIMAL_STRENGTH, params=(target_id,), rune_payment=PAYMENT)


def test_primal_strength_buffs_a_unit_at_a_battlefield():
    unit = make_unit(1, might=2)
    root = make_state(left_units=frozenset({unit}), left_ctrl=0, hand=(PRIMAL_STRENGTH,))
    action = _cast(1)
    assert abilities.is_legal_play_spell(root, action, PRIMAL_STRENGTH_CARD)

    result = abilities.resolve_spell_outcomes(root, action, PRIMAL_STRENGTH_CARD)[0]
    buffed = next(iter(result.battlefields[0].units))
    assert buffed.might_bonus == 7
    assert buffed.might == 2  # printed Might is untouched; the bonus is separate
    assert combat.effective_might(buffed) == 9


def test_primal_strength_buffs_a_unit_at_base():
    unit = make_unit(1, might=2)
    root = make_state(base_units=frozenset({unit}), hand=(PRIMAL_STRENGTH,))
    result = abilities.resolve_spell_outcomes(root, _cast(1), PRIMAL_STRENGTH_CARD)[0]
    assert next(iter(result.players[0].base_units)).might_bonus == 7


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
    assert combat.effective_might(attacker, "attacker") == 2
    # Unbuffed: attacker can't reach lethal (needs 5), defender can (needs 2).
    assert combat._apply_damage(frozenset({attacker}), ((1, 5),), "attacker") == frozenset()
    assert len(combat._apply_damage(frozenset({defender}), ((2, 2),), "defender")) == 1

    buffed = attacker.__class__(**{**attacker.__dict__, "might_bonus": 7})
    assert combat.effective_might(buffed, "attacker") == 9
    # Buffed: attacker survives the same 5 damage and now out-damages the defender.
    assert len(combat._apply_damage(frozenset({buffed}), ((1, 5),), "attacker")) == 1
    assert combat._apply_damage(frozenset({defender}), ((2, 9),), "defender") == frozenset()
