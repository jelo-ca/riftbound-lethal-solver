"""Combat resolution. See design/09-combat-resolution.md.

Attacker/Defender is determined by whose unit's move caused the Contested
status — NOT by who took the action. Since the opponent is tapped out, we
always take the action, but our own effects can move an ENEMY unit
(Charm, Blitzcrank), which makes the opponent the Attacker and us the
Defender for that combat.

This module only computes: sides, Might sums (incl. Assault/Shield),
valid damage-assignment enumerations, and the resulting board state for a
*specific* pair of assignments. It does NOT decide which assignments to
try or in what order (OR for ours, AND for the opponent's) — that
adversarial search lives in search.py, since it needs the solver's
recursion to evaluate "does this lead to a win," which this module has no
business knowing about.

Scope note: the attacking side is always exactly one unit here, since
our action space only ever moves a single unit per action (MoveUnit,
Ride The Wind). The rules allow multiple units to move together as a
single coordinated attack (rule 144.4) — not modeled, since nothing in
the action space produces it.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from . import deaths
from .state import BattlefieldState, GameState, ShowdownState, UnitInstance, replace_player
from .traits import effective_might

Assignment = tuple[tuple[int, int], ...]  # (instance_id, damage_amount) pairs


def _dead_among(before: frozenset[UnitInstance], after: frozenset[UnitInstance]) -> list[UnitInstance]:
    """Which of `before` didn't survive into `after`. Compared by
    instance_id, since survivors come back as fresh objects carrying
    updated damage."""
    survived = {u.instance_id for u in after}
    return [u for u in before if u.instance_id not in survived]


def determine_sides(state: GameState, mover: UnitInstance, destination_id: str):
    """Returns (attacker_controller, defender_controller, attacker_units,
    defender_units) for a move by `mover` into `destination_id`, which
    already has units present controlled by exactly one other player
    (rule: combat is only ever between exactly two players' units).
    `mover`'s controller is the Attacker (they caused the Contested
    status by moving); the battlefield's existing occupants' controller
    is the Defender — regardless of which one is `state.turn_player`.
    """
    destination = next(bf for bf in state.battlefields if bf.battlefield_id == destination_id)
    defender_controller = next(iter(destination.units)).controller
    attacker_units = frozenset({mover})
    defender_units = destination.units
    return mover.controller, defender_controller, attacker_units, defender_units


def is_combat_triggered(state: GameState, mover: UnitInstance, destination_id: str) -> bool:
    destination = next(bf for bf in state.battlefields if bf.battlefield_id == destination_id)
    if not destination.units:
        return False
    other_controller = next(iter(destination.units)).controller
    return other_controller != mover.controller


def our_assignment_options(state: GameState, mover: UnitInstance, destination_id: str) -> list[Assignment]:
    """All valid OUR-side damage-assignment choices for a combat triggered
    by `mover` moving to `destination_id` — regardless of whether that
    makes us the Attacker (our own unit moved) or the Defender (an effect
    of ours moved an *enemy* unit onto ground we hold, e.g. Blitzcrank).
    Generalizes what a Standard Move's candidate generation inlines
    (always-Attacker case) for any caller that doesn't know in advance
    which side it'll end up on.
    """
    attacker_ctrl, defender_ctrl, attacker_units, defender_units = determine_sides(state, mover, destination_id)
    we_are_attacker = attacker_ctrl == state.turn_player
    our_units = attacker_units if we_are_attacker else defender_units
    our_designation = "attacker" if we_are_attacker else "defender"
    target_units = defender_units if we_are_attacker else attacker_units
    target_designation = "defender" if we_are_attacker else "attacker"
    our_pool = sum(effective_might(state, u, destination_id, our_designation) for u in our_units)
    return enumerate_assignments(state, destination_id, target_units, our_pool, target_designation)


def enumerate_assignments(state: GameState, zone: str, targets: frozenset[UnitInstance], pool: int,
                           designation: Optional[str] = None) -> list[Assignment]:
    """All distinct valid ways to assign `pool` damage among `targets`,
    per the lethal-first rule (rule 465.2.c): a unit must receive its
    full remaining-lethal amount before a different unit can be targeted;
    the assigning player isn't required to touch every unit. Overkill
    beyond lethal isn't tracked separately (doesn't change which units
    die — see design/09-combat-resolution.md).

    `zone`/`designation` describe the TARGETS (the side receiving this
    damage), since what counts as lethal against them depends on their
    own effective Might — a 3-Might Shield unit being attacked needs 4,
    not 3."""
    target_list = sorted(targets, key=lambda u: u.instance_id)
    if pool <= 0 or not target_list:
        return [()]

    results: list[dict[int, int]] = []

    def recurse(remaining: list[UnitInstance], pool_left: int, assigned: dict[int, int]) -> None:
        if pool_left <= 0 or not remaining:
            results.append(dict(assigned))
            return
        for i, unit in enumerate(remaining):
            lethal_needed = max(1, effective_might(state, unit, zone, designation) - unit.damage)
            hit = min(lethal_needed, pool_left)
            next_assigned = dict(assigned)
            next_assigned[unit.instance_id] = next_assigned.get(unit.instance_id, 0) + hit
            rest = remaining[:i] + remaining[i + 1:]
            recurse(rest, pool_left - hit, next_assigned)
        if assigned:  # "stop here" is only a valid choice once something is committed
            results.append(dict(assigned))

    recurse(target_list, pool, {})

    seen: set[Assignment] = set()
    unique: list[Assignment] = []
    for r in results:
        key: Assignment = tuple(sorted(r.items()))
        if key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


def _apply_damage(state: GameState, zone: str, units: frozenset[UnitInstance], assignment: Assignment,
                   designation: Optional[str] = None) -> frozenset[UnitInstance]:
    """Marks damage per `assignment` and removes any unit whose damage
    now meets or exceeds its EFFECTIVE Might (dead — rule: Lethal Damage
    is non-zero damage >= Might). `zone`/`designation` are these units'
    own, so an Assault attacker / Shield defender / unit standing on a
    Might-granting battlefield is correspondingly harder to kill."""
    damage_by_id = dict(assignment)
    survivors = set()
    for unit in units:
        extra = damage_by_id.get(unit.instance_id, 0)
        new_damage = unit.damage + extra
        if new_damage < effective_might(state, unit, zone, designation):
            survivors.add(dataclasses.replace(unit, damage=new_damage))
    return frozenset(survivors)


def _heal(units: frozenset[UnitInstance]) -> frozenset[UnitInstance]:
    """Survivors of a resolved combat heal fully (rule: damage clears
    once the Combat Damage Step ends, not at end of turn) — direct
    effect damage via deal_damage_to_unit is unaffected, since that's
    not a combat resolution."""
    return frozenset(dataclasses.replace(u, damage=0) for u in units)


def deal_damage_to_unit(state: GameState, battlefield_id: str, target_instance_id: int, amount: int) -> GameState:
    """Direct, single-target damage from an effect outside the Combat
    Damage Step (e.g. Caitlyn - Patrolling's activated ability) — not a
    damage *assignment* choice, just a flat instruction. Removes the
    target if it dies and recomputes the battlefield's controller from
    whoever's left (rule 468: no units from any player -> Uncontrolled;
    only one controller's units remain -> that controller; this doesn't
    attempt to represent a genuinely mixed-controller Contested state
    beyond falling back to Uncontrolled, since nothing in the v0
    whitelist produces that case).
    """
    bf = next(b for b in state.battlefields if b.battlefield_id == battlefield_id)
    # designation=None: this isn't combat, so no Assault/Shield bonus applies
    # (a 3-Might Shield unit dies to 3 direct damage). The battlefield's own
    # flat bonus is positional, so it still counts.
    remaining = _apply_damage(state, battlefield_id, bf.units, ((target_instance_id, amount),), None)
    controllers = {u.controller for u in remaining}
    new_controller = next(iter(controllers)) if len(controllers) == 1 else None
    state = _replace_battlefield(state, dataclasses.replace(bf, units=remaining, controller=new_controller))
    return deaths.fire_death_triggers(
        state, [(u, battlefield_id) for u in _dead_among(bf.units, remaining)])


def deal_damage_to_all_at(state: GameState, battlefield_id: str, amount: int) -> GameState:
    """Flat damage to every unit at a battlefield, both controllers' —
    for an effect that doesn't choose targets (Kog'Maw, Caustic's
    Deathknell: "Deal 4 to all units at my battlefield"). Like
    deal_damage_to_unit this is an effect rather than a Combat Damage
    Step assignment, so designation is None: no Assault/Shield bonus
    applies against it."""
    bf = next(b for b in state.battlefields if b.battlefield_id == battlefield_id)
    if not bf.units:
        return state
    assignment = tuple((u.instance_id, amount) for u in bf.units)
    remaining = _apply_damage(state, battlefield_id, bf.units, assignment, None)
    controllers = {u.controller for u in remaining}
    new_controller = next(iter(controllers)) if len(controllers) == 1 else None
    state = _replace_battlefield(state, dataclasses.replace(bf, units=remaining, controller=new_controller))
    # Whatever this killed fires its own Deathknell — that recursion is
    # the cascade, and it terminates because each pass removes its own
    # trigger's unit from the board.
    return deaths.fire_death_triggers(
        state, [(u, battlefield_id) for u in _dead_among(bf.units, remaining)])


def open_showdown(state: GameState, mover: UnitInstance, from_zone: str, destination_id: str,
                   exhausted_after: bool = True) -> GameState:
    """Moves `mover` into `destination_id`, applying Contested status and
    opening a showdown — WITHOUT resolving damage. The two halves are
    separate because card speeds make the gap between them observable:
    an [Action]/[Reaction] card can be played after the move and before
    the Combat Damage Step (Ride The Wind moving a unit in to join the
    fight, or out of it to dodge).

    Both sides stay on the battlefield with the mover among them and no
    controller, which is what Contested means (rule 190.6). Damage is
    resolve_showdown's job.
    """
    destination = next(bf for bf in state.battlefields if bf.battlefield_id == destination_id)
    moved_mover = dataclasses.replace(mover, exhausted=exhausted_after,
                                       moved_this_turn=mover.moved_this_turn + 1)
    state = _remove_from_origin(state, mover, from_zone)
    destination = next(bf for bf in state.battlefields if bf.battlefield_id == destination_id)
    contested = dataclasses.replace(destination, units=destination.units | {moved_mover},
                                     controller=None)
    state = _replace_battlefield(state, contested)
    return dataclasses.replace(
        state, showdown=ShowdownState(battlefield_id=destination_id,
                                       attacker_controller=mover.controller))


def resolve_showdown(state: GameState, attacker_assignment: Assignment,
                      defender_assignment: Assignment) -> GameState:
    """The Combat Damage Step for the open showdown: both sides assign
    simultaneously, the dead are removed, survivors heal, and control
    resolves. Which units count as attackers is read from the showdown's
    `attacker_controller` rather than passed in — by now other cards may
    have moved units into or out of the fight, so the participants are
    whatever is standing there at this moment.
    """
    assert state.showdown is not None
    showdown = state.showdown
    bf = next(b for b in state.battlefields if b.battlefield_id == showdown.battlefield_id)
    attacker_units = frozenset(u for u in bf.units if u.controller == showdown.attacker_controller)
    defender_units = frozenset(u for u in bf.units if u.controller != showdown.attacker_controller)

    surviving_attackers = _heal(
        _apply_damage(state, showdown.battlefield_id, attacker_units, defender_assignment, "attacker"))
    surviving_defenders = _heal(
        _apply_damage(state, showdown.battlefield_id, defender_units, attacker_assignment, "defender"))

    if surviving_attackers and not surviving_defenders:
        new_controller = showdown.attacker_controller
    elif surviving_defenders and not surviving_attackers:
        new_controller = next(iter(surviving_defenders)).controller
    else:
        # Nobody left (rule 468) or both sides still present (rule 190.6).
        new_controller = None

    resolved = dataclasses.replace(bf, units=surviving_attackers | surviving_defenders,
                                    controller=new_controller)
    state = dataclasses.replace(_replace_battlefield(state, resolved), showdown=None)
    dead = _dead_among(attacker_units, surviving_attackers) + _dead_among(defender_units, surviving_defenders)
    return deaths.fire_death_triggers(state, [(u, showdown.battlefield_id) for u in dead])


def showdown_assignment_options(state: GameState, for_controller: int) -> list[Assignment]:
    """Damage-assignment choices for `for_controller`'s side of the open
    showdown, against whatever is standing on the other side right now."""
    assert state.showdown is not None
    bf = next(b for b in state.battlefields if b.battlefield_id == state.showdown.battlefield_id)
    ours = frozenset(u for u in bf.units if u.controller == for_controller)
    theirs = frozenset(u for u in bf.units if u.controller != for_controller)
    if not ours or not theirs:
        return [()]
    our_designation = "attacker" if for_controller == state.showdown.attacker_controller else "defender"
    their_designation = "defender" if our_designation == "attacker" else "attacker"
    pool = sum(effective_might(state, u, bf.battlefield_id, our_designation) for u in ours)
    return enumerate_assignments(state, bf.battlefield_id, theirs, pool, their_designation)


def _remove_from_origin(state: GameState, mover: UnitInstance, from_zone: str) -> GameState:
    if from_zone == "base":
        player = state.players[mover.controller]
        return replace_player(state, mover.controller,
                               dataclasses.replace(player, base_units=player.base_units - {mover}))
    origin = next(bf for bf in state.battlefields if bf.battlefield_id == from_zone)
    remaining = origin.units - {mover}
    origin_controller = origin.controller if remaining else None
    return _replace_battlefield(
        state, dataclasses.replace(origin, units=remaining, controller=origin_controller))


def apply_combat(state: GameState, mover: UnitInstance, from_zone: str, destination_id: str,
                  attacker_assignment: Assignment, defender_assignment: Assignment,
                  exhausted_after: bool = True) -> GameState:
    """Resolves one full combat instance for a specific pair of
    assignments: moves `mover` into `destination_id` (exhausting it per
    rule 145.1 for a Standard Move, or not — `exhausted_after=False` for
    a spell-granted move like Ride The Wind that readies instead), applies
    both assignments simultaneously, removes the dead, and resolves
    control (rule 466.7.b: the side with units remaining controls the
    battlefield; if both sides still have survivors, it stays
    Contested/uncontrolled — rule 190.6). Does not resolve scoring
    consequences of any resulting control change; that's still the
    caller's job via scoring.resolve_control_change, same as every other
    control-establishing action.
    """
    destination = next(bf for bf in state.battlefields if bf.battlefield_id == destination_id)
    moved_mover = dataclasses.replace(mover, exhausted=exhausted_after, moved_this_turn=mover.moved_this_turn + 1)
    attacker_units = frozenset({moved_mover})
    defender_units = destination.units

    # Combat resolves AT the destination, so its effects apply to both
    # sides — including the attacker moving in (Trifarian War Camp's text
    # says so explicitly: "This includes attackers").
    surviving_attackers = _heal(
        _apply_damage(state, destination_id, attacker_units, defender_assignment, "attacker"))
    surviving_defenders = _heal(
        _apply_damage(state, destination_id, defender_units, attacker_assignment, "defender"))

    # Remove the mover from its origin zone (it's now at the destination,
    # dead or alive — either way it leaves `from_zone`).
    if from_zone == "base":
        player = state.players[mover.controller]
        new_player = dataclasses.replace(player, base_units=player.base_units - {mover})
        state = replace_player(state, mover.controller, new_player)
    else:
        origin = next(bf for bf in state.battlefields if bf.battlefield_id == from_zone)
        remaining = origin.units - {mover}
        origin_controller = origin.controller if remaining else None
        state = _replace_battlefield(
            state, dataclasses.replace(origin, units=remaining, controller=origin_controller)
        )

    if surviving_attackers and not surviving_defenders:
        new_controller = mover.controller
    elif surviving_defenders and not surviving_attackers:
        new_controller = next(iter(surviving_defenders)).controller
    elif not surviving_attackers and not surviving_defenders:
        new_controller = None  # rule 468: no units from any player -> Uncontrolled
    else:
        new_controller = None  # rule 190.6: both sides still present -> stays Contested/uncontrolled

    new_bf = dataclasses.replace(
        destination, units=surviving_attackers | surviving_defenders, controller=new_controller
    )
    state = _replace_battlefield(state, new_bf)
    dead = _dead_among(attacker_units, surviving_attackers) + _dead_among(defender_units, surviving_defenders)
    return deaths.fire_death_triggers(state, [(u, destination_id) for u in dead])


def enumerate_combat_outcomes(state: GameState, mover: UnitInstance, from_zone: str, destination_id: str,
                               our_assignment: Assignment,
                               exhausted_after: bool = True) -> list[GameState]:
    """All possible resulting states for a combat-triggering move, one per
    possible opponent response to `our_assignment` — the enumeration
    itself (used by both search.py's AND-node and export.py's graph BFS,
    so it lives here rather than duplicated in each). Doesn't decide
    which outcomes are acceptable, and doesn't resolve scoring
    consequences of any resulting control change — same division of
    responsibility as apply_combat.

    `exhausted_after` defaults to True for the Standard Move case (rule
    145.1: exhausting the unit is part of that action's cost). An
    EFFECT-granted move into combat (Charm, Blitzcrank's redirect) must
    pass the mover's existing exhaustion instead — an effect-granted move
    doesn't exhaust unless the card says so.
    """
    attacker_ctrl, defender_ctrl, attacker_units, defender_units = determine_sides(state, mover, destination_id)
    we_are_attacker = attacker_ctrl == state.turn_player

    # opponent_units: the OPPONENT's own units, whose Might sums to their
    # pool. opponent_targets: OUR units, which is what that pool gets
    # assigned to. These are opposite sides - conflating them was a real
    # bug caught by test_and_node_accepts_when_every_opponent_response_still_wins
    # (it silently produced a single all-zero "opponent did nothing"
    # outcome instead of enumerating real opponent choices).
    if we_are_attacker:
        opponent_units, opponent_designation, opponent_targets = defender_units, "defender", attacker_units
        target_designation = "attacker"
    else:
        opponent_units, opponent_designation, opponent_targets = attacker_units, "attacker", defender_units
        target_designation = "defender"

    opponent_pool = sum(effective_might(state, u, destination_id, opponent_designation) for u in opponent_units)

    outcomes = []
    for opponent_assignment in enumerate_assignments(state, destination_id, opponent_targets, opponent_pool,
                                                      target_designation):
        attacker_assignment = our_assignment if we_are_attacker else opponent_assignment
        defender_assignment = opponent_assignment if we_are_attacker else our_assignment
        outcomes.append(apply_combat(
            state, mover, from_zone, destination_id, attacker_assignment, defender_assignment,
            exhausted_after=exhausted_after,
        ))
    return outcomes


def _replace_battlefield(state: GameState, updated: BattlefieldState) -> GameState:
    battlefields = tuple(
        updated if bf.battlefield_id == updated.battlefield_id else bf for bf in state.battlefields
    )
    return dataclasses.replace(state, battlefields=battlefields)
