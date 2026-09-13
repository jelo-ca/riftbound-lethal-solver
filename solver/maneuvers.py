"""Maneuver fingerprinting: reduces a puzzle's winning line to a
(action_type, card_id) sequence per step — lane, instance_id, and exact
Might numbers stripped out — so two candidates that are the same trick
with different stats/lanes collapse to the same signature. Works
directly off an already-exported puzzle dict (export.export_puzzle's
return value, or a puzzle-*.json already on disk), not live engine
state — the `card_id` field on each rendered action (export.py's
render_action) already carries what's needed.

`puzzles/maneuvers.json` holds one entry per PROMOTED puzzle
(puzzle_id -> signature); `generate.py`'s filter rejects any freshly
generated candidate whose signature matches one already there, or one
already accepted earlier in the same batch — see design/10-generation-
pipeline.md.

Walks the strategy's "spine" only: at an adversarial branch (opponent's
combat-damage choice), arbitrarily follows the first enumerated `to`
outcome rather than every branch. That's fine for a fingerprint — the
goal is "have we already made this kind of trick," not a full proof of
structural equivalence.
"""

from __future__ import annotations

import json
from pathlib import Path

Signature = tuple[tuple[str, str], ...]

REGISTRY_PATH = Path(__file__).parent.parent / "puzzles" / "maneuvers.json"


def maneuver_signature(result: dict) -> Signature:
    """`result` is an export_puzzle()-shaped dict (schema_version 2):
    needs `root`, `solution`, `edges`."""
    solution = result["solution"]
    edges = result["edges"]
    cur = result["root"]
    seen: set[str] = set()
    steps: list[tuple[str, str]] = []
    while cur in solution and cur not in seen:
        seen.add(cur)
        action_id = solution[cur]
        edge = next(e for e in edges[cur] if e["action"]["id"] == action_id)
        action = edge["action"]
        steps.append((action["type"], action["card_id"]))
        cur = edge["to"][0]
    return tuple(steps)


def load_registry() -> dict[str, Signature]:
    if not REGISTRY_PATH.exists():
        return {}
    raw = json.loads(REGISTRY_PATH.read_text())
    return {puzzle_id: tuple(tuple(step) for step in sig) for puzzle_id, sig in raw.items()}


def save_registry(registry: dict[str, Signature]) -> None:
    ordered = {puzzle_id: list(sig) for puzzle_id, sig in sorted(registry.items())}
    REGISTRY_PATH.write_text(json.dumps(ordered, indent=2) + "\n")


def register_puzzle(puzzle_id: str, result: dict) -> Signature:
    """Computes and persists `result`'s signature under `puzzle_id` in the
    registry, overwriting any existing entry for that id. Returns the
    signature."""
    registry = load_registry()
    signature = maneuver_signature(result)
    registry[puzzle_id] = signature
    save_registry(registry)
    return signature
