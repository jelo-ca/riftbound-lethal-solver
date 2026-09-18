"""[Conquer] triggers — "When I conquer" (a unit) and "when you conquer
here" (a battlefield). Same "add mechanics on demand" policy as
deaths.py: a per-card_id registry, fired from the one choke point that
already detects a genuine Conquer — scoring.resolve_control_change, which
runs exactly once regardless of which action produced the control change
(PlayUnit's open-battlefield deploy, MoveUnit, ResolveCombat/
ResolveShowdown's damage step, or a control-changing spell/ability effect
— see that function's docstring).

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
unit conquering — implemented below in BATTLEFIELD_CONQUER_TRIGGERS,
parallel to the unit-keyed CONQUER_TRIGGERS/CONQUER_TRIGGERS_WITH_CHOICE.

CHOICE-BEARING TRIGGERS (Zaun Warrens' mandatory "discard 1, then draw 1",
Kai'Sa Evolutionary's optional "play a spell from your trash") need a
genuine player choice, which the ORIGINAL deterministic-single-state
CONQUER_TRIGGERS/BATTLEFIELD_EFFECTS shape can't express. A 2026-09-17
scoping pass considered baking the choice into each of resolve_control_
change's ~9 callers' own action types (MoveUnit/PlayUnit/ResolveCombat/
ResolveShowdown all gaining a field the way ShowdownState.attack_trigger_
resolved and PlayUnit.trigger_params already do it) and rejected it: a
battlefield can change control via combat as well as a move/play, and
duplicating the same field across every action type that can possibly
cause a conquer — several of them in DIFFERENT modules (abilities.py's
spell/ability effects, legends.py's Legend abilities) — means a card
cleared only for SOME of those paths silently skips its trigger on
whichever path was missed, which is worse than leaving it blocking.

The fix actually shipped here is GameState.pending_conquer_choice (see
state.py): when a registered trigger needs a real choice, resolve_control_
change (via fire_conquer_triggers/fire_battlefield_conquer_triggers below)
returns a state with the choice PENDING rather than resolved, and
search.legal_actions() offers nothing but ResolveConquerTrigger until it's
picked. This achieves the same goal the "list-returning resolve_control_
change" design was reaching for — a genuine OR-branch over OUR OWN choice,
reachable through every one of the 9 callers uniformly — without actually
changing resolve_control_change's signature or any of its callers: a new
GameState field flows through all of them for free, because every one of
them already threads its resulting state back via `dataclasses.replace`/
`replace_player`/`replace_battlefield` rather than reconstructing GameState
from scratch. It also sidesteps a real correctness trap a bare list return
would have hit: `_and_or_search` merges a list of outcomes with AND
semantics (every one must still lead to a win) because that's what
adversarial branching needs — reusing it for OUR OWN choice would wrongly
require every possible discard to work, not just one. Modelling the choice
as its own action (ResolveConquerTrigger, generated per candidate, tried by
the ordinary OR loop in search._dfs) gets true OR semantics for free and
also keeps the choice recorded in solve()'s strategy map, which a bare
list of resulting states with no distinguishing action could not do.

Only ONE pending choice is representable at a time (PendingConquerChoice
is a single field, not a queue) — see fire_conquer_triggers/fire_
battlefield_conquer_triggers below for how that narrows in the rare case
of two choice-bearing triggers firing off the very same conquer event.
Restrictive, not permissive: no card in the pool needs the missing case
today.

Sigil of the Storm (rune economy), Qiyana (rune channelling), and Super
Mega Death Rocket! (a *third* event grammar — see coverage.py: it watches
"you conquered ANY battlefield" from trash, not a specific unit or
battlefield conquering, closer to observers.py's shape than either
grammar here) remain blocking on their own unbuilt subsystems.

Imports of abilities.py are deliberately deferred into the effect bodies:
abilities.py imports scoring.py (for scoring.resolve_control_change) and
scoring.py imports this module to fire the hook, so importing abilities
back at this module's top level would be a cycle — same trick deaths.py
uses for combat.py.
"""

from __future__ import annotations

import dataclasses
from typing import Callable

from .state import GameState, PendingConquerChoice, replace_player

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
# Deterministic (single state, no player choice) — see
# CONQUER_TRIGGERS_WITH_CHOICE below for the shape a choice needs.
CONQUER_TRIGGERS: dict[str, Callable[[GameState, int], GameState]] = {
    SETT_BRAWLER: _sett_conquer_effect,
    SETT_BRAWLER_ALT: _sett_conquer_effect,
}


KAISA_EVOLUTIONARY = "ogn-112-298"  # [Ganking] "When I conquer, you may play a
# spell from your trash with Energy cost less than your points, without
# paying its Energy cost. Then recycle it. (Must still pay Power cost.)"
KAISA_EVOLUTIONARY_ALT = "ogn-112a-298"  # same card, alternate art


def _kaisa_candidates(state: GameState, instance_id: int) -> list[tuple]:
    from .abilities import kaisa_evolutionary_candidates  # deferred — see module docstring
    return kaisa_evolutionary_candidates(state, instance_id)


def _kaisa_effect(state: GameState, instance_id: int, params: tuple) -> GameState:
    from .abilities import kaisa_evolutionary_effect  # deferred — see module docstring
    return kaisa_evolutionary_effect(state, instance_id, params)


# card_id -> (generate_candidates(state, instance_id) -> list[tuple],
#             effect(state, instance_id, params) -> GameState)
#
# `params == ()` is always the "decline" candidate for these — every
# registered entry today is a "you may". A mandatory unit-keyed choice
# trigger would need its own convention (no decline candidate), same as
# BATTLEFIELD_CONQUER_TRIGGERS' Zaun Warrens below; none is registered yet.
CONQUER_TRIGGERS_WITH_CHOICE: dict[str, tuple[
    Callable[[GameState, int], list[tuple]],
    Callable[[GameState, int, tuple], GameState],
]] = {
    KAISA_EVOLUTIONARY: (_kaisa_candidates, _kaisa_effect),
    KAISA_EVOLUTIONARY_ALT: (_kaisa_candidates, _kaisa_effect),
}


ZAUN_WARRENS = "ogn-298-298"  # Battlefield: "When you conquer here, discard 1, then draw 1."


def _zaun_warrens_candidates(state: GameState, battlefield_id: str) -> list[tuple]:
    """One candidate per hand card to discard, or the single `()`
    candidate meaning "nothing to discard" when hand is empty. Real
    Riftbound discard fizzles against an empty hand rather than blocking
    the conquest that triggered it — unlike a MANDATORY_PLAY_TRIGGERS
    target (an enemy unit that might not exist on the board), "discard 1"
    names the player's OWN hand, and "as many as possible" is a
    well-defined answer (zero) rather than an unrepresentable one."""
    hand = sorted(set(state.players[state.turn_player].hand))
    return [(card_id,) for card_id in hand] or [()]


def _zaun_warrens_effect(state: GameState, battlefield_id: str, params: tuple) -> GameState:
    """"Then draw 1" is a no-op — no Main Deck, same reasoning already
    settled for every other draw effect in coverage.py (e.g. Watchful
    Sentry, Progress Day). Discarding sends the card to trash, the same
    zone a resolved spell lands in (actions.apply_play_spell_cost) — a
    discard isn't a "recycle," so nothing sends it to the (nonexistent)
    Main Deck instead."""
    if not params:
        return state
    (card_id,) = params
    controller = state.turn_player
    player = state.players[controller]
    new_hand = list(player.hand)
    new_hand.remove(card_id)
    new_player = dataclasses.replace(player, hand=tuple(new_hand),
                                     trash=player.trash + (card_id,))
    return replace_player(state, controller, new_player)


# battlefield_effect_id -> (generate_candidates(state, battlefield_id) -> list[tuple],
#                           effect(state, battlefield_id, params) -> GameState)
#
# Zaun Warrens is MANDATORY (no "you may" in the text), so its candidate
# list never includes a bare decline the way CONQUER_TRIGGERS_WITH_CHOICE's
# entries do — only real choices, one of which may itself do nothing
# (discarding from an empty hand).
BATTLEFIELD_CONQUER_TRIGGERS: dict[str, tuple[
    Callable[[GameState, str], list[tuple]],
    Callable[[GameState, str, tuple], GameState],
]] = {
    ZAUN_WARRENS: (_zaun_warrens_candidates, _zaun_warrens_effect),
}


def fire_conquer_triggers(old_state: GameState, new_state: GameState,
                           battlefield_id: str, controller: int) -> GameState:
    """Resolve every registered "when I conquer" trigger for units of
    `controller` that are present at `battlefield_id` in `new_state` but
    were NOT already there in `old_state` — see module docstring for why
    that's the definition of "conquered" used here. Call AFTER
    resolve_conquer, so an effect that reads score sees the point already
    granted.

    A choice-bearing trigger (CONQUER_TRIGGERS_WITH_CHOICE) doesn't
    resolve here — it sets `new_state.pending_conquer_choice` and leaves
    the actual effect to ResolveConquerTrigger (see module docstring).
    Only one pending choice is representable at a time: if several
    arrivals this event carry a registered choice trigger, only the first
    (lowest instance_id) gets to open one; restrictive, not permissive,
    and no card in the pool needs the missing case today.
    """
    old_bf = next(bf for bf in old_state.battlefields if bf.battlefield_id == battlefield_id)
    new_bf = next(bf for bf in new_state.battlefields if bf.battlefield_id == battlefield_id)
    already_there = {u.instance_id for u in old_bf.units if u.controller == controller}
    arrivals = [u for u in new_bf.units
                if u.controller == controller and u.instance_id not in already_there]
    for unit in sorted(arrivals, key=lambda u: u.instance_id):
        if unit.card_id in CONQUER_TRIGGERS_WITH_CHOICE:
            if new_state.pending_conquer_choice is None:
                new_state = dataclasses.replace(
                    new_state, pending_conquer_choice=PendingConquerChoice(
                        kind="unit", key=unit.card_id, battlefield_id=battlefield_id,
                        instance_id=unit.instance_id))
            continue
        effect = CONQUER_TRIGGERS.get(unit.card_id)
        if effect is not None:
            new_state = effect(new_state, unit.instance_id)
    return new_state


def fire_battlefield_conquer_triggers(state: GameState, battlefield_id: str) -> GameState:
    """Resolve the registered "when you conquer here" trigger for
    `battlefield_id`'s printed effect, if any. Call from
    scoring.resolve_control_change AFTER fire_conquer_triggers, and skip
    entirely if that already left a choice pending — see
    fire_conquer_triggers' docstring: a board combining a choice-bearing
    unit AND a choice-bearing battlefield conquered in the very same event
    is a real, currently unhandled edge case (restrictive, not permissive
    — the battlefield trigger simply doesn't fire that turn rather than
    the engine guessing at an order). No card in the pool needs it today.

    A candidate set of exactly one (Zaun Warrens against an empty hand, or
    any future registrant whose choices happen to collapse to one) is
    resolved immediately rather than opening a pending window over a
    foregone conclusion.
    """
    if state.pending_conquer_choice is not None:
        return state
    bf = next(b for b in state.battlefields if b.battlefield_id == battlefield_id)
    entry = BATTLEFIELD_CONQUER_TRIGGERS.get(bf.effect_id)
    if entry is None:
        return state
    generate_candidates, effect = entry
    candidates = generate_candidates(state, battlefield_id)
    if len(candidates) == 1:
        return effect(state, battlefield_id, candidates[0])
    return dataclasses.replace(state, pending_conquer_choice=PendingConquerChoice(
        kind="battlefield", key=bf.effect_id, battlefield_id=battlefield_id))


def pending_choice_candidates(state: GameState) -> list[tuple]:
    """Every legal `ResolveConquerTrigger.params` for
    `state.pending_conquer_choice` — the only actions
    search.legal_actions() offers while one is pending."""
    pending = state.pending_conquer_choice
    assert pending is not None
    if pending.kind == "unit":
        generate_candidates, _ = CONQUER_TRIGGERS_WITH_CHOICE[pending.key]
        return generate_candidates(state, pending.instance_id)
    generate_candidates, _ = BATTLEFIELD_CONQUER_TRIGGERS[pending.key]
    return generate_candidates(state, pending.battlefield_id)


def apply_pending_choice(state: GameState, params: tuple) -> GameState:
    """Resolves `state.pending_conquer_choice` per the chosen `params`,
    clearing the pending marker first (effects read a state that's no
    longer pending, same as ShowdownState being cleared before
    resolve_showdown's own effects run)."""
    pending = state.pending_conquer_choice
    assert pending is not None
    state = dataclasses.replace(state, pending_conquer_choice=None)
    if pending.kind == "unit":
        _, effect = CONQUER_TRIGGERS_WITH_CHOICE[pending.key]
        return effect(state, pending.instance_id, params)
    _, effect = BATTLEFIELD_CONQUER_TRIGGERS[pending.key]
    return effect(state, pending.battlefield_id, params)
