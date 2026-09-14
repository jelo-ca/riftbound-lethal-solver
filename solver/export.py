"""Puzzle exporter: walks a verified position's reachable state graph into
the JSON DAG the web layer consumes. See design/06-export-schema.md.

Scope note on the depth cap: `depth_cap = len(solution) + margin` bounds
how far the graph-building BFS explores (per the original 6-week plan:
"cap depth at solution length + 2-3" — graph size doubles as a puzzle
quality filter). `len(solution)` is the strategy map's size (number of
distinct states covered), a safe proxy for "how deep" even when the
strategy branches (adversarial combat) rather than a single path. A state
at the cap that still has legal actions is left with no recorded outgoing
edges and is deliberately NOT marked terminal (that would mislabel a
merely-truncated state as a genuine dead end) — a well-scoped puzzle
should hit real wins/dead-ends within the cap; hitting the cap on active
branches is a signal the puzzle is too loose, not something this module
should paper over.
"""

from __future__ import annotations

import hashlib

from .engine import abilities, combat, scoring
from .engine.actions import (
    ActivateAbility,
    Action,
    EnterShowdown,
    MoveUnit,
    PlayGear,
    PlaySpell,
    PlayUnit,
    ResolveCombat,
    ResolveShowdown,
    find_unit,
)
from .engine.cards import CardDef
from .engine.state import BattlefieldState, GameState, PlayerState, UnitInstance, canonical_key
from .search import apply, legal_actions, resolve_combat_outcomes, resolve_showdown_outcomes, solve

SCHEMA_VERSION = 2


def _hash_canonical_key(key: tuple) -> str:
    return hashlib.sha256(repr(key).encode("utf-8")).hexdigest()[:16]


def state_hash(state: GameState) -> str:
    """Stable, cross-process-safe string id for a state, for use as a JSON
    object key. Python's built-in hash() is randomized per process for
    str/frozenset contents, so it's not safe to persist across runs —
    hashlib on canonical_key's repr is."""
    return _hash_canonical_key(canonical_key(state))


def render_unit(unit: UnitInstance) -> dict:
    """Every field canonical_key considers significant has to appear here,
    or the export loses information the engine acts on: two states with
    different hashes would render identically and a consumer replaying
    the puzzle couldn't tell them apart. That was live for
    `moved_this_turn` — puzzle 3's whole mechanic is Yasuo's move count,
    and it wasn't in the file at all, leaving 8 pairs of
    indistinguishable states in that one puzzle."""
    return {
        "card_id": unit.card_id,
        "instance_id": unit.instance_id,
        "controller": unit.controller,
        "might": unit.might,
        "keywords": sorted(unit.keywords),
        "exhausted": unit.exhausted,
        "damage": unit.damage,
        "is_token": unit.is_token,
        "moved_this_turn": unit.moved_this_turn,
        "might_bonus": unit.might_bonus,
    }


def render_player(player: PlayerState) -> dict:
    return {
        "base_units": [render_unit(u) for u in sorted(player.base_units, key=lambda u: u.instance_id)],
        "hand": sorted(player.hand),
        "runes": sorted(player.runes.available),
        "score": player.score,
        "legend": ({"card_id": player.legend.card_id, "exhausted": player.legend.exhausted}
                   if player.legend else None),
    }


def render_battlefield(bf: BattlefieldState) -> dict:
    return {
        "battlefield_id": bf.battlefield_id,
        "controller": bf.controller,
        "units": [render_unit(u) for u in sorted(bf.units, key=lambda u: u.instance_id)],
        "effect_id": bf.effect_id,
    }


def render_state(state: GameState) -> dict:
    """JSON-serializable projection of a GameState. v0: direct field
    conversion, no UI-friendly renaming — that's a Week 4 site concern."""
    return {
        "turn_player": state.turn_player,
        "players": [render_player(p) for p in state.players],
        "battlefields": [render_battlefield(b) for b in state.battlefields],
        "scored_this_turn": sorted(state.scored_this_turn),
        "cards_played_this_turn": state.cards_played_this_turn,
        "showdown": ({"battlefield_id": state.showdown.battlefield_id,
                      "attacker_controller": state.showdown.attacker_controller}
                     if state.showdown else None),
    }


def render_action(state: GameState, action: Action, action_id: str) -> dict:
    """`card_id` is the card most responsible for this action's identity —
    the mover's card for a MoveUnit/ResolveCombat, the played/activated
    card otherwise — independent of lane/instance_id/exact Might, so two
    structurally-identical actions on different boards render the same
    card_id. `keywords` (MoveUnit/ResolveCombat only) is the mover's own
    keyword set — maneuvers.py uses it to bucket interchangeable vanilla
    movers (no registered mechanic, e.g. two different plain 2-Might
    stat-sticks) by keyword-set instead of raw card_id, so a puzzle isn't
    treated as "novel" just because it drew a different filler card."""
    if isinstance(action, PlayUnit):
        label = f"Play {action.card_id} to {action.target_zone}"
        card_id, keywords = action.card_id, []
    elif isinstance(action, MoveUnit):
        label = f"Move unit {action.instance_id} from {action.from_zone} to {action.to_zone}"
        mover = find_unit(state, action.instance_id, action.from_zone)
        card_id, keywords = mover.card_id, sorted(mover.keywords)
    elif isinstance(action, ResolveCombat):
        label = f"Move unit {action.instance_id} from {action.from_zone} to {action.to_zone} (combat)"
        mover = find_unit(state, action.instance_id, action.from_zone)
        card_id, keywords = mover.card_id, sorted(mover.keywords)
    elif isinstance(action, EnterShowdown):
        label = (f"Move unit {action.instance_id} from {action.from_zone} to {action.to_zone} "
                  "(enter showdown)")
        mover = find_unit(state, action.instance_id, action.from_zone)
        card_id, keywords = mover.card_id, sorted(mover.keywords)
    elif isinstance(action, ResolveShowdown):
        label = "Resolve showdown damage"
        card_id, keywords = "", []
    elif isinstance(action, PlaySpell):
        label = f"Play {action.card_id} ({', '.join(str(p) for p in action.params)})"
        card_id, keywords = action.card_id, []
    elif isinstance(action, PlayGear):
        label = f"Play {action.card_id} on unit {action.target_unit}"
        card_id, keywords = action.card_id, []
    elif isinstance(action, ActivateAbility):
        label = f"Activate unit {action.source_id} ({', '.join(str(p) for p in action.params)})"
        card_id, keywords = action.ability_id, []
    else:
        label = type(action).__name__
        card_id, keywords = "", []
    return {"id": action_id, "type": type(action).__name__, "label": label,
            "card_id": card_id, "keywords": keywords}


def resolve_action_outcomes(state: GameState, action: Action, cards: dict[str, CardDef]) -> list[GameState]:
    """All possible resulting states for `action` — a single-element list
    for a deterministic action, multiple for a combat action with a real
    opponent choice. Raises NotImplementedError the same way apply() does
    for anything neither can handle yet."""
    if isinstance(action, ResolveCombat):
        return resolve_combat_outcomes(state, action)
    if isinstance(action, ResolveShowdown):
        return resolve_showdown_outcomes(state, action)
    if isinstance(action, PlayUnit) and action.trigger_params:
        return abilities.resolve_unit_play_trigger_outcomes(state, action, cards[action.card_id])
    if isinstance(action, PlaySpell):
        return abilities.resolve_spell_outcomes(state, action, cards[action.card_id])
    return [apply(state, action, cards)]


def export_puzzle(puzzle_id: str, root: GameState, cards: dict[str, CardDef],
                   max_solver_depth: int = 12, depth_cap_margin: int = 2) -> dict:
    """Verify `root` has a win (per solve()), then BFS-enumerate its
    reachable-state graph up to `len(strategy) + depth_cap_margin` and
    return the JSON-serializable DAG described in design/06-export-schema.md.
    """
    unseeded = scoring.unseeded_holds(root)
    if unseeded:
        raise ValueError(
            f"puzzle {puzzle_id!r}: turn player controls {sorted(unseeded)} but "
            f"scored_this_turn is {sorted(root.scored_this_turn)} — a controlled "
            "battlefield has always already scored this turn (see "
            "scoring.unseeded_holds). Seeding it is not a formality: without it "
            "the position admits a re-Conquer of ground the player never lost."
        )

    strategy = solve(root, cards, max_depth=max_solver_depth)
    if strategy is None:
        raise ValueError(
            f"puzzle {puzzle_id!r}: no winning line found within depth {max_solver_depth} — "
            "export.py only exports verified positions (design/06-export-schema.md)"
        )

    depth_cap = len(strategy) + depth_cap_margin

    nodes: dict[str, dict] = {}
    edges: dict[str, list[dict]] = {}
    terminal: dict[str, str] = {}
    action_lookup: dict[tuple[str, Action], str] = {}

    root_hash = state_hash(root)
    nodes[root_hash] = render_state(root)
    visited = {root_hash}
    frontier: list[tuple[GameState, int]] = [(root, 0)]
    action_counter = 0

    while frontier:
        state, depth = frontier.pop(0)
        h = state_hash(state)

        if scoring.is_winning(state):
            terminal[h] = "win"
            continue
        if depth >= depth_cap:
            continue  # truncated — not terminal, see module docstring

        state_edges = []
        any_child = False
        for action in legal_actions(state, cards):
            try:
                outcomes = resolve_action_outcomes(state, action, cards)
            except NotImplementedError:
                continue
            any_child = True
            action_counter += 1
            action_id = f"a{action_counter}"
            action_lookup[(h, action)] = action_id
            outcome_hashes = []
            for child in outcomes:
                child_hash = state_hash(child)
                outcome_hashes.append(child_hash)
                if child_hash not in visited:
                    visited.add(child_hash)
                    nodes[child_hash] = render_state(child)
                    frontier.append((child, depth + 1))
            state_edges.append({
                "action": render_action(state, action, action_id),
                "to": outcome_hashes,
                "adversarial": len(outcomes) > 1,
            })

        if state_edges:
            edges[h] = state_edges
        if not any_child:
            terminal[h] = "dead_end"

    # The strategy maps canonical_key(state) -> action; convert to
    # state_hash -> action_id using the same action_lookup the BFS above
    # built (the BFS's own legal_actions()/action objects are structurally
    # equal to the strategy's, so the lookup hits).
    solution = {
        _hash_canonical_key(key): action_lookup[(_hash_canonical_key(key), action)]
        for key, action in strategy.items()
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "puzzle_id": puzzle_id,
        "root": root_hash,
        "solution": solution,
        "nodes": nodes,
        "edges": edges,
        "terminal": terminal,
    }
