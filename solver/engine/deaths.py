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

KNOWN GAP — the [Reaction] window. Each Deathknell resolution is a point
where the rules let a player respond with a [Reaction]-speed card, the
same way a showdown opens a window for [Action]/[Reaction] plays. That
window is NOT modelled here: no card in CARD_POOL has speed="Reaction",
so it can never be observed, and building a priority system with nothing
to exercise it would be dead machinery (search.py already folds away
showdown windows on exactly this reasoning). A tripwire in
tests/test_deathknell.py fails the moment a Reaction-speed card enters
the pool, so this stops being silent the instant it stops being true.

Imports of combat/actions are deliberately deferred into the effect
bodies: combat.py imports THIS module to fire the hook, so importing it
back at module scope would be a cycle.
"""

from __future__ import annotations

from typing import Callable

from .state import GameState, UnitInstance

Zone = str  # "base" or a battlefield_id

KOGMAW_CAUSTIC = "ogn-190-298"  # "Deal 4 to all units at my battlefield."
MACHINE_EVANGEL = "ogn-239-298"  # "Play three 1 Might Recruit unit tokens into your base."


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


# card_id -> effect(state, dead_unit, zone_it_died_in) -> GameState
#
# Effects are deterministic (single state, no player choice), which is
# what keeps this out of the adversarial AND-node machinery in search.py.
# A Deathknell offering a choice would need the list-returning shape
# abilities.UNIT_PLAY_TRIGGERS uses.
DEATH_TRIGGERS: dict[str, Callable[[GameState, UnitInstance, Zone], GameState]] = {
    KOGMAW_CAUSTIC: _kogmaw_effect,
    MACHINE_EVANGEL: _machine_evangel_effect,
}


def fire_death_triggers(state: GameState, dead: list[tuple[UnitInstance, Zone]]) -> GameState:
    """Resolve every registered Deathknell among `dead`, in instance_id
    order. Call AFTER the dead have been removed from the board — a
    trigger reads the state its own death produced, not the one before
    it."""
    for unit, zone in sorted(dead, key=lambda pair: pair[0].instance_id):
        effect = DEATH_TRIGGERS.get(unit.card_id)
        if effect is not None:
            state = effect(state, unit, zone)
    return state
