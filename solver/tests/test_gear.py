"""Gear — standalone permanents with activated abilities.

The rules under test were derived from the printed text of all 30 Origins
Gear cards, not by analogy to units. The two that matter most and are
easiest to get backwards:

  * Gear does NOT attach to a unit (no printing says attach/equip), so a
    unit dying leaves it untouched;
  * Gear enters READY, the opposite of units — Iron Ballista has to print
    "This enters exhausted" precisely because that isn't the default.
"""

from solver.engine import gear
from solver.engine.actions import (
    ActivateAbility,
    PlayGear,
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
