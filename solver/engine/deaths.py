"""[Deathknell] — "When I die, get the effect."

Per-card registry, same "add mechanics on demand" policy as abilities.py.
The hook itself is the load-bearing part: units are removed in three
places inside combat.py (`apply_combat`, `resolve_showdown`,
`deal_damage_to_unit`) plus `actions.kill_unit`'s Base path, and until
now nothing fired on any of them.

Cascades resolve recursively and terminate on their own: an effect that
kills more units fires their triggers in turn, and a unit is removed
before its own trigger runs, so the recursion is bounded by the number
of units on the board. Triggers fire in instance_id order when several
units die at once, which only matters if one effect changes what another
sees.

KNOWN GAP — the [Reaction] window, now live rather than hypothetical.
Each Deathknell resolution is a point where the rules let a player
respond with a [Reaction]-speed card, and Reaction cards are now
implemented (Flurry of Blades, Gust, Smoke Screen). No window is offered
here, so a line like "Kog'Maw's blast is about to kill my unit, buff it
in response" cannot be found.

Scope of the gap, measured rather than assumed. Reaction cards ARE
playable inside showdowns — search._showdown_actions admits both
[Action] and [Reaction], and a test pins it — and that is the larger of
the two windows, since it is where combat is decided. What is missing is
only the narrower trigger-resolution window.

A full resolution stack is deliberately NOT built. Of the 21 Reaction
cards in Origins, exactly three reference an unresolved spell (Defy and
Wind Wall counter one, Mystic Reversal steals one) and only those need a
stack at all. All three are inert here for an unrelated reason: the
opponent never acts, so no opposing spell can exist to respond to, and
countering your own is never better than not casting it. For the other
eighteen, "respond to my own effect" resolves in the same order as
playing it first, so a stack would add no expressible line.

Imports of combat/actions are deliberately deferred into the effect
bodies: combat.py imports THIS module to fire the hook, so importing it
back at module scope would be a cycle.
"""

from __future__ import annotations

import dataclasses
from typing import Callable

from .state import GameState, UnitInstance, replace_player

Zone = str  # "base" or a battlefield_id

KOGMAW_CAUSTIC = "ogn-190-298"  # "Deal 4 to all units at my battlefield."
MACHINE_EVANGEL = "ogn-239-298"  # "Play three 1 Might Recruit unit tokens into your base."
EKKO_RECURRENT = "ogn-110-298"  # "Recycle me to ready your runes."


def _kogmaw_effect(state: GameState, unit: UnitInstance, zone: Zone) -> GameState:
    """"Deal 4 to all units at my battlefield" — friendly ones included,
    the text doesn't restrict it. A Kog'Maw that dies at Base has no
    battlefield to speak of, so the trigger simply finds nothing.

    The damage lands on whoever is standing there once the death that
    triggered this has been resolved; a unit that died in the same damage
    step is already gone and can't be hit twice, while one that survived
    on non-lethal damage takes the extra 4 and may well die to it — which
    is the case that actually matters.
    """
    if zone == "base":
        return state
    from . import combat  # deferred: combat imports this module
    return combat.deal_damage_to_all_at(state, zone, 4)


def _machine_evangel_effect(state: GameState, unit: UnitInstance, zone: Zone) -> GameState:
    """"...into your base" — not "here", so the tokens land at Base
    regardless of where this unit died."""
    from .abilities import RECRUIT_TOKEN_CARD  # deferred: abilities -> actions -> combat -> here
    from .actions import mint_token_unit
    for _ in range(3):
        state = mint_token_unit(state, RECRUIT_TOKEN_CARD, unit.controller, "base")
    return state


def _ekko_effect(state: GameState, unit: UnitInstance, zone: Zone) -> GameState:
    """"Recycle me to ready your runes." Readying restores Energy capacity
    on runes already Exhausted this turn, which is real resource: it can
    pay for another card after the board already looked tapped out.

    "Recycle me" is where the dying card goes, not a cost to weigh — it is
    already leaving the board, and no trash or rune deck is modelled, so
    the only observable half is the readying.
    """
    from .state import ready_runes  # deferred purely for symmetry with the others
    player = state.players[unit.controller]
    return replace_player(state, unit.controller,
                          dataclasses.replace(player, runes=ready_runes(player.runes)))


# card_id -> effect(state, dead_unit, zone_it_died_in) -> GameState
#
# Effects are deterministic (single state, no player choice), which is
# what keeps this out of the adversarial AND-node machinery in search.py.
# A Deathknell offering a choice would need the list-returning shape
# abilities.UNIT_PLAY_TRIGGERS uses.
DEATH_TRIGGERS: dict[str, Callable[[GameState, UnitInstance, Zone], GameState]] = {
    KOGMAW_CAUSTIC: _kogmaw_effect,
    MACHINE_EVANGEL: _machine_evangel_effect,
    EKKO_RECURRENT: _ekko_effect,
}

# Cards whose own death text redirects the dying card somewhere OTHER
# than trash — excluded from the blanket "dead cards land in trash" rule
# below. Ekko's "recycle me" means back to the (nonexistent) Main Deck,
# not the trash a card like Cemetery Attendant could return him from.
RECYCLED_ON_DEATH = frozenset({EKKO_RECURRENT})


def _send_to_trash(state: GameState, unit: UnitInstance) -> GameState:
    """Every dying card lands in its controller's trash — except a token
    (never a printed card; it ceases to exist rather than occupying a
    zone) or a card whose own text redirects it elsewhere on death."""
    if unit.is_token or unit.card_id in RECYCLED_ON_DEATH:
        return state
    player = state.players[unit.controller]
    return replace_player(state, unit.controller,
                          dataclasses.replace(player, trash=player.trash + (unit.card_id,)))


def fire_death_triggers(state: GameState, dead: list[tuple[UnitInstance, Zone]]) -> GameState:
    """Send each dead unit to trash, then resolve any registered
    Deathknell among `dead`, in instance_id order. Call AFTER the dead
    have been removed from the board — a trigger reads the state its own
    death produced, not the one before it."""
    for unit, zone in sorted(dead, key=lambda pair: pair[0].instance_id):
        state = _send_to_trash(state, unit)
        effect = DEATH_TRIGGERS.get(unit.card_id)
        if effect is not None:
            state = effect(state, unit, zone)
    return state
