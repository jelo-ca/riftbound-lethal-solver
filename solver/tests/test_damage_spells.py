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


# --- trait grants, readying, and multi-target choices ---

from solver.engine.abilities import (  # noqa: E402
    BACK_TO_BACK,
    CLEAVE,
    DANGEROUS_DUO,
    FIRST_MATE,
    KINKOU_MONK,
    MADDENED_MARAUDER,
    SINGULARITY,
    is_legal_unit_play_trigger,
    resolve_unit_play_trigger_outcomes,
)
from solver.engine.traits import resolved_traits  # noqa: E402


def play_unit(card_id, zone, trigger_params, st):
    card = card_def(card_id)
    payment = RunePayment(energy_runes=("Fury",) * card.energy_cost,
                          power_runes=(card.power_domain,) * card.power_cost)
    action = PlayUnit(card_id=card_id, target_zone=zone, rune_payment=payment,
                       trigger_params=trigger_params)
    return card, action


def test_cleave_grants_assault_which_only_counts_while_attacking():
    """[Assault 3] is a trait, not flat Might — it must be worth nothing on
    defence, which is why it can't just be added to `might`."""
    from solver.engine import combat
    st = state_with(left=frozenset({unit(1, might=3)}), hand=(CLEAVE,), runes=("Fury",))
    out = cast(CLEAVE, (1,), st)
    target = next(u for u in out.battlefields[0].units if u.instance_id == 1)
    assert "Assault 3" in resolved_traits(out, target, "left")
    assert combat.effective_might(out, target, "left", "attacker") == 6
    assert combat.effective_might(out, target, "left", "defender") == 3


def test_singularity_targets_must_be_distinct():
    """"Each of up to two units" — unlike Falling Star, which is two
    separate instances and may double up."""
    st = state_with(left=frozenset({unit(1, might=6)}), hand=(SINGULARITY,))
    card = card_def(SINGULARITY)
    payment = RunePayment(energy_runes=("Fury",) * card.energy_cost,
                          power_runes=(card.power_domain,) * card.power_cost)
    doubled = PlaySpell(card_id=SINGULARITY, params=(1, 1), rune_payment=payment)
    assert not abilities.is_legal_play_spell(st, doubled, card)


def test_singularity_may_hit_nobody():
    st = state_with(left=frozenset({unit(1, might=6)}), hand=(SINGULARITY,))
    assert ids_at(cast(SINGULARITY, (), st)) == {1}


def test_back_to_back_needs_two_distinct_friendly_units():
    ours, theirs = unit(1), unit(2, controller=1)
    st = state_with(left=frozenset({ours, theirs}), hand=(BACK_TO_BACK,))
    card = card_def(BACK_TO_BACK)
    payment = RunePayment(energy_runes=("Fury",) * card.energy_cost, power_runes=())
    assert not abilities.is_legal_play_spell(
        st, PlaySpell(card_id=BACK_TO_BACK, params=(1, 2), rune_payment=payment), card)  # enemy
    assert not abilities.is_legal_play_spell(
        st, PlaySpell(card_id=BACK_TO_BACK, params=(1, 1), rune_payment=payment), card)  # same twice


def test_first_mate_readies_another_unit():
    exhausted = UnitInstance(card_id="u", instance_id=1, controller=0, might=3,
                              keywords=frozenset(), exhausted=True, damage=0, is_token=False)
    st = state_with(left=frozenset({exhausted}), hand=(FIRST_MATE,))
    card, action = play_unit(FIRST_MATE, "left", (1,), st)
    out = resolve_unit_play_trigger_outcomes(st, action, card)[0]
    assert next(u for u in out.battlefields[0].units if u.instance_id == 1).exhausted is False


def test_first_mate_cannot_ready_itself():
    """It enters exhausted, so 'another unit' is what stops it undoing
    that — the loophole worth closing explicitly."""
    from solver.engine.actions import next_instance_id
    st = state_with(left=frozenset({unit(1)}), hand=(FIRST_MATE,))
    card, _ = play_unit(FIRST_MATE, "left", (), st)
    own = next_instance_id(st)
    _, self_target = play_unit(FIRST_MATE, "left", (own,), st)
    assert not is_legal_unit_play_trigger(st, self_target, card)


def test_kinkou_monk_may_buff_zero_one_or_two():
    a, b = unit(1), unit(2)
    st = state_with(left=frozenset({a, b}), hand=(KINKOU_MONK,))
    card, action = play_unit(KINKOU_MONK, "left", (1, 2), st)
    out = resolve_unit_play_trigger_outcomes(st, action, card)[0]
    assert all(u.buffed for u in out.battlefields[0].units if u.instance_id in (1, 2))

    _, none_action = play_unit(KINKOU_MONK, "left", (), st)
    out_none = resolve_unit_play_trigger_outcomes(st, none_action, card)[0]
    assert not any(u.buffed for u in out_none.battlefields[0].units)


def test_maddened_marauder_stays_unregistered_because_of_the_zone_model():
    """A real structural blocker, pinned so it can't be quietly forgotten.

    "Move a unit from a battlefield to its base" works for our own units
    and is unrepresentable for an enemy's: Zone is "base" or a battlefield
    id, with no way to express WHOSE base. Charm's docstring flagged the
    same gap earlier. The card is implemented apart from the destination
    and stays out of the registry until the zone model can name both."""
    from solver.engine.abilities import UNIT_PLAY_TRIGGERS
    from solver.engine import coverage
    assert MADDENED_MARAUDER not in UNIT_PLAY_TRIGGERS
    assert coverage.classify(MADDENED_MARAUDER) == "blocking"


# --- doubling, mass effects, and simultaneous mutual damage ---

from solver.engine.abilities import CHALLENGE, LAST_STAND, UNCHECKED_POWER  # noqa: E402


def test_last_stand_doubles_printed_might():
    st = state_with(left=frozenset({unit(1, might=4)}), hand=(LAST_STAND,))
    out = cast(LAST_STAND, (1,), st)
    assert next(u for u in out.battlefields[0].units if u.instance_id == 1).might == 8


def test_last_stand_grants_temporary_even_though_it_is_inert():
    """Granted for fidelity: [Temporary] kills at the start of a Beginning
    Phase a single turn never reaches, so it does nothing here — but the
    card says it, and recording it costs nothing."""
    st = state_with(left=frozenset({unit(1, might=4)}), hand=(LAST_STAND,))
    out = cast(LAST_STAND, (1,), st)
    target = next(u for u in out.battlefields[0].units if u.instance_id == 1)
    assert "Temporary" in resolved_traits(out, target, "left")


def test_unchecked_power_exhausts_our_units_before_the_damage():
    """Exhausting our own side is a real cost, not flavour — it can strip
    the very unit that would have used the opening."""
    survivor = unit(1, might=20)          # survives 12
    enemy = unit(2, controller=1, might=6)  # does not
    st = state_with(left=frozenset({survivor, enemy}), hand=(UNCHECKED_POWER,))
    out = cast(UNCHECKED_POWER, (), st)
    ours = next(u for u in out.battlefields[0].units if u.instance_id == 1)
    assert ours.exhausted is True
    assert 2 not in ids_at(out)


def test_challenge_damage_is_simultaneous():
    """Both Mights are read before either lands, so a unit that dies still
    deals its damage. Resolving one at a time would let the first kill
    silence the second — here that would wrongly leave our 5-Might unit
    alive against a 5-Might enemy."""
    ours, theirs = unit(1, might=5), unit(2, controller=1, might=5)
    st = state_with(left=frozenset({ours, theirs}), hand=(CHALLENGE,))
    out = cast(CHALLENGE, (1, 2), st)
    assert ids_at(out) == set()  # both die


def test_challenge_requires_one_of_each_side():
    ours, theirs = unit(1, might=5), unit(2, controller=1, might=5)
    st = state_with(left=frozenset({ours, theirs}), hand=(CHALLENGE,))
    card = card_def(CHALLENGE)
    payment = RunePayment(energy_runes=("Fury",) * card.energy_cost,
                          power_runes=(card.power_domain,) * card.power_cost)
    both_ours = PlaySpell(card_id=CHALLENGE, params=(1, 1), rune_payment=payment)
    assert not abilities.is_legal_play_spell(st, both_ours, card)


# --- board-conditional buff, gear buff, and the Snapvine trade ---

from solver.engine.abilities import CARNIVOROUS_SNAPVINE, EN_GARDE  # noqa: E402


def test_en_garde_pays_double_when_the_unit_stands_alone():
    solo = unit(1, might=3)
    st = state_with(left=frozenset({solo}), hand=(EN_GARDE,), runes=("Fury",))
    out = cast(EN_GARDE, (1,), st)
    assert next(u for u in out.battlefields[0].units if u.instance_id == 1).might == 5  # +2


def test_en_garde_pays_single_with_a_friend_present():
    """"The only unit you control there" counts OUR units in that zone —
    so a companion halves the payoff."""
    st = state_with(left=frozenset({unit(1, might=3), unit(2, might=3)}),
                     hand=(EN_GARDE,), runes=("Fury",))
    out = cast(EN_GARDE, (1,), st)
    assert next(u for u in out.battlefields[0].units if u.instance_id == 1).might == 4  # +1


def test_en_garde_ignores_enemy_units_when_counting_alone():
    st = state_with(left=frozenset({unit(1, might=3), unit(2, controller=1, might=3)}),
                     hand=(EN_GARDE,), runes=("Fury",))
    out = cast(EN_GARDE, (1,), st)
    assert next(u for u in out.battlefields[0].units if u.instance_id == 1).might == 5


def test_snapvine_loses_the_exchange_to_a_bigger_body():
    """The Snapvine is one side of its own exchange, so the trade is
    decided by Mights. At 6 against a 7, it deals 6 (not lethal) and takes
    7 (lethal) — it dies and the enemy walks away damaged."""
    from solver.engine.abilities import resolve_unit_play_trigger_outcomes
    big = unit(2, controller=1, might=7)
    st = state_with(left=frozenset({unit(1), big}), hand=(CARNIVOROUS_SNAPVINE,))
    card, action = play_unit(CARNIVOROUS_SNAPVINE, "left", (2,), st)
    out = resolve_unit_play_trigger_outcomes(st, action, card)[0]
    survivor = next(u for u in out.battlefields[0].units if u.instance_id == 2)
    assert survivor.damage == 6
    assert not any(u.card_id == CARNIVOROUS_SNAPVINE for u in out.battlefields[0].units)


def test_snapvine_kills_anything_its_own_size_or_smaller():
    from solver.engine.abilities import resolve_unit_play_trigger_outcomes
    same_size = unit(2, controller=1, might=6)
    st = state_with(left=frozenset({unit(1), same_size}), hand=(CARNIVOROUS_SNAPVINE,))
    card, action = play_unit(CARNIVOROUS_SNAPVINE, "left", (2,), st)
    out = resolve_unit_play_trigger_outcomes(st, action, card)[0]
    assert 2 not in ids_at(out)  # both die — simultaneous, so it still deals its 6


def test_arena_bar_only_buffs_an_exhausted_unit():
    """The exhausted requirement is the card's whole restriction."""
    from solver.engine import gear
    from solver.engine.actions import ActivateAbility
    from solver.engine.state import GearInstance

    ready = unit(1, might=3)
    tired = UnitInstance(card_id="u", instance_id=2, controller=0, might=3,
                          keywords=frozenset(), exhausted=True, damage=0, is_token=False)
    st = state_with(left=frozenset({ready, tired}))
    st = st.__class__(**{**st.__dict__, "players": (
        st.players[0].__class__(**{**st.players[0].__dict__,
                                   "gear": frozenset({GearInstance(card_id="ogn-124-298", instance_id=9)})}),
        st.players[1])})
    assert not gear.is_legal_gear_ability(
        st, ActivateAbility(source_id=9, ability_id="ogn-124-298", params=(1,), rune_payment=None))
    assert gear.is_legal_gear_ability(
        st, ActivateAbility(source_id=9, ability_id="ogn-124-298", params=(2,), rune_payment=None))
