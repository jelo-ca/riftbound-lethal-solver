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
import re

from .state import BattlefieldState, GameState, UnitInstance, replace_player

Assignment = tuple[tuple[int, int], ...]  # (instance_id, damage_amount) pairs

_KEYWORD_BONUS = re.compile(r"^(Assault|Shield)(?: (\d+))?$")


def unit_combat_might(unit: UnitInstance, designation: str) -> int:
    """Effective Might for Combat Damage Step summing, including Assault
    ("+Might while I'm an attacker") / Shield ("+Might while I'm a
    defender") — read directly off keyword text, e.g. "Assault 2" -> +2,
    bare "Assault" -> +1. `designation` is "attacker" or "defender"."""
    bonus = 0
    for keyword in unit.keywords:
        match = _KEYWORD_BONUS.match(keyword)
        if not match:
            continue
        kind, amount = match.group(1), match.group(2)
        applies = (kind == "Assault" and designation == "attacker") or (
            kind == "Shield" and designation == "defender"
        )
        if applies:
            bonus += int(amount) if amount else 1
    return unit.might + bonus


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


def enumerate_assignments(targets: frozenset[UnitInstance], pool: int) -> list[Assignment]:
    """All distinct valid ways to assign `pool` damage among `targets`,
    per the lethal-first rule (rule 465.2.c): a unit must receive its
    full remaining-lethal amount before a different unit can be targeted;
    the assigning player isn't required to touch every unit. Overkill
    beyond lethal isn't tracked separately (doesn't change which units
    die — see design/09-combat-resolution.md)."""
    target_list = sorted(targets, key=lambda u: u.instance_id)
    if pool <= 0 or not target_list:
        return [()]

    results: list[dict[int, int]] = []

    def recurse(remaining: list[UnitInstance], pool_left: int, assigned: dict[int, int]) -> None:
        if pool_left <= 0 or not remaining:
            results.append(dict(assigned))
            return
        for i, unit in enumerate(remaining):
            lethal_needed = max(1, unit.might - unit.damage)
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


def _apply_damage(units: frozenset[UnitInstance], assignment: Assignment) -> frozenset[UnitInstance]:
    """Marks damage per `assignment` and removes any unit whose damage
    now meets or exceeds its Might (dead — rule: Lethal Damage is
    non-zero damage >= Might)."""
    damage_by_id = dict(assignment)
    survivors = set()
    for unit in units:
        extra = damage_by_id.get(unit.instance_id, 0)
        new_damage = unit.damage + extra
        if new_damage < unit.might:
            survivors.add(dataclasses.replace(unit, damage=new_damage))
    return frozenset(survivors)


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
    moved_mover = dataclasses.replace(mover, exhausted=exhausted_after)
    attacker_units = frozenset({moved_mover})
    defender_units = destination.units

    surviving_attackers = _apply_damage(attacker_units, defender_assignment)
    surviving_defenders = _apply_damage(defender_units, attacker_assignment)

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
    return _replace_battlefield(state, new_bf)


def enumerate_combat_outcomes(state: GameState, mover: UnitInstance, from_zone: str, destination_id: str,
                               our_assignment: Assignment) -> list[GameState]:
    """All possible resulting states for a combat-triggering move, one per
    possible opponent response to `our_assignment` — the enumeration
    itself (used by both search.py's AND-node and export.py's graph BFS,
    so it lives here rather than duplicated in each). Doesn't decide
    which outcomes are acceptable, and doesn't resolve scoring
    consequences of any resulting control change — same division of
    responsibility as apply_combat.
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
    else:
        opponent_units, opponent_designation, opponent_targets = attacker_units, "attacker", defender_units

    opponent_pool = sum(unit_combat_might(u, opponent_designation) for u in opponent_units)

    outcomes = []
    for opponent_assignment in enumerate_assignments(opponent_targets, opponent_pool):
        attacker_assignment = our_assignment if we_are_attacker else opponent_assignment
        defender_assignment = opponent_assignment if we_are_attacker else our_assignment
        outcomes.append(apply_combat(
            state, mover, from_zone, destination_id, attacker_assignment, defender_assignment,
            exhausted_after=True,
        ))
    return outcomes


def _replace_battlefield(state: GameState, updated: BattlefieldState) -> GameState:
    battlefields = tuple(
        updated if bf.battlefield_id == updated.battlefield_id else bf for bf in state.battlefields
    )
    return dataclasses.replace(state, battlefields=battlefields)
