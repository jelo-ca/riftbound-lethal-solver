"""Observer triggers — "when you play ANOTHER unit," fired regardless of
which card is being played, at whoever is already on the board watching.

Cithria of Cloudfield is the card that exercises the new hook. The
reachability test goes through search.legal_actions/search.apply, not a
direct call into observers.py, for the same reason test_conquer.py's
does: "registered but unreachable" is this codebase's most common
self-inflicted bug.
"""

from solver import search
from solver.engine import observers
from solver.engine.actions import PlayUnit
from solver.engine.card_pool import card_def
from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    UnitInstance,
)

CITHRIA = observers.CITHRIA_OF_CLOUDFIELD
OTHER_UNIT = "ogn-049-298"  # Playful Phantom — cheap, no text of its own


def make_unit(card_id, instance_id, controller=0, might=1, buffed=False, exhausted=False):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=frozenset(), exhausted=exhausted, damage=0,
                         is_token=False, buffed=buffed)


def make_state(base_units=frozenset(), hand=(), left_units=frozenset(), runes=()):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=hand, runes=RunePool(available=runes), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0 if left_units else None, left_units, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


# --- the hook itself: fire_observer_play_triggers ---


def test_a_watcher_is_buffed_when_another_unit_is_played():
    watcher = make_unit(CITHRIA, 1)
    played = make_unit(OTHER_UNIT, 2)
    state = make_state(base_units=frozenset({played}), left_units=frozenset({watcher}))
    result = observers.fire_observer_play_triggers(state, played)
    watcher_after = next(iter(result.battlefields[0].units))
    assert watcher_after.buffed is True


def test_a_watcher_does_not_watch_its_own_play():
    """"Another unit" — a Cithria who is herself the card being played
    must not buff herself off her own arrival."""
    cithria = make_unit(CITHRIA, 1)
    state = make_state(base_units=frozenset({cithria}))
    result = observers.fire_observer_play_triggers(state, cithria)
    assert next(iter(result.players[0].base_units)).buffed is False


def test_only_the_watchers_own_controller_is_considered():
    """An enemy Cithria doesn't watch OUR plays."""
    enemy_cithria = make_unit(CITHRIA, 1, controller=1)
    played = make_unit(OTHER_UNIT, 2, controller=0)
    state = make_state(base_units=frozenset({played}), left_units=frozenset({enemy_cithria}))
    result = observers.fire_observer_play_triggers(state, played)
    assert next(iter(result.battlefields[0].units)).buffed is False


def test_an_already_buffed_watcher_is_a_no_op():
    watcher = make_unit(CITHRIA, 1, buffed=True)
    played = make_unit(OTHER_UNIT, 2)
    state = make_state(base_units=frozenset({played}), left_units=frozenset({watcher}))
    result = observers.fire_observer_play_triggers(state, played)
    assert next(iter(result.battlefields[0].units)).buffed is True  # still true, not "twice"


def test_a_unit_without_a_registered_observer_does_nothing():
    plain = make_unit("plain-card", 1)
    played = make_unit(OTHER_UNIT, 2)
    state = make_state(base_units=frozenset({played}), left_units=frozenset({plain}))
    result = observers.fire_observer_play_triggers(state, played)
    assert result == state


# --- reachability: the hook fires through REAL PLAY, not just a direct call ---


def test_playing_a_unit_buffs_cithria_through_legal_actions():
    """search.legal_actions -> search.apply, exactly the path a solve()
    would take. This is the guard against "registered but unreachable"."""
    cithria = make_unit(CITHRIA, 1)
    state = make_state(hand=(OTHER_UNIT,), left_units=frozenset({cithria}), runes=("Fury",) * 5)
    cards = {OTHER_UNIT: card_def(OTHER_UNIT)}

    play = next(a for a in search.legal_actions(state, cards)
                if isinstance(a, PlayUnit) and a.card_id == OTHER_UNIT and a.target_zone == "base")
    result = search.apply(state, play, cards)

    watcher = next(iter(result.battlefields[0].units))
    assert watcher.card_id == CITHRIA
    assert watcher.buffed is True
