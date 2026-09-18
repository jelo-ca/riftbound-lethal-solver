"""The trash zone — starts empty at position setup (same convention as no
Main Deck), fills live during the turn as units die or spells resolve.

Four cards exercised here need only the zone itself, no new action shape:
Dr. Mundo (reads trash SIZE for Might), Vi Destructive (an activated
ability costed by recycling a trash card), Cemetery Attendant and Morbid
Return (both return a unit FROM trash TO hand). Stats come from
card_pool.card_def, never hand-written (non-negotiable #2).
"""

from solver import search
from solver.engine import abilities, combat, traits
from solver.engine.actions import ActivateAbility, PlaySpell, PlayUnit, RunePayment
from solver.engine.card_pool import card_def
from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    UnitInstance,
)

DR_MUNDO = traits.DR_MUNDO
VI = abilities.VI_DESTRUCTIVE
CEMETERY_ATTENDANT = abilities.CEMETERY_ATTENDANT
MORBID_RETURN = abilities.MORBID_RETURN
DEAD_UNIT = "ogn-052-298"  # Stalwart Poro — any real Unit printing works as trash filler
DEAD_SPELL = "ogn-004-298"  # Cleave — a real Spell printing, to prove Units-only filtering


def make_unit(card_id, instance_id, controller=0, might=3, exhausted=False):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=frozenset(), exhausted=exhausted, damage=0,
                         is_token=False)


def make_state(base_units=frozenset(), hand=(), left_units=frozenset(), runes=(), trash=()):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=hand, runes=RunePool(available=runes),
                        score=0, trash=trash),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0 if left_units else None, left_units, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


# --- Dr. Mundo: Might scales with trash size ---


def test_dr_mundos_might_scales_with_trash_size():
    mundo = make_unit(DR_MUNDO, 1, might=6)
    state = make_state(left_units=frozenset({mundo}), trash=(DEAD_UNIT,) * 3)
    assert traits.effective_might(state, mundo, "left") == 9


def test_dr_mundo_with_empty_trash_is_plain_might():
    mundo = make_unit(DR_MUNDO, 1, might=6)
    state = make_state(left_units=frozenset({mundo}))
    assert traits.effective_might(state, mundo, "left") == 6


# --- Vi Destructive: recycle 1 from trash as a cost ---


def test_vi_destructive_needs_a_card_in_trash():
    vi = make_unit(VI, 1, might=3)
    state = make_state(left_units=frozenset({vi}))
    action = ActivateAbility(source_id=1, ability_id=VI, params=(DEAD_UNIT,), rune_payment=None)
    is_legal, _, _ = abilities.ABILITY_EFFECTS[VI]
    assert not is_legal(state, action)


def test_vi_destructive_recycles_a_card_for_might():
    vi = make_unit(VI, 1, might=3)
    state = make_state(left_units=frozenset({vi}), trash=(DEAD_UNIT,))
    action = ActivateAbility(source_id=1, ability_id=VI, params=(DEAD_UNIT,), rune_payment=None)
    is_legal, effect, _ = abilities.ABILITY_EFFECTS[VI]
    assert is_legal(state, action)
    result = effect(state, action)
    assert result.players[0].trash == ()
    moved = next(iter(result.battlefields[0].units))
    assert moved.might == 4


def test_vi_destructive_reachable_through_legal_actions():
    vi = make_unit(VI, 1, might=3, exhausted=False)
    state = make_state(left_units=frozenset({vi}), trash=(DEAD_UNIT,))
    cards = {VI: card_def(VI)}
    action = next(a for a in search.legal_actions(state, cards)
                  if isinstance(a, ActivateAbility) and a.ability_id == VI)
    result = search.apply(state, action, cards)
    assert result.players[0].trash == ()
    assert next(iter(result.battlefields[0].units)).might == 4


# --- Cemetery Attendant / Morbid Return: return a unit from trash to hand ---


def test_only_units_are_offered_from_trash():
    """A spell that landed in trash isn't a legal target for "return a
    unit" — filtered by card_pool.card_def's card_type, not by guessing."""
    assert abilities._units_in_trash(
        make_state(trash=(DEAD_UNIT, DEAD_SPELL)), 0) == [DEAD_UNIT]


def test_cemetery_attendant_returns_a_unit_from_trash():
    card = card_def(CEMETERY_ATTENDANT)
    state = make_state(hand=(CEMETERY_ATTENDANT,), trash=(DEAD_UNIT,),
                        runes=("Chaos", "Fury", "Fury", "Fury"))
    payment = RunePayment(energy_runes=("Fury",) * 3, power_runes=("Chaos",))
    action = PlayUnit(card_id=CEMETERY_ATTENDANT, target_zone="base", rune_payment=payment,
                       trigger_params=(DEAD_UNIT,))
    assert abilities.is_legal_unit_play_trigger(state, action, card)
    [result] = abilities.resolve_unit_play_trigger_outcomes(state, action, card)
    assert result.players[0].trash == ()
    assert DEAD_UNIT in result.players[0].hand


def test_cemetery_attendant_with_no_units_in_trash_offers_no_triggered_form():
    """Mandatory but unreachable with no target — same shape as Harnessed
    Dragon against an empty board, not a fizzled no-op play."""
    card = card_def(CEMETERY_ATTENDANT)
    state = make_state(hand=(CEMETERY_ATTENDANT,), runes=("Chaos", "Fury", "Fury", "Fury"))
    cards = {CEMETERY_ATTENDANT: card}
    actions = [a for a in search.legal_actions(state, cards)
               if getattr(a, "card_id", None) == CEMETERY_ATTENDANT]
    assert actions == []


def test_morbid_return_reachable_through_legal_actions():
    card = card_def(MORBID_RETURN)
    state = make_state(hand=(MORBID_RETURN,), trash=(DEAD_UNIT,), runes=("Fury", "Fury"))
    cards = {MORBID_RETURN: card}
    action = next(a for a in search.legal_actions(state, cards)
                  if isinstance(a, PlaySpell) and a.card_id == MORBID_RETURN)
    [result] = abilities.resolve_spell_outcomes(state, action, card)
    # DEAD_UNIT left trash for hand; Morbid Return itself lands in trash
    # as a resolved spell (apply_play_spell_cost) — the two cross paths.
    assert result.players[0].trash == (MORBID_RETURN,)
    assert DEAD_UNIT in result.players[0].hand
