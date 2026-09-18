"""IDDFS solver. See design/05-dfs-solver.md and design/09-combat-resolution.md.

Scope note: pruning here is the depth cap plus a transposition table that
records, per state, the largest budget it has been proven unwinnable
with — failing with more actions in hand implies failing with fewer, so
one entry answers every smaller budget, which is what makes it pay across
iterative deepening.

There is still no "no path to score" dead-end heuristic. Measured
2026-09-16, search cost grows roughly 2-4x per additional unit on the
board: 1.1s at three units a side, 4.5s at four, 7.9s at five, at depth
five. Hand-authored puzzles are far smaller than that, but an arbitrary
Origins board is not, so this is the next thing to look at if the MVP
starts meeting real positions. Any such heuristic has to be ADMISSIBLE —
it may never prune a branch that could still win, or the engine starts
missing lethals, which is the one failure mode the whole coverage ledger
exists to prevent.

`legal_actions()` here composes actions.py's board-only legality
(legal_board_actions — PlayUnit/MoveUnit/ResolveCombat) with abilities.py's
registered spell candidates, since generating PlaySpell candidates needs
abilities.py and abilities.py imports from actions.py, so it can't live in
actions.py without a circular import. It can include moves apply() can't
resolve yet (e.g. a spell moving a unit onto an occupied battlefield —
spell-triggered combat isn't wired up yet, only Standard-Move-triggered
combat is, see design/09-combat-resolution.md). The search catches that
`NotImplementedError` and skips the action rather than crashing, which
correctly limits what puzzles this solver can currently solve without the
legality checks having to lie about what the rules allow.

`solve()` returns a **strategy** (dict[StateKey, Action]), not a flat
path — see design/09-combat-resolution.md's "solve()'s return type"
section for why a flat path can't represent a solution once an opponent's
adversarial choice can lead to different resulting states.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .engine import abilities, combat, conquer, gear, legends, scoring
from .engine.actions import (
    Action,
    ActivateAbility,
    EnterShowdown,
    MoveUnit,
    PlayGear,
    PlaySpell,
    PlayUnit,
    ResolveAttackTrigger,
    ResolveCombat,
    ResolveConquerTrigger,
    ResolveShowdown,
    apply_move_unit,
    apply_play_unit,
    consume_runes,
    apply_play_gear,
    find_unit,
    generate_rune_payments,
    is_legal_play_gear,
    legal_board_actions,
)
from .engine.cards import CardDef
from .engine.state import GameState, canonical_key

StateKey = tuple
Strategy = dict[StateKey, Action]


def _board_actions_with_showdown_entries(state: GameState, cards: dict[str, CardDef]) -> list[Action]:
    """Board actions, with combat-triggering moves rewritten to
    EnterShowdown wherever stopping mid-combat would actually offer a
    choice.

    A showdown whose only legal action is "resolve damage" is not a
    decision, so folding it into the atomic ResolveCombat keeps solutions
    the same length they were before showdowns existed. The window is
    only materialised when an [Action]/[Reaction] play is genuinely
    available inside it — which is checked by entering and looking.

    A mover registered in abilities.ATTACK_TRIGGERS ALWAYS forces the
    showdown, regardless of what's playable: the atomic `atomic` list here
    was built by legal_board_actions against the PRE-trigger defender
    list, which Rule Answer 1 (coverage.py's ATTACK_TRIGGERS section)
    makes unsafe to offer at all once the trigger could still kill one of
    those defenders before the Combat Damage Step. There is no "decline
    the trigger" form to fall back to either — every registered trigger is
    mandatory, so forcing the showdown IS withholding the untriggered
    path, the same way MANDATORY_PLAY_TRIGGERS withholds a plain PlayUnit.
    """
    result: list[Action] = []
    combat_groups: dict[tuple[int, str, str], list[ResolveCombat]] = {}
    for action in legal_board_actions(state, cards):
        if isinstance(action, ResolveCombat):
            combat_groups.setdefault(
                (action.instance_id, action.from_zone, action.to_zone), []).append(action)
        else:
            result.append(action)

    for (instance_id, from_zone, to_zone), atomic in combat_groups.items():
        mover = find_unit(state, instance_id, from_zone)
        has_trigger = mover.card_id in abilities.ATTACK_TRIGGERS
        entered = combat.open_showdown(state, mover, from_zone, to_zone)
        if has_trigger or _playable_spells(entered, cards, ("Action", "Reaction")):
            result.append(EnterShowdown(instance_id=instance_id, from_zone=from_zone, to_zone=to_zone))
        else:
            result.extend(atomic)
    return result


def _playable_spells(state: GameState, cards: dict[str, CardDef],
                      speeds: tuple[str, ...]) -> list[PlaySpell]:
    """Every legal PlaySpell whose card speed is in `speeds`."""
    player = state.players[state.turn_player]
    found: list[PlaySpell] = []
    for card_id in sorted(set(player.hand)):
        card = cards.get(card_id)
        if card is None or card.speed not in speeds:
            continue
        entry = abilities.SPELL_EFFECTS.get(card_id)
        if entry is None:
            continue
        _, _, generate_candidates = entry
        for params in generate_candidates(state):
            # Payments are generated per-params, not once per card: the
            # [Deflect] tax depends on what this particular casting chooses.
            tax = abilities.deflect_tax_for(state, card_id, params, state.turn_player)
            for payment in generate_rune_payments(player.runes, card.energy_cost,
                                                   card.power_cost, card.power_domain,
                                                   rainbow_cost=tax):
                action = PlaySpell(card_id=card_id, params=params, rune_payment=payment)
                if abilities.is_legal_play_spell(state, action, card):
                    found.append(action)
    return found


def _pending_attack_trigger_actions(state: GameState) -> list[Action]:
    """The ONLY legal actions while ShowdownState.attack_trigger_resolved
    is False — one ResolveAttackTrigger per candidate the registered
    trigger offers. Nothing else (not even ResolveShowdown) is legal yet;
    see abilities.py's ATTACK_TRIGGERS module comment for why the trigger
    must fire before any damage-assignment option can even be computed."""
    bf = next(b for b in state.battlefields if b.battlefield_id == state.showdown.battlefield_id)
    attacker = next(u for u in bf.units if u.controller == state.showdown.attacker_controller)
    _, _, generate_candidates = abilities.ATTACK_TRIGGERS[attacker.card_id]
    return [ResolveAttackTrigger(instance_id=attacker.instance_id, trigger_params=params)
            for params in generate_candidates(state, attacker.instance_id)]


def _showdown_actions(state: GameState, cards: dict[str, CardDef]) -> list[Action]:
    """The action space while a showdown is open. Standard Moves are gone
    entirely — a unit can neither join nor leave a showdown by moving,
    only by being moved by a card — and so is anything Slow, which is
    every unit and (today) every registered ability. What's left is
    [Action]/[Reaction] spells, plus resolving the damage step — UNLESS a
    mandatory attack trigger is still pending, in which case it alone is
    offered (see _pending_attack_trigger_actions).
    """
    if not state.showdown.attack_trigger_resolved:
        return _pending_attack_trigger_actions(state)
    result: list[Action] = list(_playable_spells(state, cards, ("Action", "Reaction")))
    for assignment in combat.showdown_assignment_options(state, state.turn_player):
        result.append(ResolveShowdown(our_assignment=assignment))
    return result


def legal_actions(state: GameState, cards: dict[str, CardDef]) -> list[Action]:
    # A pending choice-bearing conquer trigger (engine/conquer.py) gates
    # everything else, same shape as an open showdown's pending attack
    # trigger — checked first since it can coexist with neither (a
    # showdown's own control change, if any, resolves after
    # combat.resolve_showdown has already cleared state.showdown).
    if state.pending_conquer_choice is not None:
        return [ResolveConquerTrigger(params=params)
                for params in conquer.pending_choice_candidates(state)]

    if state.showdown is not None:
        return _showdown_actions(state, cards)

    result = _board_actions_with_showdown_entries(state, cards)
    player = state.players[state.turn_player]
    for card_id in sorted(set(player.hand)):
        card = cards.get(card_id)
        if card is None:
            continue
        entry = abilities.SPELL_EFFECTS.get(card_id)
        if entry is None:
            continue
        _, _, generate_candidates = entry
        for params in generate_candidates(state):
            tax = abilities.deflect_tax_for(state, card_id, params, state.turn_player)
            for payment in generate_rune_payments(player.runes, card.energy_cost,
                                                   card.power_cost, card.power_domain,
                                                   rainbow_cost=tax):
                action = PlaySpell(card_id=card_id, params=params, rune_payment=payment)
                if abilities.is_legal_play_spell(state, action, card):
                    result.append(action)

    # Spell-kill reactions ("when you kill a unit with a spell") — offered
    # on top of whichever base PlaySpell actions were just generated, for
    # any of them that would actually kill a unit (abilities.
    # spell_kill_reaction_candidates does the diff-based check). Guarded
    # here, before touching `result` at all: this loop runs on every node
    # of every search, so it must cost nothing when no registered watcher
    # is even in trash (the overwhelmingly common case).
    if any(c in abilities.SPELL_KILL_REACTION_COST for c in player.trash):
        for base_action in [a for a in result if isinstance(a, PlaySpell)]:
            base_card = cards[base_action.card_id]
            for reaction_params in abilities.spell_kill_reaction_candidates(state, base_action, base_card):
                reacted = dataclasses.replace(base_action, reaction_params=reaction_params)
                if abilities.is_legal_spell_kill_reaction(state, reacted, base_card):
                    result.append(reacted)

    # PlayGear: Gear has no target and no placement choice, so the only
    # variable is how its cost is paid (engine/gear.py).
    for card_id in sorted(set(player.hand)):
        card = cards.get(card_id)
        if card is None or card.card_type != "Gear":
            continue
        for payment in generate_rune_payments(player.runes, card.energy_cost,
                                               card.power_cost, card.power_domain):
            action = PlayGear(card_id=card_id, rune_payment=payment)
            if is_legal_play_gear(state, action, card):
                result.append(action)

    # PlayGear "when you play this" trigger candidates — same shape as the
    # PlayUnit trigger loop below, minus the [Deflect] tax machinery (no
    # registered Gear trigger targets an enemy unit).
    for base_action in [a for a in result if isinstance(a, PlayGear)]:
        entry = abilities.GEAR_PLAY_TRIGGERS.get(base_action.card_id)
        if entry is None:
            continue
        card = cards[base_action.card_id]
        _, _, generate_trigger_candidates = entry
        if base_action.card_id in abilities.MANDATORY_GEAR_TRIGGERS:
            result.remove(base_action)
        for trigger_params in generate_trigger_candidates(state, base_action, card):
            triggered = dataclasses.replace(base_action, trigger_params=trigger_params)
            if abilities.is_legal_gear_play_trigger(state, triggered, card):
                result.append(triggered)

    # Gear abilities: same ActivateAbility action as a unit's, sourced from
    # the player's gear rather than a body on the board. Costs come from
    # gear.ability_cost, since several charge runes on top of the Exhaust.
    for gear_piece in sorted(player.gear, key=lambda g: g.instance_id):
        entry = gear.GEAR_ABILITIES.get(gear_piece.card_id)
        if entry is None:
            continue
        _, _, generate_candidates = entry
        energy_cost, power_cost, power_domain = gear.ability_cost(gear_piece.card_id)
        payments = (generate_rune_payments(player.runes, energy_cost, power_cost, power_domain)
                    if (energy_cost or power_cost) else [None])
        for payment in payments:
            for params in generate_candidates(state):
                action = ActivateAbility(source_id=gear_piece.instance_id,
                                          ability_id=gear_piece.card_id,
                                          params=params, rune_payment=payment)
                if gear.is_legal_gear_ability(state, action):
                    result.append(action)

    # ActivateAbility candidates: one registry per unit currently on the
    # board (not hand), keyed by card_id — same registry-lookup pattern as
    # spells, but scanning units instead of cards in hand.
    all_units = list(player.base_units) + [u for bf in state.battlefields for u in bf.units if u.controller == state.turn_player]
    for unit in sorted(all_units, key=lambda u: u.instance_id):
        entry = abilities.ABILITY_EFFECTS.get(unit.card_id)
        if entry is None:
            continue
        _, _, generate_candidates = entry
        for params in generate_candidates(state):
            # A unit ability prints no rune cost today, but [Deflect] can
            # still charge one for choosing its target — so the payment is
            # None only when nothing is owed.
            tax = abilities.deflect_tax_for(state, unit.card_id, params, state.turn_player)
            payments = generate_rune_payments(player.runes, 0, 0, None, rainbow_cost=tax) if tax else [None]
            for payment in payments:
                action = ActivateAbility(source_id=unit.instance_id, ability_id=unit.card_id,
                                          params=params, rune_payment=payment)
                if abilities.is_legal_activate_ability(state, action):
                    result.append(action)

    # Legend ability candidates: same ActivateAbility action, but sourced
    # from the player's Legend zone rather than a unit on the board, so
    # source_id is the LEGEND_SOURCE_ID sentinel and the rune payment is
    # real (unlike Caitlyn's exhaust-only ability, which pays None).
    if player.legend is not None and legends.is_legend_ability(player.legend.card_id):
        ability_id = player.legend.card_id
        energy_cost, power_cost, power_domain = legends.ABILITY_COSTS[ability_id]
        _, _, generate_candidates = legends.LEGEND_ABILITIES[ability_id]
        payments = (generate_rune_payments(player.runes, energy_cost, power_cost, power_domain)
                    if energy_cost or power_cost else [None])
        for payment in payments:
            for params in generate_candidates(state):
                action = ActivateAbility(source_id=legends.LEGEND_SOURCE_ID, ability_id=ability_id,
                                          params=params, rune_payment=payment)
                if legends.is_legal_legend_ability(state, action):
                    result.append(action)

    # PlayUnit "when you play me" trigger candidates: legal_board_actions
    # already generated the plain (trigger_params=()) form for every
    # affordable PlayUnit — this adds the "use the trigger" variants on
    # top, one per registered card's own candidate generator. For a
    # MANDATORY trigger (no "you may" — Faithful Manufactor, Vanguard
    # Captain), the plain form is removed rather than kept alongside the
    # triggered one: "play it WITHOUT the effect" was never actually a
    # legal choice.
    for base_action in [a for a in result if isinstance(a, PlayUnit)]:
        entry = abilities.UNIT_PLAY_TRIGGERS.get(base_action.card_id)
        if entry is None:
            continue
        card = cards[base_action.card_id]
        _, _, generate_trigger_candidates = entry
        if base_action.card_id in abilities.MANDATORY_PLAY_TRIGGERS:
            result.remove(base_action)
        for trigger_params in generate_trigger_candidates(state, base_action, card):
            triggered = dataclasses.replace(base_action, trigger_params=trigger_params)
            # A trigger that CHOOSES an enemy unit owes [Deflect]'s tax,
            # paid out of what's left after the card's own cost.
            tax = abilities.trigger_deflect_tax(state, triggered, card)
            if tax:
                left = consume_runes(state.players[state.turn_player].runes,
                                      triggered.rune_payment)
                payments = generate_rune_payments(left, 0, 0, None, rainbow_cost=tax)
                if not payments:
                    continue  # tax unaffordable — this target is out of reach
                triggered = dataclasses.replace(triggered, trigger_payment=payments[0])
            if abilities.is_legal_unit_play_trigger(state, triggered, card):
                result.append(triggered)
    return result


def apply(state: GameState, action: Action, cards: dict[str, CardDef]) -> GameState:
    """Board mechanics + scoring consequences for one action — composes
    actions.py (board state) with scoring.py (points); see both modules'
    docstrings for why the split exists.

    `ResolveCombat`, a `PlayUnit` with non-empty `trigger_params`, and
    `PlaySpell` all deliberately raise: none can produce a single
    resulting state on its own once its effect can cause combat (the
    opponent's damage-assignment response is still pending) — use
    `solve()`, or `combat.apply_combat`/`abilities.
    resolve_unit_play_trigger_outcomes`/`abilities.resolve_spell_outcomes`
    directly with a chosen opponent assignment, instead. Every spell
    routes through the same list-returning path regardless of whether
    IT specifically can branch, for the same reason `PlayUnit` triggers
    do: consistency beats special-casing the (today) 2-of-3 spells that
    happen to always return exactly one outcome.
    """
    if isinstance(action, PlayUnit):
        if action.trigger_params:
            raise NotImplementedError(
                "apply: PlayUnit with trigger_params can have multiple outcomes — see search.solve()"
            )
        new_state = apply_play_unit(state, action, cards[action.card_id])
        if action.target_zone != "base":
            new_state = scoring.resolve_control_change(state, new_state, action.target_zone)
        return new_state

    if isinstance(action, MoveUnit):
        new_state = apply_move_unit(state, action)
        if action.to_zone != "base":
            new_state = scoring.resolve_control_change(state, new_state, action.to_zone)
        return abilities.apply_move_triggers(new_state, action.instance_id)

    if isinstance(action, EnterShowdown):
        # No damage yet, so no deaths and no control change - nothing for
        # scoring to resolve until the showdown does.
        mover = find_unit(state, action.instance_id, action.from_zone)
        has_trigger = mover.card_id in abilities.ATTACK_TRIGGERS
        new_state = combat.open_showdown(state, mover, action.from_zone, action.to_zone,
                                          has_pending_trigger=has_trigger)
        return abilities.apply_move_triggers(new_state, action.instance_id)

    if isinstance(action, ResolveAttackTrigger):
        return abilities.apply_attack_trigger(state, action)

    if isinstance(action, ResolveConquerTrigger):
        # Deterministic given the chosen params (a single candidate from
        # conquer.pending_choice_candidates), so this is a plain
        # single-state apply — the OR over which candidate to choose is
        # handled by _dfs's outer loop over legal_actions(), the same way
        # every other choice in this codebase is (see conquer.py's module
        # docstring for why this shape was chosen).
        return conquer.apply_pending_choice(state, action.params)

    if isinstance(action, ResolveShowdown):
        raise NotImplementedError(
            "apply: ResolveShowdown has an adversarial opponent assignment — see search.solve()"
        )

    if isinstance(action, PlaySpell):
        raise NotImplementedError(
            "apply: PlaySpell can have multiple outcomes — see search.solve() or "
            "abilities.resolve_spell_outcomes()"
        )

    if isinstance(action, PlayGear):
        if action.trigger_params:
            raise NotImplementedError(
                "apply: PlayGear with trigger_params can have multiple outcomes — see search.solve()"
            )
        # Gear has no target and enters nobody's battlefield, so playing it
        # can't change control or trigger combat — no scoring to resolve.
        return apply_play_gear(state, action, cards[action.card_id])

    if isinstance(action, ActivateAbility):
        if gear.is_legal_gear_ability(state, action):
            return gear.apply_gear_ability(state, action)
        if legends.is_legend_ability(action.ability_id):
            outcomes = legends.resolve_legend_ability_outcomes(state, action)
            if len(outcomes) != 1:
                raise NotImplementedError(
                    "apply: this Legend ability has multiple outcomes — see search.solve()"
                )
            return outcomes[0]
        return abilities.apply_ability(state, action)

    raise NotImplementedError(
        f"apply: {type(action).__name__} not supported yet (see design/03-action-space.md / "
        f"design/09-combat-resolution.md — ResolveCombat has no single-state apply(), see search.solve())"
    )


def solve(root: GameState, cards: dict[str, CardDef], max_depth: int = 12) -> Optional[Strategy]:
    """Iterative-deepening DFS: try depth 1, then 2, ... up to max_depth,
    returning the first (shallowest-found) winning strategy, or None if
    no win exists within max_depth. A strategy is a map from every state
    the player might find themselves in (including states reached via an
    opponent's forced combat-assignment branch) to the one action to take
    from there.
    """
    transposition_table: dict[tuple, int] = {}
    for depth_limit in range(1, max_depth + 1):
        result = _dfs(root, depth_limit, cards, transposition_table)
        if result is not None:
            return result
    return None


def _dfs(state: GameState, remaining: int, cards: dict[str, CardDef],
         ttable: dict[tuple, int]) -> Optional[Strategy]:
    if scoring.is_winning(state):
        return {}

    if remaining == 0:
        return None

    key = canonical_key(state)
    # The table records, per state, the LARGEST action budget it has been
    # proven unwinnable with. Failing with more actions in hand implies
    # failing with fewer, so that one entry answers every smaller budget
    # too — which is what makes it useful across iterative deepening,
    # where the same states are revisited over and over with different
    # budgets. Keying on (state, remaining) instead, as this did, meant a
    # state proven dead at 5 was searched again from scratch at 4, 3, 2.
    if ttable.get(key, -1) >= remaining:
        return None

    for action in legal_actions(state, cards):
        if isinstance(action, ResolveCombat):
            result = _resolve_combat_search(state, action, remaining, cards, ttable)
        elif isinstance(action, ResolveShowdown):
            result = _and_or_search(state, action, resolve_showdown_outcomes(state, action),
                                     remaining, cards, ttable)
        elif isinstance(action, PlayUnit) and action.trigger_params:
            outcomes = abilities.resolve_unit_play_trigger_outcomes(state, action, cards[action.card_id])
            result = _and_or_search(state, action, outcomes, remaining, cards, ttable)
        elif isinstance(action, PlayGear) and action.trigger_params:
            outcomes = abilities.resolve_gear_play_trigger_outcomes(state, action, cards[action.card_id])
            result = _and_or_search(state, action, outcomes, remaining, cards, ttable)
        elif isinstance(action, PlaySpell):
            try:
                resolver = (abilities.resolve_spell_outcomes_with_reaction if action.reaction_params
                           else abilities.resolve_spell_outcomes)
                outcomes = resolver(state, action, cards[action.card_id])
            except NotImplementedError:
                # e.g. Ride The Wind moving a friendly unit onto an enemy-
                # occupied battlefield - that spell's effect doesn't handle
                # combat (only Charm's does), same documented gap
                # legal_actions()'s docstring already calls out.
                result = None
            else:
                result = _and_or_search(state, action, outcomes, remaining, cards, ttable)
        else:
            try:
                child = apply(state, action, cards)
            except NotImplementedError:
                result = None
            else:
                sub = _dfs(child, remaining - 1, cards, ttable)
                result = None if sub is None else {**sub, key: action}
        if result is not None:
            return result

    ttable[key] = max(ttable.get(key, -1), remaining)
    return None


def _resolve_combat_search(state: GameState, action: ResolveCombat, remaining: int,
                            cards: dict[str, CardDef], ttable: dict[tuple, int]) -> Optional[Strategy]:
    """Thin wrapper: computes ResolveCombat's outcomes, then defers to the
    shared _and_or_search."""
    outcomes = resolve_combat_outcomes(state, action)
    return _and_or_search(state, action, outcomes, remaining, cards, ttable)


def resolve_combat_outcomes(state: GameState, action: ResolveCombat) -> list[GameState]:
    mover = find_unit(state, action.instance_id, action.from_zone)
    outcomes = combat.enumerate_combat_outcomes(state, mover, action.from_zone, action.to_zone,
                                                 action.our_assignment)
    outcomes = [scoring.resolve_control_change(state, o, action.to_zone) for o in outcomes]
    return [abilities.apply_move_triggers(o, action.instance_id) for o in outcomes]


def resolve_showdown_outcomes(state: GameState, action: ResolveShowdown) -> list[GameState]:
    """Damage step for the open showdown, one outcome per opponent
    assignment — the same AND-node shape as ResolveCombat, just reading
    its participants off the live board instead of a remembered mover."""
    assert state.showdown is not None
    battlefield_id = state.showdown.battlefield_id
    opponent = 1 - state.turn_player
    we_attack = state.showdown.attacker_controller == state.turn_player

    outcomes = []
    for theirs in combat.showdown_assignment_options(state, opponent):
        attacker_assignment = action.our_assignment if we_attack else theirs
        defender_assignment = theirs if we_attack else action.our_assignment
        resolved = combat.resolve_showdown(state, attacker_assignment, defender_assignment)
        outcomes.append(scoring.resolve_control_change(state, resolved, battlefield_id))
    return outcomes


def count_winning_strategies(root: GameState, cards: dict[str, CardDef], max_depth: int = 12) -> int:
    """How many DISTINCT complete winning strategies exist from `root`
    within the shortest possible depth — the generation pipeline's
    solution-count filter (design/10-generation-pipeline.md). This counts
    full lines to lethal, not just root's first move: a puzzle with one
    forced opener that then branches into several correct follow-ups is
    still "easy" in the sense this filter cares about, so branching at any
    point in the line counts, not just at the root.

    At an adversarial (AND) node, our own play must still work against
    EVERY opponent response, so a "strategy" through that node fixes one
    continuation per response — the count contributed is the PRODUCT of
    the continuation counts across responses (only valid, i.e. counted at
    all, if every response has at least one continuation). This can grow
    quickly if a puzzle has heavy combat branching, but every puzzle in
    scope so far is small enough for this not to matter.

    A count of 0 means `root` isn't solvable within `max_depth` (or is
    already winning, a degenerate case that shouldn't occur for a sampled
    puzzle). Recomputes the shortest depth the same way solve() does
    internally (len(solve(...)) isn't the right proxy — it counts every
    state across the whole strategy map, not the ply-depth of root's own
    shortest path).
    """
    if scoring.is_winning(root):
        return 0

    d_star = None
    for depth_limit in range(1, max_depth + 1):
        if _dfs(root, depth_limit, cards, {}) is not None:
            d_star = depth_limit
            break
    if d_star is None:
        return 0

    memo: dict[tuple, int] = {}
    return _count_solutions(root, d_star, cards, memo)


def _count_solutions(state: GameState, remaining: int, cards: dict[str, CardDef],
                      memo: dict[tuple, int]) -> int:
    if scoring.is_winning(state):
        return 1
    if remaining == 0:
        return 0

    key = (canonical_key(state), remaining)
    if key in memo:
        return memo[key]

    total = 0
    for action in legal_actions(state, cards):
        if isinstance(action, ResolveCombat):
            outcomes = resolve_combat_outcomes(state, action)
        elif isinstance(action, ResolveShowdown):
            outcomes = resolve_showdown_outcomes(state, action)
        elif isinstance(action, PlayUnit) and action.trigger_params:
            outcomes = abilities.resolve_unit_play_trigger_outcomes(state, action, cards[action.card_id])
        elif isinstance(action, PlayGear) and action.trigger_params:
            outcomes = abilities.resolve_gear_play_trigger_outcomes(state, action, cards[action.card_id])
        elif isinstance(action, PlaySpell):
            try:
                resolver = (abilities.resolve_spell_outcomes_with_reaction if action.reaction_params
                           else abilities.resolve_spell_outcomes)
                outcomes = resolver(state, action, cards[action.card_id])
            except NotImplementedError:
                continue
        else:
            try:
                outcomes = [apply(state, action, cards)]
            except NotImplementedError:
                continue

        counts = [_count_solutions(o, remaining - 1, cards, memo) for o in outcomes]
        if all(c > 0 for c in counts):
            product = 1
            for c in counts:
                product *= c
            total += product

    memo[key] = total
    return total


def _and_or_search(state: GameState, action: Action, outcomes: list[GameState], remaining: int,
                    cards: dict[str, CardDef], ttable: dict[tuple, int]) -> Optional[Strategy]:
    """The AND-node: `action` already bakes in our own choice (a specific
    damage assignment, tried in `legal_actions`'s outer OR-loop via
    `_dfs`); `outcomes` is every possible way the adversary's response can
    resolve it. For `action` to be validated, EVERY outcome must still
    lead to a win — see design/09-combat-resolution.md. Shared by
    ResolveCombat and any "when played" trigger whose effect can cause
    combat (abilities.UNIT_PLAY_TRIGGERS), since both reduce to the same
    shape once their outcomes are computed.
    """
    key = canonical_key(state)
    merged: Strategy = {}
    for child in outcomes:
        sub = _dfs(child, remaining - 1, cards, ttable)
        if sub is None:
            return None  # this adversary response defeats us — action doesn't survive
        merged.update(sub)

    merged[key] = action
    return merged
