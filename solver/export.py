"""Puzzle exporter: walks a verified position's reachable state graph into
the JSON DAG the web layer consumes. See design/06-export-schema.md.

Scope note on the depth cap: `depth_cap = len(solution) + margin` bounds
how far the graph-building BFS explores (per the original 6-week plan:
"cap depth at solution length + 2-3" — graph size doubles as a puzzle
quality filter). A state at the cap that still has legal actions is left
with no recorded outgoing edges and is deliberately NOT marked terminal
(that would mislabel a merely-truncated state as a genuine dead end) — a
well-scoped puzzle should hit real wins/dead-ends within the cap; hitting
the cap on active branches is a signal the puzzle is too loose, not
something this module should paper over.
"""

from __future__ import annotations

import hashlib

from .engine import scoring
from .engine.actions import Action, MoveUnit, PlayGear, PlaySpell, PlayUnit, legal_actions
from .engine.cards import CardDef
from .engine.state import BattlefieldState, GameState, PlayerState, UnitInstance, canonical_key
from .search import apply, solve

SCHEMA_VERSION = 1


def state_hash(state: GameState) -> str:
    """Stable, cross-process-safe string id for a state, for use as a JSON
    object key. Python's built-in hash() is randomized per process for
    str/frozenset contents, so it's not safe to persist across runs —
    hashlib on canonical_key's repr is."""
    canonical_repr = repr(canonical_key(state)).encode("utf-8")
    return hashlib.sha256(canonical_repr).hexdigest()[:16]


def render_unit(unit: UnitInstance) -> dict:
    return {
        "card_id": unit.card_id,
        "instance_id": unit.instance_id,
        "controller": unit.controller,
        "might": unit.might,
        "keywords": sorted(unit.keywords),
        "exhausted": unit.exhausted,
        "damage": unit.damage,
        "is_token": unit.is_token,
    }


def render_player(player: PlayerState) -> dict:
    return {
        "base_units": [render_unit(u) for u in sorted(player.base_units, key=lambda u: u.instance_id)],
        "hand": sorted(player.hand),
        "runes": sorted(player.runes.available),
        "score": player.score,
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
    }


def render_action(action: Action, action_id: str) -> dict:
    if isinstance(action, PlayUnit):
        label = f"Play {action.card_id} to {action.target_zone}"
    elif isinstance(action, MoveUnit):
        label = f"Move unit {action.instance_id} from {action.from_zone} to {action.to_zone}"
    elif isinstance(action, PlaySpell):
        label = f"Play {action.card_id}"
    elif isinstance(action, PlayGear):
        label = f"Play {action.card_id} on unit {action.target_unit}"
    else:
        label = type(action).__name__
    return {"id": action_id, "type": type(action).__name__, "label": label}


def export_puzzle(puzzle_id: str, root: GameState, cards: dict[str, CardDef],
                   max_solver_depth: int = 12, depth_cap_margin: int = 2) -> dict:
    """Verify `root` has a win (per solve()), then BFS-enumerate its
    reachable-state graph up to `len(solution) + depth_cap_margin` and
    return the JSON-serializable DAG described in design/06-export-schema.md.
    """
    solution = solve(root, cards, max_depth=max_solver_depth)
    if solution is None:
        raise ValueError(
            f"puzzle {puzzle_id!r}: no winning line found within depth {max_solver_depth} — "
            "export.py only exports verified positions (design/06-export-schema.md)"
        )

    depth_cap = len(solution) + depth_cap_margin

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
                child = apply(state, action, cards)
            except NotImplementedError:
                continue
            any_child = True
            child_hash = state_hash(child)
            action_counter += 1
            action_id = f"a{action_counter}"
            action_lookup[(h, action)] = action_id
            state_edges.append({"action": render_action(action, action_id), "to": child_hash})
            if child_hash not in visited:
                visited.add(child_hash)
                nodes[child_hash] = render_state(child)
                frontier.append((child, depth + 1))

        if state_edges:
            edges[h] = state_edges
        if not any_child:
            terminal[h] = "dead_end"

    # Walk the solver's specific winning path to recover its action_ids —
    # the BFS above may have recorded the same (state, action) pair once
    # even though the winning path revisits shared prefixes.
    solution_ids = []
    current = root
    for action in solution:
        h = state_hash(current)
        solution_ids.append(action_lookup[(h, action)])
        current = apply(current, action, cards)

    return {
        "schema_version": SCHEMA_VERSION,
        "puzzle_id": puzzle_id,
        "root": root_hash,
        "solution": solution_ids,
        "nodes": nodes,
        "edges": edges,
        "terminal": terminal,
    }
