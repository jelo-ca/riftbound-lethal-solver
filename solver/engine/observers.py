"""Observer triggers — "when you play ANOTHER unit," as opposed to a card's
own "when you play me" (abilities.UNIT_PLAY_TRIGGERS). The watching unit
doesn't have to be the one entering play; it has to already be on the
board, watching.

Fired from actions.apply_play_unit, the single choke point every genuine
unit-from-hand play routes through (mint_token_unit is a different path
and deliberately does NOT fire this — minting a token isn't "playing" a
card, the same reasoning that keeps it off cards_played_this_turn).

Deterministic effects only, same policy as conquer.py/deaths.py: a
watcher whose effect offers a choice would need the list-returning shape
abilities.UNIT_PLAY_TRIGGERS uses, and none registered here does.

Imports of abilities.py are deferred into the effect bodies for the same
reason conquer.py/deaths.py defer theirs: actions.py is imported BY
abilities.py, so importing abilities back at this module's top level
would cycle.
"""

from __future__ import annotations

from typing import Callable

from .state import GameState, UnitInstance

CITHRIA_OF_CLOUDFIELD = "ogn-139-298"  # "When you play another unit, buff me."


def _cithria_effect(state: GameState, watcher: UnitInstance, played: UnitInstance) -> GameState:
    """Buff is binary (abilities.apply_buff already no-ops if she's already
    buffed), so there's no case to special-case for a Cithria who has
    triggered before."""
    from .abilities import apply_buff  # deferred — see module docstring
    return apply_buff(state, watcher.instance_id)


# card_id -> effect(state, watching_unit, played_unit) -> GameState
#
# Effects are deterministic (single state, no player choice) — see module
# docstring.
OBSERVER_PLAY_TRIGGERS: dict[str, Callable[[GameState, UnitInstance, UnitInstance], GameState]] = {
    CITHRIA_OF_CLOUDFIELD: _cithria_effect,
}


def _our_units(state: GameState, controller: int) -> list[UnitInstance]:
    found = list(state.players[controller].base_units)
    for bf in state.battlefields:
        found.extend(u for u in bf.units if u.controller == controller)
    return found


def fire_observer_play_triggers(state: GameState, played: UnitInstance) -> GameState:
    """Resolve every registered observer among `played`'s controller's
    OTHER units — "another unit," so `played` never watches its own play,
    which matters the turn a watcher is the card being played. Fires in
    instance_id order for determinism when more than one watcher is
    present."""
    watchers = sorted(
        (u for u in _our_units(state, played.controller)
         if u.instance_id != played.instance_id and u.card_id in OBSERVER_PLAY_TRIGGERS),
        key=lambda u: u.instance_id,
    )
    for watcher in watchers:
        effect = OBSERVER_PLAY_TRIGGERS[watcher.card_id]
        state = effect(state, watcher, played)
    return state


JINX_REBEL = "ogn-202-298"  # "When you discard one or more cards, ready me and give me +1 Might this turn."
JINX_REBEL_ALT = "ogn-202a-298"  # same card, alternate art


def _jinx_rebel_effect(state: GameState, watcher: UnitInstance) -> GameState:
    """No target and no "another" restriction — Jinx watches her OWN
    controller discard and reacts to it herself, unlike Cithria watching
    someone else's play. `ready_unit`/`_grant_might` are already no-ops
    where there's nothing to change (ready_unit on an already-ready unit),
    so a Jinx who discards twice in one effect just gets readied once and
    +1 Might once per call — matching how many times THIS function runs,
    which fire_observer_discard_triggers's caller controls (see this
    module's docstring, and actions.discard_from_hand's)."""
    from .abilities import _grant_might, ready_unit  # deferred — see module docstring
    state = ready_unit(state, watcher.instance_id)
    return _grant_might(state, watcher.instance_id, 1)


# card_id -> effect(state, watching_unit) -> GameState
#
# Unlike OBSERVER_PLAY_TRIGGERS, there is no "played" unit to pass through:
# a discard event names a card_id and a controller, not a UnitInstance, and
# no registered effect here needs to know WHICH card was discarded.
OBSERVER_DISCARD_TRIGGERS: dict[str, Callable[[GameState, UnitInstance], GameState]] = {
    JINX_REBEL: _jinx_rebel_effect,
    JINX_REBEL_ALT: _jinx_rebel_effect,
}


def fire_observer_discard_triggers(state: GameState, discarding_controller: int) -> GameState:
    """Resolve every registered observer controlled by `discarding_controller`
    — "when YOU discard" names the watching card's OWN controller, so this
    correctly fires for an enemy watcher when WE force the opponent to
    discard from their own hand (Mindsplitter), not just for our own
    discards. Call exactly ONCE per discard EVENT (see this module's and
    actions.discard_from_hand's docstrings) — "discard 2" is one event
    encompassing two cards, not two events."""
    watchers = sorted(
        (u for u in _our_units(state, discarding_controller)
         if u.card_id in OBSERVER_DISCARD_TRIGGERS),
        key=lambda u: u.instance_id,
    )
    for watcher in watchers:
        effect = OBSERVER_DISCARD_TRIGGERS[watcher.card_id]
        state = effect(state, watcher)
    return state
