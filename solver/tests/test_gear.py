"""Gear — standalone permanents with activated abilities.

The rules under test were derived from the printed text of all 30 Origins
Gear cards, not by analogy to units. The two that matter most and are
easiest to get backwards:

  * Gear does NOT attach to a unit (no printing says attach/equip), so a
    unit dying leaves it untouched;
  * Gear enters READY, the opposite of units — Iron Ballista has to print
    "This enters exhausted" precisely because that isn't the default.
"""

import dataclasses

from solver.engine import gear
from solver.engine.actions import (
    ActivateAbility,
    PlayGear,
    PlaySpell,
    RunePayment,
    apply_play_gear,
    is_legal_play_gear,
    next_instance_id,
)
from solver.engine.cards import CardDef
from solver.engine.state import (
    BattlefieldState,
    GameState,
    GearInstance,
    PlayerState,
    RunePool,
    UnitInstance,
    canonical_key,
)

BALLISTA = CardDef(card_id=gear.IRON_BALLISTA, card_type="Gear", energy_cost=3,
                    power_cost=0, gear_enters_exhausted=True)
ORB = CardDef(card_id=gear.ORB_OF_REGRET, card_type="Gear", energy_cost=1, power_cost=0)
SYREN = CardDef(card_id=gear.THE_SYREN, card_type="Gear", energy_cost=2, power_cost=0)


def make_unit(instance_id, controller=0, might=3, exhausted=False, card_id="u"):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=frozenset(), exhausted=exhausted, damage=0,
                         is_token=False)


def make_state(gear_pieces=frozenset(), hand=(), runes=(), left_units=frozenset(),
               base_units=frozenset(), left_ctrl=None):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=hand, runes=RunePool(available=runes),
                        score=0, gear=gear_pieces),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", left_ctrl, left_units, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def ready_gear(card_id, instance_id=50):
    return GearInstance(card_id=card_id, instance_id=instance_id, exhausted=False)


# --- playing Gear ---


def test_gear_enters_ready_by_default():
    """The opposite of units (rule 143.4.a). Getting this backwards would
    make every Gear unusable the turn it lands."""
    state = make_state(hand=(gear.THE_SYREN,), runes=("Fury", "Fury"))
    action = PlayGear(card_id=gear.THE_SYREN,
                       rune_payment=RunePayment(energy_runes=("Fury", "Fury"), power_runes=()))
    assert is_legal_play_gear(state, action, SYREN)
    result = apply_play_gear(state, action, SYREN)
    placed = next(iter(result.players[0].gear))
    assert placed.exhausted is False
    assert gear.THE_SYREN not in result.players[0].hand


def test_gear_that_says_it_enters_exhausted_does():
    state = make_state(hand=(gear.IRON_BALLISTA,), runes=("Fury",) * 3)
    action = PlayGear(card_id=gear.IRON_BALLISTA,
                       rune_payment=RunePayment(energy_runes=("Fury",) * 3, power_runes=()))
    result = apply_play_gear(state, action, BALLISTA)
    assert next(iter(result.players[0].gear)).exhausted is True


# --- Gear "when you play this" triggers: Forge of the Future ---
#
# The first Gear play-trigger — Forge of the Future's mandatory "play a
# 1 Might Recruit token at your base." Stats come from card_pool.card_def,
# never hand-written (non-negotiable #2).


from solver import search
from solver.engine import abilities
from solver.engine.card_pool import card_def

FORGE = abilities.FORGE_OF_THE_FUTURE


def test_forge_of_the_future_mints_a_token_on_play():
    card = card_def(FORGE)
    state = make_state(hand=(FORGE,), runes=("Fury", "Fury"))
    action = PlayGear(card_id=FORGE, trigger_params=("mint",),
                       rune_payment=RunePayment(energy_runes=("Fury", "Fury"), power_runes=()))
    assert abilities.is_legal_gear_play_trigger(state, action, card)
    [result] = abilities.resolve_gear_play_trigger_outcomes(state, action, card)
    assert any(g.card_id == FORGE for g in result.players[0].gear)
    tokens = [u for u in result.players[0].base_units if u.card_id == abilities.RECRUIT_TOKEN]
    assert len(tokens) == 1
    assert tokens[0].might == 1


def test_the_bare_play_form_is_not_offered_since_the_trigger_is_mandatory():
    card = card_def(FORGE)
    state = make_state(hand=(FORGE,), runes=("Fury", "Fury"))
    cards = {FORGE: card}
    actions = [a for a in search.legal_actions(state, cards) if getattr(a, "card_id", None) == FORGE]
    assert all(a.trigger_params == ("mint",) for a in actions)


def test_forge_of_the_future_reachable_through_legal_actions():
    """search.legal_actions -> search.apply's NotImplementedError path (a
    triggered PlayGear, like a triggered PlayUnit, has to route through
    solve()'s list-returning outcomes) — the guard against "registered but
    unreachable"."""
    card = card_def(FORGE)
    state = make_state(hand=(FORGE,), runes=("Fury", "Fury"))
    cards = {FORGE: card}
    play = next(a for a in search.legal_actions(state, cards)
                if getattr(a, "card_id", None) == FORGE)
    assert play.trigger_params == ("mint",)
    outcomes = abilities.resolve_gear_play_trigger_outcomes(state, play, card)
    assert len(outcomes) == 1
    tokens = [u for u in outcomes[0].players[0].base_units if u.card_id == abilities.RECRUIT_TOKEN]
    assert len(tokens) == 1


def test_playing_gear_counts_as_playing_a_card():
    """Legion and anything else keying off cards_played_this_turn has to
    see it."""
    state = make_state(hand=(gear.ORB_OF_REGRET,), runes=("Fury",))
    action = PlayGear(card_id=gear.ORB_OF_REGRET,
                       rune_payment=RunePayment(energy_runes=("Fury",), power_runes=()))
    assert apply_play_gear(state, action, ORB).cards_played_this_turn == 1


def test_gear_shares_the_unit_instance_id_space():
    """Pack of Wonders returns "another friendly gear, unit, or Hidden
    card" by target, so the ids must not collide."""
    state = make_state(gear_pieces=frozenset({ready_gear(gear.ORB_OF_REGRET, 7)}),
                        base_units=frozenset({make_unit(3)}))
    assert next_instance_id(state) == 8


def test_gear_is_part_of_the_canonical_key():
    """An exhausted Gear is a different position from a ready one — if it
    weren't in the key, the transposition table would prune real lines."""
    ready = make_state(gear_pieces=frozenset({ready_gear(gear.ORB_OF_REGRET)}))
    spent = make_state(gear_pieces=frozenset({
        GearInstance(card_id=gear.ORB_OF_REGRET, instance_id=50, exhausted=True)}))
    assert canonical_key(ready) != canonical_key(spent)


# --- The Seals: "Exhaust: [Reaction] Add 1 [domain] rune." (RULING 2) ---
#
# A card that STATES its domain gets a normal, real-domain rune — none of
# RULING 1's domain-less machinery — and nothing says "exhausted," so it
# arrives ready, immediately able to pay Energy AND Power of its domain.


def test_seal_of_rage_adds_a_ready_fury_rune():
    state = make_state(gear_pieces=frozenset({ready_gear(gear.SEAL_OF_RAGE)}))
    action = _activate(gear.SEAL_OF_RAGE, ())
    assert gear.is_legal_gear_ability(state, action)
    result = gear.apply_gear_ability(state, action)
    from solver.engine.state import energy_capacity, power_capacity
    assert result.players[0].runes.available == ("Fury",)
    assert energy_capacity(result.players[0].runes) == 1  # ready, not exhausted
    assert power_capacity(result.players[0].runes, "Fury") == 1
    assert next(iter(result.players[0].gear)).exhausted is True  # its own cost is spent


def test_every_seal_adds_its_own_stated_domain():
    for seal_id, domain in gear.SEAL_DOMAINS.items():
        state = make_state(gear_pieces=frozenset({ready_gear(seal_id)}))
        result = gear.apply_gear_ability(state, _activate(seal_id, ()))
        assert result.players[0].runes.available == (domain,)


def test_seal_reachable_through_legal_actions():
    """The guard against "registered but unreachable" — search.legal_actions
    must actually offer the activation, not just gear.GEAR_ABILITIES."""
    state = make_state(gear_pieces=frozenset({ready_gear(gear.SEAL_OF_UNITY)}))
    actions = [a for a in search.legal_actions(state, {})
               if isinstance(a, ActivateAbility) and a.ability_id == gear.SEAL_OF_UNITY]
    assert len(actions) == 1
    result = gear.apply_gear_ability(state, actions[0])
    assert result.players[0].runes.available == ("Order",)


def test_exhausted_seal_cannot_activate_again():
    state = make_state(gear_pieces=frozenset({
        GearInstance(card_id=gear.SEAL_OF_RAGE, instance_id=50, exhausted=True)}))
    assert not gear.is_legal_gear_ability(state, _activate(gear.SEAL_OF_RAGE, ()))


def test_playing_gear_needs_the_runes():
    state = make_state(hand=(gear.IRON_BALLISTA,), runes=("Fury",))
    action = PlayGear(card_id=gear.IRON_BALLISTA,
                       rune_payment=RunePayment(energy_runes=("Fury",) * 3, power_runes=()))
    assert not is_legal_play_gear(state, action, BALLISTA)


# --- abilities ---


def _activate(card_id, params, payment=None, source_id=50):
    return ActivateAbility(source_id=source_id, ability_id=card_id, params=params,
                            rune_payment=payment)


def test_ballista_deals_two_to_a_unit_at_a_battlefield():
    target = make_unit(1, controller=1, might=5)
    state = make_state(gear_pieces=frozenset({ready_gear(gear.IRON_BALLISTA)}),
                        left_units=frozenset({target}), left_ctrl=1)
    action = _activate(gear.IRON_BALLISTA, (1,))
    assert gear.is_legal_gear_ability(state, action)
    result = gear.apply_gear_ability(state, action)
    assert next(iter(result.battlefields[0].units)).damage == 2


def test_ballista_kills_what_it_can_and_clears_control():
    target = make_unit(1, controller=1, might=2)
    state = make_state(gear_pieces=frozenset({ready_gear(gear.IRON_BALLISTA)}),
                        left_units=frozenset({target}), left_ctrl=1)
    result = gear.apply_gear_ability(state, _activate(gear.IRON_BALLISTA, (1,)))
    assert result.battlefields[0].units == frozenset()
    assert result.battlefields[0].controller is None


def test_an_ability_exhausts_its_gear_and_cannot_be_used_twice():
    target = make_unit(1, controller=1, might=9)
    state = make_state(gear_pieces=frozenset({ready_gear(gear.IRON_BALLISTA)}),
                        left_units=frozenset({target}), left_ctrl=1)
    action = _activate(gear.IRON_BALLISTA, (1,))
    result = gear.apply_gear_ability(state, action)
    assert next(iter(result.players[0].gear)).exhausted is True
    assert not gear.is_legal_gear_ability(result, action)


def test_ballista_cannot_hit_a_unit_at_base():
    """"a unit at a battlefield" — Base is out of reach."""
    state = make_state(gear_pieces=frozenset({ready_gear(gear.IRON_BALLISTA)}),
                        base_units=frozenset({make_unit(1)}))
    assert not gear.is_legal_gear_ability(state, _activate(gear.IRON_BALLISTA, (1,)))


def test_orb_lowers_might_but_never_below_one():
    weak = make_unit(1, might=1)
    state = make_state(gear_pieces=frozenset({ready_gear(gear.ORB_OF_REGRET)}),
                        base_units=frozenset({weak}))
    result = gear.apply_gear_ability(state, _activate(gear.ORB_OF_REGRET, (1,)))
    assert next(iter(result.players[0].base_units)).might == 1  # floored, not 0


def test_orb_lowers_a_healthy_unit():
    state = make_state(gear_pieces=frozenset({ready_gear(gear.ORB_OF_REGRET)}),
                        base_units=frozenset({make_unit(1, might=4)}))
    result = gear.apply_gear_ability(state, _activate(gear.ORB_OF_REGRET, (1,)))
    assert next(iter(result.players[0].base_units)).might == 3


def test_orb_can_target_either_players_unit():
    """"a unit" — the text doesn't restrict it."""
    enemy = make_unit(1, controller=1, might=4)
    state = make_state(gear_pieces=frozenset({ready_gear(gear.ORB_OF_REGRET)}),
                        left_units=frozenset({enemy}), left_ctrl=1)
    assert gear.is_legal_gear_ability(state, _activate(gear.ORB_OF_REGRET, (1,)))


def test_syren_charges_its_extra_energy():
    unit = make_unit(1, controller=0)
    state = make_state(gear_pieces=frozenset({ready_gear(gear.THE_SYREN)}),
                        runes=("Fury",), left_units=frozenset({unit}), left_ctrl=0)
    paid = RunePayment(energy_runes=("Fury",), power_runes=())
    assert not gear.is_legal_gear_ability(state, _activate(gear.THE_SYREN, (1,)))  # unpaid
    assert gear.is_legal_gear_ability(state, _activate(gear.THE_SYREN, (1,), paid))


def test_syren_pulls_a_friendly_unit_home_and_spends_the_energy():
    unit = make_unit(1, controller=0)
    state = make_state(gear_pieces=frozenset({ready_gear(gear.THE_SYREN)}),
                        runes=("Fury",), left_units=frozenset({unit}), left_ctrl=0)
    paid = RunePayment(energy_runes=("Fury",), power_runes=())
    result = gear.apply_gear_ability(state, _activate(gear.THE_SYREN, (1,), paid))
    assert result.battlefields[0].units == frozenset()
    assert {u.instance_id for u in result.players[0].base_units} == {1}
    assert result.players[0].runes.energy_spent == 1


def test_syren_will_not_move_an_enemy_unit():
    enemy = make_unit(1, controller=1)
    state = make_state(gear_pieces=frozenset({ready_gear(gear.THE_SYREN)}),
                        runes=("Fury",), left_units=frozenset({enemy}), left_ctrl=1)
    paid = RunePayment(energy_runes=("Fury",), power_runes=())
    assert not gear.is_legal_gear_ability(state, _activate(gear.THE_SYREN, (1,), paid))


def test_an_exhausted_gear_cannot_activate():
    state = make_state(
        gear_pieces=frozenset({GearInstance(card_id=gear.ORB_OF_REGRET, instance_id=50,
                                             exhausted=True)}),
        base_units=frozenset({make_unit(1)}))
    assert not gear.is_legal_gear_ability(state, _activate(gear.ORB_OF_REGRET, (1,)))


def test_gear_survives_the_death_of_a_unit():
    """Gear doesn't attach, so nothing about a unit dying touches it —
    the failure mode if it had been modelled as equipment."""
    from solver.engine.actions import kill_unit
    state = make_state(gear_pieces=frozenset({ready_gear(gear.ORB_OF_REGRET)}),
                        base_units=frozenset({make_unit(1)}))
    result = kill_unit(state, 1)
    assert result.players[0].base_units == frozenset()
    assert len(result.players[0].gear) == 1


def test_an_unregistered_gear_ability_is_refused():
    state = make_state(gear_pieces=frozenset({ready_gear("ogn-021-298")}))
    assert not gear.is_legal_gear_ability(state, _activate("ogn-021-298", (1,)))


# --- kill_gear: removal + trash landing ---


def test_kill_gear_removes_it_from_the_board():
    from solver.engine.actions import kill_gear
    piece = ready_gear(gear.ORB_OF_REGRET)
    state = make_state(gear_pieces=frozenset({piece}))
    result = kill_gear(state, 0, piece)
    assert result.players[0].gear == frozenset()


def test_kill_gear_lands_the_card_in_its_controllers_trash():
    """A Gear is a real printed card, same as a dying unit — it leaves
    play into trash, not off into the void."""
    from solver.engine.actions import kill_gear
    piece = ready_gear(gear.ORB_OF_REGRET)
    state = make_state(gear_pieces=frozenset({piece}))
    result = kill_gear(state, 0, piece)
    assert result.players[0].trash == (gear.ORB_OF_REGRET,)


def test_kill_gear_does_not_touch_other_gear_or_units():
    from solver.engine.actions import kill_gear
    victim = ready_gear(gear.ORB_OF_REGRET, instance_id=50)
    survivor = ready_gear(gear.THE_SYREN, instance_id=51)
    unit = make_unit(1)
    state = make_state(gear_pieces=frozenset({victim, survivor}), base_units=frozenset({unit}))
    result = kill_gear(state, 0, victim)
    assert {g.instance_id for g in result.players[0].gear} == {51}
    assert result.players[0].base_units == frozenset({unit})


# --- reachable through real action generation ---

def test_gear_can_actually_be_played_from_hand():
    """The subsystem shipped unwired: complete and tested, but no line
    could ever play a Gear because generation never emitted PlayGear.
    This is the end-to-end proof that it is reachable now."""
    from solver.engine.actions import PlayGear
    from solver.engine.card_pool import card_def
    from solver.search import legal_actions

    ballista = "ogn-017-298"
    card = card_def(ballista)
    state = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(ballista,),
                        runes=RunePool(available=("Fury",) * 6), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    plays = [a for a in legal_actions(state, {ballista: card}) if isinstance(a, PlayGear)]
    assert plays, "PlayGear is not being generated"


def test_a_gear_ability_is_generated_once_the_gear_is_on_the_board():
    """Iron Ballista enters exhausted, so its own ability is unusable the
    turn it lands — the Orb is the one that can act immediately."""
    from solver.engine.actions import ActivateAbility
    from solver.engine.card_pool import card_def
    from solver.engine.state import GearInstance
    from solver.search import legal_actions

    orb = "ogn-090-298"
    target = UnitInstance(card_id="u", instance_id=1, controller=1, might=4,
                           keywords=frozenset(), exhausted=False, damage=0, is_token=False)
    state = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0,
                        gear=frozenset({GearInstance(card_id=orb, instance_id=9)})),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 1, frozenset({target}), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    acts = [a for a in legal_actions(state, {orb: card_def(orb)})
            if isinstance(a, ActivateAbility) and a.ability_id == orb]
    assert acts, "gear abilities are not being generated"


# --- Pack of Wonders: "Exhaust: Return another friendly gear, unit, or
# [Hidden] card to its owner's hand." ---


def test_pack_of_wonders_returns_a_friendly_unit_at_base_to_hand():
    unit = make_unit(1, controller=0)
    state = make_state(gear_pieces=frozenset({ready_gear(gear.PACK_OF_WONDERS)}),
                        base_units=frozenset({unit}))
    action = ActivateAbility(source_id=50, ability_id=gear.PACK_OF_WONDERS,
                              params=("unit", 1), rune_payment=None)
    assert gear.is_legal_gear_ability(state, action)
    out = gear.apply_gear_ability(state, action)
    assert out.players[0].base_units == frozenset()
    assert out.players[0].hand == ("u",)
    assert next(g for g in out.players[0].gear).exhausted is True


def test_pack_of_wonders_returns_another_friendly_gear_not_itself():
    orb = GearInstance(card_id=gear.ORB_OF_REGRET, instance_id=51, exhausted=False)
    state = make_state(gear_pieces=frozenset({ready_gear(gear.PACK_OF_WONDERS), orb}))

    self_target = ActivateAbility(source_id=50, ability_id=gear.PACK_OF_WONDERS,
                                   params=("gear", 50), rune_payment=None)
    assert not gear.is_legal_gear_ability(state, self_target)

    other_target = ActivateAbility(source_id=50, ability_id=gear.PACK_OF_WONDERS,
                                    params=("gear", 51), rune_payment=None)
    assert gear.is_legal_gear_ability(state, other_target)
    out = gear.apply_gear_ability(state, other_target)
    remaining_ids = {g.card_id for g in out.players[0].gear}
    assert remaining_ids == {gear.PACK_OF_WONDERS}
    assert out.players[0].hand == (gear.ORB_OF_REGRET,)


# --- Spirit's Refuge: "When you play this, buff a friendly unit."
# "Friendly buffed units have [Deflect] if they didn't already." ---


SPIRITS_REFUGE = abilities.SPIRITS_REFUGE


def test_spirits_refuge_buffs_the_chosen_friendly_unit_on_play():
    card = card_def(SPIRITS_REFUGE)
    unit = make_unit(1, controller=0)
    state = make_state(hand=(SPIRITS_REFUGE,), runes=("Calm",) * 3,
                        base_units=frozenset({unit}))
    action = PlayGear(card_id=SPIRITS_REFUGE, trigger_params=(1,),
                       rune_payment=RunePayment(energy_runes=("Calm", "Calm"),
                                                 power_runes=("Calm",)))
    assert abilities.is_legal_gear_play_trigger(state, action, card)
    [result] = abilities.resolve_gear_play_trigger_outcomes(state, action, card)
    assert next(iter(result.players[0].base_units)).buffed is True


def test_spirits_refuge_cannot_target_an_enemy_unit():
    """"A FRIENDLY unit" — unlike Whiteflame's unrestricted "a unit"."""
    card = card_def(SPIRITS_REFUGE)
    enemy = make_unit(1, controller=1)
    state = make_state(hand=(SPIRITS_REFUGE,), runes=("Calm",) * 3,
                        left_units=frozenset({enemy}), left_ctrl=1)
    action = PlayGear(card_id=SPIRITS_REFUGE, trigger_params=(1,),
                       rune_payment=RunePayment(energy_runes=("Calm", "Calm"),
                                                 power_runes=("Calm",)))
    assert not abilities.is_legal_gear_play_trigger(state, action, card)


def test_spirits_refuge_grants_deflect_to_any_buffed_friendly_unit():
    """The second clause is a board-wide conditional grant sourced from the
    Gear, not from the unit the play trigger buffed — it has to reach a
    SEPARATE unit that was buffed some other way (here, just constructed
    already-buffed), including one sitting at Base, where Gear (never
    positional) still reaches it."""
    from solver.engine.traits import resolved_traits

    buffed_unit = dataclasses.replace(make_unit(1, controller=0), buffed=True)
    state = make_state(gear_pieces=frozenset({ready_gear(SPIRITS_REFUGE)}),
                        base_units=frozenset({buffed_unit}))
    assert "Deflect" in resolved_traits(state, buffed_unit, "base")


def test_no_spirits_refuge_means_no_deflect_from_being_buffed():
    from solver.engine.traits import resolved_traits

    buffed_unit = dataclasses.replace(make_unit(1, controller=0), buffed=True)
    state = make_state(base_units=frozenset({buffed_unit}))
    assert "Deflect" not in resolved_traits(state, buffed_unit, "base")


def test_spirits_refuge_reachable_through_legal_actions():
    unit = make_unit(1, controller=0)
    state = make_state(hand=(SPIRITS_REFUGE,), runes=("Calm",) * 3,
                        base_units=frozenset({unit}))
    plays = [a for a in search.legal_actions(state, {SPIRITS_REFUGE: card_def(SPIRITS_REFUGE)})
             if getattr(a, "card_id", None) == SPIRITS_REFUGE]
    assert plays, "Spirit's Refuge is not being generated"
    assert all(a.trigger_params == (1,) for a in plays)  # mandatory — no bare play


# --- Sun Disc: "[Legion] Exhaust: The next unit you play this turn enters
# ready." ---


SUN_DISC = gear.SUN_DISC


def test_sun_disc_sets_the_flag_when_legion_is_met():
    state = make_state(gear_pieces=frozenset({ready_gear(SUN_DISC)}))
    state = dataclasses.replace(state, cards_played_this_turn=1)
    action = _activate(SUN_DISC, ())
    assert gear.is_legal_gear_ability(state, action)
    result = gear.apply_gear_ability(state, action)
    assert result.players[0].next_unit_enters_ready is True
    assert next(iter(result.players[0].gear)).exhausted is True


def test_sun_disc_does_nothing_without_legion():
    """[Legion] not met — the Exhaust is legal but produces no effect, same
    convention as Dangerous Duo/Trifarian Gloryseeker."""
    state = make_state(gear_pieces=frozenset({ready_gear(SUN_DISC)}))
    action = _activate(SUN_DISC, ())
    assert gear.is_legal_gear_ability(state, action)  # legal, just wasted
    result = gear.apply_gear_ability(state, action)
    assert result.players[0].next_unit_enters_ready is False


def test_sun_disc_makes_the_next_played_unit_enter_ready():
    from solver.engine.actions import PlayUnit, apply_play_unit
    from solver.engine.cards import CardDef

    plain = CardDef(card_id="p", card_type="Unit", energy_cost=1, power_cost=0, might=2)
    state = make_state(gear_pieces=frozenset({ready_gear(SUN_DISC)}), hand=("p",),
                        runes=("Fury",))
    state = dataclasses.replace(state, cards_played_this_turn=1)
    flagged = gear.apply_gear_ability(state, _activate(SUN_DISC, ()))
    assert flagged.players[0].next_unit_enters_ready is True

    play = PlayUnit(card_id="p", target_zone="base",
                     rune_payment=RunePayment(energy_runes=("Fury",), power_runes=()))
    result = apply_play_unit(flagged, play, plain)
    placed = next(iter(result.players[0].base_units))
    assert placed.exhausted is False
    assert result.players[0].next_unit_enters_ready is False  # consumed


def test_sun_disc_reachable_through_legal_actions():
    state = make_state(gear_pieces=frozenset({ready_gear(SUN_DISC)}))
    state = dataclasses.replace(state, cards_played_this_turn=1)
    acts = [a for a in search.legal_actions(state, {})
            if isinstance(a, ActivateAbility) and a.ability_id == SUN_DISC]
    assert acts, "Sun Disc is not being generated"
    result = gear.apply_gear_ability(state, acts[0])
    assert result.players[0].next_unit_enters_ready is True


# --- Ravenborn Tome: "Exhaust: The next spell you play this turn deals 1
# Bonus Damage." ---


RAVENBORN_TOME = gear.RAVENBORN_TOME


def test_ravenborn_tome_sets_the_bonus_damage_flag():
    state = make_state(gear_pieces=frozenset({ready_gear(RAVENBORN_TOME)}))
    action = _activate(RAVENBORN_TOME, ())
    assert gear.is_legal_gear_ability(state, action)
    result = gear.apply_gear_ability(state, action)
    assert result.players[0].next_spell_bonus_damage == 1
    assert next(iter(result.players[0].gear)).exhausted is True


def test_ravenborn_tome_adds_one_to_the_next_spells_damage_and_is_consumed():
    """Hextech Ray: "Deal 3 to a unit at a battlefield" — 3 becomes 4, and
    a second spell afterward gets no further bonus."""
    hextech_ray = "ogn-009-298"  # 1 Energy, 1 Fury Power: "Deal 3 to a unit at a battlefield."
    target = make_unit(1, controller=1, might=9)
    state = make_state(gear_pieces=frozenset({ready_gear(RAVENBORN_TOME)}),
                        hand=(hextech_ray,), runes=("Fury", "Fury"),
                        left_units=frozenset({target}), left_ctrl=1)
    flagged = gear.apply_gear_ability(state, _activate(RAVENBORN_TOME, ()))
    assert flagged.players[0].next_spell_bonus_damage == 1

    action = PlaySpell(card_id=hextech_ray, params=(1,),
                        rune_payment=RunePayment(energy_runes=("Fury",), power_runes=("Fury",)))
    [result] = abilities.resolve_spell_outcomes(flagged, action, card_def(hextech_ray))
    hit = next(iter(result.battlefields[0].units))
    assert hit.damage == 4  # 3 printed + 1 Bonus Damage
    assert result.players[0].next_spell_bonus_damage == 0  # consumed by this one spell


def test_ravenborn_tome_bonus_applies_to_both_sides_of_challenge():
    """Challenge routes through the SHARED _mutual_damage helper (also used
    by Carnivorous Snapvine's UNIT_PLAY_TRIGGERS effect, which must NOT see
    the bonus — _mutual_damage's `bonus` parameter defaults to 0 and only
    Challenge's SPELL_EFFECTS caller passes one). Both simultaneous damage
    instances get +1 when the flag is set."""
    challenge = "ogn-128-298"  # 2 Energy, 1 Body Power
    ours = make_unit(1, controller=0, might=5)
    theirs = make_unit(2, controller=1, might=5)
    state = make_state(gear_pieces=frozenset({ready_gear(RAVENBORN_TOME)}),
                        hand=(challenge,), runes=("Body", "Body", "Body"),
                        left_units=frozenset({ours, theirs}))
    flagged = gear.apply_gear_ability(state, _activate(RAVENBORN_TOME, ()))
    action = PlaySpell(card_id=challenge, params=(1, 2),
                        rune_payment=RunePayment(energy_runes=("Body", "Body"), power_runes=("Body",)))
    [result] = abilities.resolve_spell_outcomes(flagged, action, card_def(challenge))
    # Both 5-Might units deal 5+1=6 to each other — lethal against a
    # 5-Might body, which the printed 5-for-5 trade alone would not be.
    assert result.battlefields[0].units == frozenset()
    assert result.players[0].next_spell_bonus_damage == 0


def test_ravenborn_tome_reachable_through_legal_actions():
    state = make_state(gear_pieces=frozenset({ready_gear(RAVENBORN_TOME)}))
    acts = [a for a in search.legal_actions(state, {})
            if isinstance(a, ActivateAbility) and a.ability_id == RAVENBORN_TOME]
    assert acts, "Ravenborn Tome is not being generated"
    result = gear.apply_gear_ability(state, acts[0])
    assert result.players[0].next_spell_bonus_damage == 1


# --- Pirate's Haven: "When you ready a friendly unit, give it +1 Might
# this turn." ---


PIRATES_HAVEN = abilities.PIRATES_HAVEN


def test_pirates_haven_buffs_a_unit_actually_readied():
    exhausted_unit = make_unit(1, controller=0, might=3, exhausted=True)
    state = make_state(gear_pieces=frozenset({ready_gear(PIRATES_HAVEN)}),
                        base_units=frozenset({exhausted_unit}))
    result = abilities.ready_unit(state, 1)
    placed = next(iter(result.players[0].base_units))
    assert placed.exhausted is False
    assert placed.might == 4  # +1 Might from Pirate's Haven


def test_pirates_haven_does_nothing_on_an_already_ready_unit():
    """"When you ready" — readying an already-ready unit is not a second
    readying, same no-op convention as ready_unit itself."""
    ready_unit_ = make_unit(1, controller=0, might=3, exhausted=False)
    state = make_state(gear_pieces=frozenset({ready_gear(PIRATES_HAVEN)}),
                        base_units=frozenset({ready_unit_}))
    result = abilities.ready_unit(state, 1)
    assert next(iter(result.players[0].base_units)).might == 3


def test_without_pirates_haven_readying_grants_no_might():
    exhausted_unit = make_unit(1, controller=0, might=3, exhausted=True)
    state = make_state(base_units=frozenset({exhausted_unit}))
    result = abilities.ready_unit(state, 1)
    assert next(iter(result.players[0].base_units)).might == 3


def test_pirates_haven_reachable_through_legal_actions_via_first_mate():
    """First Mate's own play trigger ("ready another unit") is the
    end-to-end path — abilities.ready_unit is not itself an action, so the
    proof is that a REGISTERED reader of it is reachable with Pirate's
    Haven present."""
    first_mate = abilities.FIRST_MATE
    exhausted_ally = make_unit(1, controller=0, might=2, exhausted=True)
    state = make_state(gear_pieces=frozenset({ready_gear(PIRATES_HAVEN)}),
                        hand=(first_mate,), runes=("Fury",) * 3,
                        base_units=frozenset({exhausted_ally}))
    cards = {first_mate: card_def(first_mate)}
    plays = [a for a in search.legal_actions(state, cards)
             if getattr(a, "card_id", None) == first_mate and a.trigger_params == (1,)]
    assert plays, "First Mate's ready-another-unit trigger is not reachable"
    [result] = abilities.resolve_unit_play_trigger_outcomes(state, plays[0], cards[first_mate])
    readied = next(u for u in result.players[0].base_units if u.instance_id == 1)
    assert readied.exhausted is False
    assert readied.might == 3  # +1 from Pirate's Haven


# --- Treasure Trove: "When this leaves the board, draw 1 and channel 1
# rune exhausted. [Chaos rune], Exhaust: Kill this." ---


TREASURE_TROVE = gear.TREASURE_TROVE


def test_treasure_trove_kills_itself_and_channels_a_rune():
    from solver.engine.state import energy_capacity

    state = make_state(gear_pieces=frozenset({ready_gear(TREASURE_TROVE)}),
                        runes=("Chaos",))
    action = _activate(TREASURE_TROVE, (), payment=RunePayment(energy_runes=(), power_runes=("Chaos",)))
    assert gear.is_legal_gear_ability(state, action)
    result = gear.apply_gear_ability(state, action)
    assert result.players[0].gear == frozenset()
    assert TREASURE_TROVE in result.players[0].trash
    # One new domain-less rune (RULING 1) on top of the starting Chaos one,
    # arriving already-exhausted — the original Chaos rune only spent its
    # POWER on this ability's own cost, so its OWN Energy is untouched.
    assert len(result.players[0].runes.available) == 2
    assert None in result.players[0].runes.available
    assert energy_capacity(result.players[0].runes) == 1


def test_treasure_trove_needs_the_chaos_rune_to_activate():
    state = make_state(gear_pieces=frozenset({ready_gear(TREASURE_TROVE)}))
    action = _activate(TREASURE_TROVE, (), payment=None)
    assert not gear.is_legal_gear_ability(state, action)


def test_pack_of_wonders_bouncing_treasure_trove_also_fires_its_reaction():
    """A bounce leaves the board same as a kill — the reaction doesn't
    care which removal path triggered it."""
    trove = GearInstance(card_id=TREASURE_TROVE, instance_id=51, exhausted=False)
    state = make_state(gear_pieces=frozenset({ready_gear(gear.PACK_OF_WONDERS), trove}))
    action = ActivateAbility(source_id=50, ability_id=gear.PACK_OF_WONDERS,
                              params=("gear", 51), rune_payment=None)
    assert gear.is_legal_gear_ability(state, action)
    result = gear.apply_gear_ability(state, action)
    assert result.players[0].hand == (TREASURE_TROVE,)
    assert None in result.players[0].runes.available


def test_treasure_trove_reachable_through_legal_actions():
    state = make_state(gear_pieces=frozenset({ready_gear(TREASURE_TROVE)}), runes=("Chaos",))
    acts = [a for a in search.legal_actions(state, {})
            if isinstance(a, ActivateAbility) and a.ability_id == TREASURE_TROVE]
    assert acts, "Treasure Trove's kill-this ability is not being generated"
    result = gear.apply_gear_ability(state, acts[0])
    assert result.players[0].gear == frozenset()


def test_pack_of_wonders_reachable_through_legal_actions():
    """End-to-end proof through search.legal_actions, same as Ballista's
    own reachability test above — a new Gear ability is exactly the class
    of thing that has shipped "registered but unreachable" before."""
    from solver.engine.actions import ActivateAbility
    from solver.engine.card_pool import card_def
    from solver.search import legal_actions

    unit = make_unit(1, controller=0)
    state = make_state(gear_pieces=frozenset({ready_gear(gear.PACK_OF_WONDERS)}),
                        base_units=frozenset({unit}))
    acts = [a for a in legal_actions(state, {gear.PACK_OF_WONDERS: card_def(gear.PACK_OF_WONDERS)})
            if isinstance(a, ActivateAbility) and a.ability_id == gear.PACK_OF_WONDERS]
    assert acts, "Pack of Wonders' ability is not being generated"
    assert ("unit", 1) in {a.params for a in acts}
