"""[Conquer] triggers — "When I conquer" (a unit) and "when you conquer
here" (a battlefield). Same "add mechanics on demand" policy and shape as
deaths.py: a per-card_id registry of deterministic single-state effects,
fired from the one choke point that already detects a genuine Conquer —
scoring.resolve_control_change, which runs exactly once regardless of
which action produced the control change (PlayUnit's open-battlefield
deploy, MoveUnit, ResolveCombat/ResolveShowdown's damage step, or a
control-changing spell/ability effect — see that function's docstring).

WHO CONQUERED, deliberately narrow: only the unit(s) that ARRIVE at
battlefield_id as part of the very action being resolved — the set
difference between who (of the new controller's units) stands there in
the state just before the change and the state just after. This needs no
new parameter threaded through every one of resolve_control_change's
several callers, because the answer is already fully determined by the
two states it's already given.

A unit already standing at a battlefield uncontested, which only gains
control because the last contesting enemy unit left by some OTHER effect
(a damage spell, say), is NOT treated as having conquered under this
model — restrictive rather than permissive, the same direction as
generate_rune_payments' documented incompleteness (search.py): it can
miss a hypothetical lethal that depends on that reading, but it can never
invent a trigger that didn't happen, which is the direction that matters
for a solver that must never bluff. No card in the pool needs the missing
case today.

BATTLEFIELD-keyed "when you conquer HERE" triggers are a different event
grammar — the player conquering a specific battlefield, not a specific
unit conquering — and aren't wired up here yet: every battlefield-effect
card whose conquer trigger has a real, fully-implementable effect (Zaun
Warrens' mandatory "discard 1, then draw 1") needs a CHOICE (which card to
discard). Baking that choice into MoveUnit/PlayUnit's params (2026-09-17
scoping pass, the way ShowdownState.attack_trigger_resolved and
PlayUnit.trigger_params already do it) turned out NOT to be enough on its
own: a battlefield can also change control via ResolveCombat/
ResolveShowdown (winning a fight for it), and scoring.resolve_control_change
is the one choke point common to all of them — so a Zaun Warrens cleared
only for the move/play paths would silently skip the discard on a
combat-won conquest, which is worse than leaving it blocking. Doing this
right needs resolve_control_change itself to fan out (a genuine list-
returning return type, threaded through its ~9 call sites in abilities.py/
legends.py/search.py) rather than a per-action-type param. Building that
machinery for one card would be its own deliberate pass, not a side effect
of the choice-trigger work — see coverage.py for how Zaun Warrens (and the
others gated on unbuilt subsystems: Sigil of the Storm on rune economy,
Qiyana on rune channelling, Kai'Sa Evolutionary and Super Mega Death
Rocket! on the trash zone) are left blocking instead.

Imports of abilities.py are deliberately deferred into the effect bodies:
abilities.py imports scoring.py (for scoring.resolve_control_change) and
scoring.py imports this module to fire the hook, so importing abilities
back at this module's top level would be a cycle — same trick deaths.py
uses for combat.py.
"""

from __future__ import annotations

from typing import Callable

from .state import GameState

SETT_BRAWLER = "ogn-164-298"  # "When I'm played and when I conquer, buff me."
SETT_BRAWLER_ALT = "ogn-164a-298"  # same card, alternate art — identical text


def _sett_conquer_effect(state: GameState, instance_id: int) -> GameState:
    """Buff is binary and already a no-op when the unit is buffed (this is
    also its "when I'm played" trigger's effect), so there's no case to
    special-case here even though Sett is very likely to already carry a
    buff by the time he conquers something."""
    from .abilities import apply_buff  # deferred — see module docstring
    return apply_buff(state, instance_id)


# card_id -> effect(state, conquering_unit_instance_id) -> GameState
#
# Effects are deterministic (single state, no player choice) — a Conquer
# trigger offering a choice needs the list-returning shape noted above,
# and isn't built.
CONQUER_TRIGGERS: dict[str, Callable[[GameState, int], GameState]] = {
    SETT_BRAWLER: _sett_conquer_effect,
    SETT_BRAWLER_ALT: _sett_conquer_effect,
}


def fire_conquer_triggers(old_state: GameState, new_state: GameState,
                           battlefield_id: str, controller: int) -> GameState:
    """Resolve every registered "when I conquer" trigger for units of
    `controller` that are present at `battlefield_id` in `new_state` but
    were NOT already there in `old_state` — see module docstring for why
    that's the definition of "conquered" used here. Call AFTER
    resolve_conquer, so an effect that reads score sees the point already
    granted."""
    old_bf = next(bf for bf in old_state.battlefields if bf.battlefield_id == battlefield_id)
    new_bf = next(bf for bf in new_state.battlefields if bf.battlefield_id == battlefield_id)
    already_there = {u.instance_id for u in old_bf.units if u.controller == controller}
    arrivals = [u for u in new_bf.units
                if u.controller == controller and u.instance_id not in already_there]
    for unit in sorted(arrivals, key=lambda u: u.instance_id):
        effect = CONQUER_TRIGGERS.get(unit.card_id)
        if effect is not None:
            new_state = effect(new_state, unit.instance_id)
    return new_state
