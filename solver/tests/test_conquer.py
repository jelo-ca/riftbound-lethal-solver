"""[Conquer] triggers — "When I conquer" (a unit) and "when you conquer
here" (a battlefield).

Sett, Brawler is the card that exercises the new hook: a body simple
enough to isolate the trigger (a binary buff, already implemented
elsewhere for its "when I'm played" twin) sitting behind a genuinely new
choke point — scoring.resolve_control_change, called from every action
that can establish control. The reachability test below goes through
search.legal_actions/search.apply, not a direct call into conquer.py,
because "registered but unreachable" (Tank, Gear) is this codebase's most
common self-inflicted bug.
"""

from solver import search
from solver.engine import conquer
from solver.engine.abilities import SETT_BRAWLER, SETT_BRAWLER_ALT, resolve_unit_play_trigger_outcomes
from solver.engine.actions import ActivateAbility, MoveUnit, PlayUnit
from solver.engine.card_pool import card_def
from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    UnitInstance,
)


def make_unit(card_id, instance_id, controller=0, might=3, buffed=False, exhausted=False):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=frozenset(), exhausted=exhausted, damage=0,
                         is_token=False, buffed=buffed)


def make_state(base_units=frozenset(), hand=(), left_units=frozenset(), left_ctrl=None,
               right_units=frozenset(), right_ctrl=None, opp_base=frozenset(), runes=()):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=hand, runes=RunePool(available=runes), score=0),
            PlayerState(base_units=opp_base, hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", left_ctrl, left_units, None),
            BattlefieldState("right", right_ctrl, right_units, None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


# --- the hook itself: fire_conquer_triggers ---


def test_a_newly_arrived_unit_with_a_registered_trigger_fires():
    sett = make_unit(SETT_BRAWLER, 1, buffed=False)
    old_state = make_state(left_units=frozenset(), left_ctrl=None)
    new_state = make_state(left_units=frozenset({sett}), left_ctrl=0)
    result = conquer.fire_conquer_triggers(old_state, new_state, "left", controller=0)
    assert next(iter(result.battlefields[0].units)).buffed is True


def test_a_unit_without_a_registered_trigger_does_nothing():
    plain = make_unit("plain-card", 1)
    old_state = make_state(left_units=frozenset(), left_ctrl=None)
    new_state = make_state(left_units=frozenset({plain}), left_ctrl=0)
    result = conquer.fire_conquer_triggers(old_state, new_state, "left", controller=0)
    assert result == new_state  # untouched


def test_a_unit_already_present_before_the_conquer_does_not_refire():
    """Sett was already standing at a contested "left" (alongside an enemy
    unit that has since been removed by whatever action produced
    new_state); only a genuinely NEW arrival should trigger, not a
    resident who happened to end up on the winning side."""
    sett = make_unit(SETT_BRAWLER, 1, buffed=False)
    old_state = make_state(left_units=frozenset({sett}), left_ctrl=None)
    new_state = make_state(left_units=frozenset({sett}), left_ctrl=0)
    result = conquer.fire_conquer_triggers(old_state, new_state, "left", controller=0)
    assert next(iter(result.battlefields[0].units)).buffed is False


def test_only_the_conquering_players_units_are_considered():
    """A newly-arrived ENEMY unit (e.g. moved there by one of our own
    effects) must not fire a trigger keyed to OUR conquer."""
    enemy_sett = make_unit(SETT_BRAWLER, 1, controller=1, buffed=False)
    old_state = make_state(left_units=frozenset(), left_ctrl=None)
    new_state = make_state(left_units=frozenset({enemy_sett}), left_ctrl=0)
    result = conquer.fire_conquer_triggers(old_state, new_state, "left", controller=0)
    assert next(iter(result.battlefields[0].units)).buffed is False


def test_an_already_buffed_conqueror_is_a_no_op():
    """Buffs are binary — the second buff this turn (played, then
    conquered) does nothing, same as everywhere else apply_buff is used."""
    sett = make_unit(SETT_BRAWLER, 1, buffed=True)
    old_state = make_state(left_units=frozenset(), left_ctrl=None)
    new_state = make_state(left_units=frozenset({sett}), left_ctrl=0)
    result = conquer.fire_conquer_triggers(old_state, new_state, "left", controller=0)
    assert next(iter(result.battlefields[0].units)).buffed is True  # still true, not "twice"


def test_the_alternate_art_printing_shares_the_same_trigger():
    sett = make_unit(SETT_BRAWLER_ALT, 1, buffed=False)
    old_state = make_state(left_units=frozenset(), left_ctrl=None)
    new_state = make_state(left_units=frozenset({sett}), left_ctrl=0)
    result = conquer.fire_conquer_triggers(old_state, new_state, "left", controller=0)
    assert next(iter(result.battlefields[0].units)).buffed is True


# --- reachability: the hook fires through REAL PLAY, not just a direct call ---


def test_moving_to_an_open_battlefield_fires_the_conquer_trigger_through_legal_actions():
    """search.legal_actions -> search.apply, exactly the path a solve()
    would take. This is the guard against "registered but unreachable"."""
    sett = make_unit(SETT_BRAWLER, 1, buffed=False, exhausted=False)
    state = make_state(base_units=frozenset({sett}))
    cards = {SETT_BRAWLER: card_def(SETT_BRAWLER)}

    move = next(a for a in search.legal_actions(state, cards)
                if isinstance(a, MoveUnit) and a.instance_id == 1 and a.to_zone == "left")
    result = search.apply(state, move, cards)

    assert result.battlefields[0].controller == 0
    moved = next(iter(result.battlefields[0].units))
    assert moved.card_id == SETT_BRAWLER
    assert moved.buffed is True  # the conquer trigger, not just the move landing


def test_playing_to_base_never_conquers_so_only_the_play_trigger_fires():
    """Sett prints no "may play me to an open battlefield" text, so Base
    is his only legal PlayUnit target — and Base is never conquered
    (search.py's own guard never calls resolve_control_change for it), so
    only the mandatory "when I'm played" buff should land here. The
    conquer half of his text is exercised separately, via the MoveUnit
    reachability test above, once he's already on the board."""
    state = make_state(hand=(SETT_BRAWLER,), runes=("Body",) * 5)
    cards = {SETT_BRAWLER: card_def(SETT_BRAWLER)}
    base_play = next(a for a in search.legal_actions(state, cards)
                      if isinstance(a, PlayUnit) and a.card_id == SETT_BRAWLER
                      and a.target_zone == "base" and a.trigger_params == ("buff",))
    [result] = resolve_unit_play_trigger_outcomes(state, base_play, cards[SETT_BRAWLER])
    unit = next(iter(result.players[0].base_units))
    assert unit.buffed is True  # from the play trigger alone


def test_the_bare_play_form_is_not_offered_since_the_trigger_is_mandatory():
    state = make_state(hand=(SETT_BRAWLER,), runes=("Body",) * 5)
    cards = {SETT_BRAWLER: card_def(SETT_BRAWLER)}
    bare = [a for a in search.legal_actions(state, cards)
            if isinstance(a, PlayUnit) and a.card_id == SETT_BRAWLER and a.trigger_params == ()]
    assert bare == []


def test_sett_spend_buff_ability_grants_four_might_and_clears_the_buff():
    sett = make_unit(SETT_BRAWLER, 1, buffed=True, might=4)
    state = make_state(base_units=frozenset({sett}))
    cards = {SETT_BRAWLER: card_def(SETT_BRAWLER)}
    action = next(a for a in search.legal_actions(state, cards)
                  if isinstance(a, ActivateAbility) and a.ability_id == SETT_BRAWLER)
    result = search.apply(state, action, cards)
    unit = next(iter(result.players[0].base_units))
    assert unit.buffed is False
    assert unit.might == 8


def test_sett_spend_buff_ability_unavailable_without_a_buff():
    sett = make_unit(SETT_BRAWLER, 1, buffed=False)
    state = make_state(base_units=frozenset({sett}))
    cards = {SETT_BRAWLER: card_def(SETT_BRAWLER)}
    actions = [a for a in search.legal_actions(state, cards)
               if isinstance(a, ActivateAbility) and a.ability_id == SETT_BRAWLER]
    assert actions == []
