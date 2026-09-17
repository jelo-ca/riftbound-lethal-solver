"""Direct-damage, removal and mass-buff spells.

All variations on helpers that already existed — the work here is the
per-card targeting rules, not new mechanics. Damage routes through
combat.deal_damage_to_unit, so it is EFFECT damage: no Shield or Assault
softens it, and any death it causes fires that unit's [Deathknell].
"""

from solver.engine import abilities
from solver.engine.abilities import (
    FALLING_COMET,
    FALLING_STAR,
    GRAND_STRATEGEM,
    HARNESSED_DRAGON,
    HEXTECH_RAY,
    REBUKE,
    RIPTIDE_REX,
)
from solver.engine.actions import PlaySpell, PlayUnit, RunePayment
from solver.engine.card_pool import card_def
from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    UnitInstance,
)


def unit(instance_id, controller=0, might=3, card_id="u"):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=frozenset(), exhausted=False, damage=0,
                         is_token=False)


def state_with(left=frozenset(), base=frozenset(), hand=(), runes=("Fury",) * 12):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base, hand=hand, runes=RunePool(available=runes), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, left, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def cast(card_id, params, state):
    card = card_def(card_id)
    payment = RunePayment(energy_runes=("Fury",) * card.energy_cost,
                          power_runes=(card.power_domain,) * card.power_cost)
    action = PlaySpell(card_id=card_id, params=params, rune_payment=payment)
    return abilities.resolve_spell_outcomes(state, action, card)[0]


def ids_at(state, index=0):
    return {u.instance_id for u in state.battlefields[index].units}


def test_hextech_ray_deals_three():
    st = state_with(left=frozenset({unit(1, might=4)}), hand=(HEXTECH_RAY,),
                     runes=("Fury",) * 4)
    out = cast(HEXTECH_RAY, (1,), st)
    assert next(u for u in out.battlefields[0].units if u.instance_id == 1).damage == 3


def test_falling_comet_kills_a_six_might_unit():
    st = state_with(left=frozenset({unit(1, might=6)}), hand=(FALLING_COMET,))
    assert 1 not in ids_at(cast(FALLING_COMET, (1,), st))


def test_falling_star_can_aim_both_instances_at_one_unit():
    """"Deal 3 to a unit. Deal 3 to a unit." is two separate instances, so
    stacking them on one 6-Might body kills it — collapsing the card into
    a single 6 would be the same here but wrong when they are split."""
    st = state_with(left=frozenset({unit(1, might=6)}), hand=(FALLING_STAR,))
    assert 1 not in ids_at(cast(FALLING_STAR, (1, 1), st))


def test_falling_star_can_split_across_two_units():
    st = state_with(left=frozenset({unit(1, might=3), unit(2, might=3)}), hand=(FALLING_STAR,))
    assert ids_at(cast(FALLING_STAR, (1, 2), st)) == set()


def test_falling_stars_second_instance_survives_the_first_killing_the_target():
    """The first 3 removes the unit, so the second finds nothing there —
    it must not crash or resurrect it."""
    st = state_with(left=frozenset({unit(1, might=3)}), hand=(FALLING_STAR,))
    assert ids_at(cast(FALLING_STAR, (1, 1), st)) == set()


def test_rebuke_returns_a_unit_to_hand():
    st = state_with(left=frozenset({unit(1, might=3)}), hand=(REBUKE,))
    out = cast(REBUKE, (1,), st)
    assert ids_at(out) == set()
    assert "u" in out.players[0].hand


def test_grand_strategem_buffs_every_friendly_unit_and_no_enemy():
    ours_bf, theirs, ours_base = unit(1), unit(2, controller=1), unit(3)
    st = state_with(left=frozenset({ours_bf, theirs}), base=frozenset({ours_base}),
                     hand=(GRAND_STRATEGEM,))
    out = cast(GRAND_STRATEGEM, (), st)
    by_id = {u.instance_id: u for u in out.battlefields[0].units}
    assert by_id[1].might == 8      # +5
    assert by_id[2].might == 3      # enemy untouched
    assert next(iter(out.players[0].base_units)).might == 8  # Base counts too


def test_riptide_rex_deals_six_on_arrival():
    card = card_def(RIPTIDE_REX)
    enemy = unit(2, controller=1, might=6)
    st = state_with(left=frozenset({unit(1), enemy}), hand=(RIPTIDE_REX,))
    payment = RunePayment(energy_runes=("Fury",) * card.energy_cost,
                          power_runes=(card.power_domain,) * card.power_cost)
    action = PlayUnit(card_id=RIPTIDE_REX, target_zone="left", rune_payment=payment,
                       trigger_params=(2,))
    out = abilities.resolve_unit_play_trigger_outcomes(st, action, card)[0]
    assert 2 not in ids_at(out)


def test_harnessed_dragon_cannot_kill_a_friendly_unit():
    """"Kill an ENEMY unit" — unlike Vengeance, which is unrestricted."""
    card = card_def(HARNESSED_DRAGON)
    st = state_with(left=frozenset({unit(1)}), hand=(HARNESSED_DRAGON,))
    payment = RunePayment(energy_runes=("Fury",) * card.energy_cost,
                          power_runes=(card.power_domain,) * card.power_cost)
    action = PlayUnit(card_id=HARNESSED_DRAGON, target_zone="left", rune_payment=payment,
                       trigger_params=(1,))
    assert not abilities.is_legal_unit_play_trigger(st, action, card)
