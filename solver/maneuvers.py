"""Maneuver fingerprinting: reduces a puzzle's winning line to a
per-step token sequence — lane, instance_id, and exact Might numbers
stripped out — so two candidates that are the same trick with different
stats/lanes collapse to the same signature. Works directly off an
already-exported puzzle dict (export.export_puzzle's return value, or a
puzzle-*.json already on disk), not live engine state — the `card_id`/
`keywords` fields on each rendered action (export.py's render_action)
already carry what's needed.

A MoveUnit/ResolveCombat step's token is its mover's raw `card_id` ONLY
if that card has a registered mechanic (a spell/ability/trigger, or a
move-count trigger); a plain vanilla mover (no registered mechanic —
Assault/Shield/Ganking/Tank included, since those are just combat-math
modifiers, not a distinct trick) is instead bucketed by its keyword set
(`vanilla:Tank`, `vanilla:` for a bare stat-stick, etc.). Without this,
two candidates built from the same trick but drawing a different filler
stat-stick (Sneaky Deckhand vs Faithful Manufactor as "the spare unit
that walks into the cleared lane") register as different signatures and
dedup misses them — confirmed happening in practice (design/10-
generation-pipeline.md's "known gap" note, now fixed).

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

from .engine import abilities

Signature = tuple[tuple[str, str], ...]

REGISTRY_PATH = Path(__file__).parent.parent / "puzzles" / "maneuvers.json"

_MOVE_ACTION_TYPES = {"MoveUnit", "ResolveCombat"}


def _registered_mechanic_card_ids() -> set[str]:
    return (set(abilities.SPELL_EFFECTS) | set(abilities.ABILITY_EFFECTS)
            | set(abilities.UNIT_PLAY_TRIGGERS) | set(abilities.MOVE_COUNT_TRIGGERS))


def _mover_token(action: dict) -> str:
    card_id = action["card_id"]
    if card_id in _registered_mechanic_card_ids():
        return card_id
    return "vanilla:" + ",".join(action["keywords"])


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
        token = _mover_token(action) if action["type"] in _MOVE_ACTION_TYPES else action["card_id"]
        steps.append((action["type"], token))
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
