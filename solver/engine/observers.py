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
