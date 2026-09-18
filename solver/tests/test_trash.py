"""The trash zone — starts empty at position setup (same convention as no
Main Deck), fills live during the turn as units die or spells resolve.

Four cards exercised here need only the zone itself, no new action shape:
Dr. Mundo (reads trash SIZE for Might), Vi Destructive (an activated
ability costed by recycling a trash card), Cemetery Attendant and Morbid
Return (both return a unit FROM trash TO hand). Stats come from
card_pool.card_def, never hand-written (non-negotiable #2).
"""

from solver import search
from solver.engine import abilities, combat, gear as gear_module, traits
from solver.engine.actions import ActivateAbility, PlaySpell, PlayUnit, RunePayment
from solver.engine.card_pool import card_def
from solver.engine.state import (
    BattlefieldState,
    GameState,
    GearInstance,
    PlayerState,
    RunePool,
    UnitInstance,
)

DR_MUNDO = traits.DR_MUNDO
VI = abilities.VI_DESTRUCTIVE
CEMETERY_ATTENDANT = abilities.CEMETERY_ATTENDANT
MORBID_RETURN = abilities.MORBID_RETURN
SOULGORGER = abilities.SOULGORGER
THE_HARROWING = abilities.THE_HARROWING
SPECTRAL_MATRON = abilities.SPECTRAL_MATRON
SALVAGE = abilities.SALVAGE
TOO_EXPENSIVE_UNIT = "ogn-215-298"  # Petty Officer — 5 Energy, over Spectral Matron's 3-cap
DEAD_UNIT = "ogn-052-298"  # Stalwart Poro — any real Unit printing works as trash filler
DEAD_SPELL = "ogn-004-298"  # Cleave — a real Spell printing, to prove Units-only filtering
TRIGGERED_UNIT = "ogn-136-298"  # Pit Rookie — a real Unit WITH its own UNIT_PLAY_TRIGGERS entry


def make_unit(card_id, instance_id, controller=0, might=3, exhausted=False):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=frozenset(), exhausted=exhausted, damage=0,
                         is_token=False)


def make_state(base_units=frozenset(), hand=(), left_units=frozenset(), runes=(), trash=(),
               gear=frozenset(), enemy_gear=frozenset()):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=hand, runes=RunePool(available=runes),
                        score=0, trash=trash, gear=gear),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0,
                        gear=enemy_gear),
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


# --- Soulgorger / The Harrowing: play a unit from trash, ignoring Energy ---


def test_soulgorger_decline_is_still_legal():
    card = card_def(SOULGORGER)
    state = make_state(hand=(SOULGORGER,), trash=(VI,), runes=("Fury",) * 8 + ("Chaos",) * 2)
    action = PlayUnit(card_id=SOULGORGER, target_zone="base", trigger_params=(),
                       rune_payment=RunePayment(energy_runes=("Fury",) * 8, power_runes=("Chaos", "Chaos")))
    assert abilities.is_legal_unit_play_trigger(state, action, card)


def test_soulgorger_replays_a_unit_ignoring_its_energy_cost():
    card = card_def(SOULGORGER)
    state = make_state(hand=(SOULGORGER,), trash=(VI,), runes=("Fury",) * 9 + ("Chaos",) * 2)
    cards = {SOULGORGER: card}
    action = next(a for a in search.legal_actions(state, cards)
                  if isinstance(a, PlayUnit) and a.card_id == SOULGORGER
                  and a.trigger_params and a.trigger_params[0] == VI)
    [result] = abilities.resolve_unit_play_trigger_outcomes(state, action, card)
    assert result.players[0].trash == ()
    replayed = [u for u in result.players[0].base_units if u.card_id == VI]
    assert len(replayed) == 1
    assert replayed[0].exhausted is True  # no [Accelerate] variant offered on replay


def test_soulgorger_cannot_replay_a_unit_with_its_own_play_trigger():
    """Restrictive by design (see play_unit_from_trash's docstring): a
    replayed unit's own "when you play me" text is never dispatched
    through this path, so a card that has one is never offered."""
    card = card_def(SOULGORGER)
    state = make_state(hand=(SOULGORGER,), trash=(TRIGGERED_UNIT,), runes=("Fury",) * 9 + ("Chaos",) * 2)
    cards = {SOULGORGER: card}
    actions = [a for a in search.legal_actions(state, cards) if isinstance(a, PlayUnit)
               and a.card_id == SOULGORGER and a.trigger_params]
    assert actions == []


def test_the_harrowing_replays_a_unit_paying_from_what_the_spell_leaves_behind():
    card = card_def(THE_HARROWING)
    state = make_state(hand=(THE_HARROWING,), trash=(VI,), runes=("Fury",) * 8 + ("Chaos",) * 2)
    cards = {THE_HARROWING: card}
    action = next(a for a in search.legal_actions(state, cards)
                  if isinstance(a, PlaySpell) and a.card_id == THE_HARROWING)
    [result] = abilities.resolve_spell_outcomes(state, action, card)
    assert any(u.card_id == VI for u in result.players[0].base_units)
    assert THE_HARROWING in result.players[0].trash
    assert VI not in result.players[0].trash


# --- Spectral Matron: play a unit from trash, ignoring its WHOLE cost ---


def test_spectral_matron_replays_a_unit_for_free():
    card = card_def(SPECTRAL_MATRON)
    state = make_state(hand=(SPECTRAL_MATRON,), trash=(DEAD_UNIT,), runes=("Fury",) * 4 + ("Order",) * 2)
    cards = {SPECTRAL_MATRON: card}
    action = next(a for a in search.legal_actions(state, cards)
                  if isinstance(a, PlayUnit) and a.card_id == SPECTRAL_MATRON
                  and a.trigger_params and a.trigger_params[0] == DEAD_UNIT)
    [result] = abilities.resolve_unit_play_trigger_outcomes(state, action, card)
    assert result.players[0].trash == ()
    replayed = [u for u in result.players[0].base_units if u.card_id == DEAD_UNIT]
    assert len(replayed) == 1
    # Nothing spent on the replay: only Spectral Matron's own cost is gone.
    assert result.players[0].runes.energy_spent == 4
    assert result.players[0].runes.power_spent == ("Order",) * 2


def test_spectral_matron_cannot_replay_a_unit_over_the_cost_cap():
    card = card_def(SPECTRAL_MATRON)
    state = make_state(hand=(SPECTRAL_MATRON,), trash=(TOO_EXPENSIVE_UNIT,),
                        runes=("Fury",) * 4 + ("Order",) * 2)
    cards = {SPECTRAL_MATRON: card}
    actions = [a for a in search.legal_actions(state, cards)
               if isinstance(a, PlayUnit) and a.card_id == SPECTRAL_MATRON and a.trigger_params]
    assert actions == []


# --- Salvage: "[Action] You may kill a gear. Draw 1." ---


def _ready_gear(card_id, instance_id):
    return GearInstance(card_id=card_id, instance_id=instance_id, exhausted=False)


def test_salvage_decline_is_still_legal():
    """"Draw 1" alone (a no-op) is always a legal resolution."""
    card = card_def(SALVAGE)
    state = make_state(hand=(SALVAGE,), runes=("Fury", "Fury", "Order"),
                        gear=frozenset({_ready_gear(gear_module.ORB_OF_REGRET, 50)}))
    action = PlaySpell(card_id=SALVAGE, params=(),
                        rune_payment=RunePayment(energy_runes=("Fury", "Fury"), power_runes=("Order",)))
    assert abilities.is_legal_play_spell(state, action, card)
    [result] = abilities.resolve_spell_outcomes(state, action, card)
    assert len(result.players[0].gear) == 1  # untouched


def test_salvage_kills_a_gear_and_lands_it_in_trash():
    card = card_def(SALVAGE)
    piece = _ready_gear(gear_module.ORB_OF_REGRET, 50)
    state = make_state(hand=(SALVAGE,), runes=("Fury", "Fury", "Order"), gear=frozenset({piece}))
    action = PlaySpell(card_id=SALVAGE, params=(50,),
                        rune_payment=RunePayment(energy_runes=("Fury", "Fury"), power_runes=("Order",)))
    assert abilities.is_legal_play_spell(state, action, card)
    [result] = abilities.resolve_spell_outcomes(state, action, card)
    assert result.players[0].gear == frozenset()
    assert gear_module.ORB_OF_REGRET in result.players[0].trash
    assert SALVAGE in result.players[0].trash  # the resolved spell itself


def test_salvage_can_kill_the_opponents_gear():
    """"A gear" is unqualified — either player's, same convention as Orb
    of Regret's "a unit"."""
    card = card_def(SALVAGE)
    piece = _ready_gear(gear_module.THE_SYREN, 60)
    state = make_state(hand=(SALVAGE,), runes=("Fury", "Fury", "Order"), enemy_gear=frozenset({piece}))
    action = PlaySpell(card_id=SALVAGE, params=(60,),
                        rune_payment=RunePayment(energy_runes=("Fury", "Fury"), power_runes=("Order",)))
    assert abilities.is_legal_play_spell(state, action, card)
    [result] = abilities.resolve_spell_outcomes(state, action, card)
    assert result.players[1].gear == frozenset()
    assert gear_module.THE_SYREN in result.players[1].trash


def test_salvage_can_target_treasure_trove_and_fires_its_leaves_board_reaction():
    """Treasure Trove's "when this leaves the board, ...channel 1 rune
    exhausted" used to be dropped on the floor (no hook existed to fire
    it), so Salvage excluded it as a kill target. Both gaps are closed
    now (gear.fire_gear_leaves_board_reactions, called from
    actions.kill_gear) — Salvage can target it like any other Gear, and
    the reaction actually fires."""
    card = card_def(SALVAGE)
    piece = _ready_gear(gear_module.TREASURE_TROVE, 70)
    state = make_state(hand=(SALVAGE,), runes=("Fury", "Fury", "Order"), gear=frozenset({piece}))
    action = PlaySpell(card_id=SALVAGE, params=(70,),
                        rune_payment=RunePayment(energy_runes=("Fury", "Fury"), power_runes=("Order",)))
    assert abilities.is_legal_play_spell(state, action, card)
    [result] = abilities.resolve_spell_outcomes(state, action, card)
    assert result.players[0].gear == frozenset()
    assert gear_module.TREASURE_TROVE in result.players[0].trash
    # One new domain-less rune joined the pool (RULING 1), arriving
    # already-exhausted — the starting three runes are untouched here.
    assert len(result.players[0].runes.available) == 4
    assert None in result.players[0].runes.available
    assert result.players[0].runes.energy_spent >= 1  # the new rune's own Energy is spent


def test_salvage_can_target_scrapheap_since_its_own_reaction_is_proven_inert():
    """Scrapheap ALSO reacts to its own death ("...or killed, draw 1"),
    but coverage.py clears its whole card as inert (every trigger is the
    same no-op draw) — so unlike Treasure Trove it needs no exclusion."""
    card = card_def(SALVAGE)
    piece = _ready_gear("ogn-182-298", 71)  # Scrapheap
    state = make_state(hand=(SALVAGE,), runes=("Fury", "Fury", "Order"), gear=frozenset({piece}))
    action = PlaySpell(card_id=SALVAGE, params=(71,),
                        rune_payment=RunePayment(energy_runes=("Fury", "Fury"), power_runes=("Order",)))
    assert abilities.is_legal_play_spell(state, action, card)
    [result] = abilities.resolve_spell_outcomes(state, action, card)
    assert result.players[0].gear == frozenset()
    assert "ogn-182-298" in result.players[0].trash


def test_salvage_reachable_through_legal_actions():
    card = card_def(SALVAGE)
    piece = _ready_gear(gear_module.ORB_OF_REGRET, 50)
    state = make_state(hand=(SALVAGE,), runes=("Fury", "Fury", "Order"), gear=frozenset({piece}))
    cards = {SALVAGE: card}
    action = next(a for a in search.legal_actions(state, cards)
                  if isinstance(a, PlaySpell) and a.card_id == SALVAGE and a.params == (50,))
    [result] = abilities.resolve_spell_outcomes(state, action, card)
    assert result.players[0].gear == frozenset()
    assert gear_module.ORB_OF_REGRET in result.players[0].trash
