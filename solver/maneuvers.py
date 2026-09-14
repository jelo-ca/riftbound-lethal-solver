"""Maneuver fingerprinting: reduces a puzzle's winning line to a
per-step token sequence — lane, instance_id, and exact Might numbers
stripped out — so two candidates that are the same trick with different
stats/lanes collapse to the same signature. Works directly off an
already-exported puzzle dict (export.export_puzzle's return value, or a
puzzle-*.json already on disk), not live engine state — the `card_id`/
`keywords` fields on each rendered action (export.py's render_action)
already carry what's needed.

A move step's token is its mover's raw `card_id` ONLY if that card has a
registered mechanic (a spell/ability/trigger, or a move-count trigger);
a plain vanilla mover (no registered mechanic — Assault/Shield/Ganking/
Tank included, since those are just combat-math modifiers, not a
distinct trick) is instead bucketed by keywords (`vanilla:Tank`,
`vanilla:` for a bare stat-stick, etc.). Without this, two candidates
built from the same trick but drawing a different filler stat-stick
(Sneaky Deckhand vs Faithful Manufactor as "the spare unit that walks
into the cleared lane") register as different signatures and dedup
misses them — confirmed happening in practice (design/10-generation-
pipeline.md's "known gap" note, now fixed).

Which keywords go into that bucket depends on the step: a fighting step
keeps all of them, a plain MoveUnit keeps only the ones that change
where it may go (see `_MOVEMENT_KEYWORDS`).

Two normalizations keep equivalent lines tokenizing alike. An
EnterShowdown/ResolveShowdown pair with nothing between them collapses
to the single ResolveCombat it's equivalent to, and containment matches
an order-preserving subsequence rather than a contiguous run, so a known
trick with a step spliced into its middle is still recognised. Both
existed as live holes: each let a line that had already been declined
come back through a later batch looking novel.

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
from typing import Iterable

from .engine import abilities

Signature = tuple[tuple[str, str], ...]

REGISTRY_PATH = Path(__file__).parent.parent / "puzzles" / "maneuvers.json"
# Tricks we've generated, audited, and decided NOT to promote. Without
# this the registry only ever learns from puzzles we KEEP, so a trick we
# keep rejecting keeps coming back and eating the whole attempt budget -
# the bounce-and-double-attack line turned up in every batch from the
# first one onward for exactly this reason.
DECLINED_PATH = Path(__file__).parent.parent / "puzzles" / "declined-maneuvers.json"

# EnterShowdown belongs here with the other two: it IS a move — the same
# move a ResolveCombat makes, just stopped halfway. Leaving it out keyed
# showdown entries on raw card_id while the identical atomic combat keyed
# on the vanilla bucket, so one trick tokenized two different ways
# depending on whether an [Action] card happened to be affordable.
_MOVE_ACTION_TYPES = {"MoveUnit", "ResolveCombat", "EnterShowdown"}


def _move_relevant_card_ids() -> set[str]:
    """Cards whose registered mechanic changes what a MOVE itself means —
    only move-count triggers (Yasuo - Windrider) qualify today.

    A card whose mechanic is a play-trigger (Blitzcrank) or an activated
    ability (Caitlyn) is just a body when all it does is move, so it must
    bucket as vanilla like any other body. Keying moves on raw card_id
    instead let one trick read as three different ones purely because a
    different mechanic card happened to fill the walk-in slot — seen in a
    live batch where 50,000 attempts produced three "distinct" survivors
    that were all the same bounce-and-double-attack line."""
    return set(abilities.MOVE_COUNT_TRIGGERS)


# Keywords that change what a *move* means rather than what a fight
# resolves to. Ganking is the only one today: it makes Battlefield-to-
# Battlefield legal (rule 810), so a mover that has it can go somewhere a
# mover without it cannot.
_MOVEMENT_KEYWORDS = frozenset({"Ganking"})


def _mover_token(action: dict) -> str:
    """Combat keywords (Assault/Shield/Tank) only matter on a step that
    actually fights. On a plain MoveUnit — walking into an empty or
    friendly zone — they do nothing, so including them splits the vanilla
    bucket on a detail the trick doesn't depend on.

    That is not hypothetical: generated-07640 and generated-08685 are the
    same Blitzcrank line, and read as two distinct tricks purely because
    one happened to walk a Shield unit into the cleared lane and the
    other a bare one. Bucketing by the full keyword set defeats the point
    of bucketing at all, which is to make interchangeable filler bodies
    interchangeable."""
    card_id = action["card_id"]
    if card_id in _move_relevant_card_ids():
        return card_id
    keywords = action["keywords"]
    if action["type"] == "MoveUnit":
        keywords = [k for k in keywords if k in _MOVEMENT_KEYWORDS]
    return "vanilla:" + ",".join(keywords)


def _collapse_empty_showdowns(steps: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """An EnterShowdown immediately followed by ResolveShowdown is a
    showdown nobody acted in, which is just a combat written across two
    steps — so it has to tokenize as the one ResolveCombat it's
    equivalent to.

    Without this, opening a window and declining it reads as two novel
    steps and breaks up any known run it sits inside. That is exactly how
    the bounce-and-double-attack line came back after being declined: the
    first of its two combats happened to open a window, the solver
    immediately resolved it, and the declined 4-step run no longer
    matched."""
    collapsed: list[tuple[str, str]] = []
    i = 0
    while i < len(steps):
        if (i + 1 < len(steps)
                and steps[i][0] == "EnterShowdown"
                and steps[i + 1][0] == "ResolveShowdown"):
            collapsed.append(("ResolveCombat", steps[i][1]))
            i += 2
        else:
            collapsed.append(steps[i])
            i += 1
    return collapsed


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
    return tuple(_collapse_empty_showdowns(steps))


# A registered trick shorter than this is too generic to match by
# containment — puzzle 2's signature is a single ("MoveUnit", "vanilla:")
# step and puzzle 4's is a single Ride The Wind, which between them appear
# inside almost every candidate ever generated.
MIN_CONTAINMENT_LENGTH = 3
# ...and even a long enough trick only counts as "already done" if it
# accounts for most of the candidate. A candidate that CHAINS a known
# trick with substantial other work is exactly the kind of composite
# puzzle worth keeping (e.g. starting at 5 points and using Yasuo's
# move-count point for the 8th), so it must not be rejected just for
# containing a known run somewhere inside it.
CONTAINMENT_COVERAGE = 0.7


def _contains_run(signature: Signature, run: Signature) -> bool:
    """Order-preserving subsequence, NOT a contiguous substring: `run`'s
    steps must appear in `signature` in order, but other steps may sit
    between them.

    Requiring contiguity meant a known trick with anything spliced into
    its middle read as novel. generated-05347 was puzzle 3's signature
    exactly — Yasuo move, Ride The Wind, Yasuo move — with one combat
    inserted to clear the destination first, and it survived a whole
    audit round before anyone noticed.

    This is only as loose as CONTAINMENT_COVERAGE allows. That gate
    demands the known trick be most of the candidate, so a 3-step trick
    can absorb at most one extra step (3/4 = 0.75, while 3/5 = 0.6 fails)
    — the gap budget is small, and all this change does is let the
    padding sit inside the run rather than only at its ends."""
    if len(run) > len(signature):
        return False
    it = iter(signature)
    return all(step in it for step in run)


def is_duplicate(signature: Signature, known: Iterable[Signature]) -> bool:
    """True if `signature` is the same trick as something already known —
    either exactly, or because a known multi-step trick makes up the bulk
    of it (a known run plus a bit of setup, e.g. "attack something, then
    do puzzle 3's Yasuo loop").

    Deliberately NOT pure containment: see CONTAINMENT_COVERAGE."""
    if not signature:
        return False
    for other in known:
        if signature == other:
            return True
        if (len(other) >= MIN_CONTAINMENT_LENGTH
                and len(other) / len(signature) >= CONTAINMENT_COVERAGE
                and _contains_run(signature, other)):
            return True
    return False


def load_registry() -> dict[str, Signature]:
    if not REGISTRY_PATH.exists():
        return {}
    raw = json.loads(REGISTRY_PATH.read_text())
    return {puzzle_id: tuple(tuple(step) for step in sig) for puzzle_id, sig in raw.items()}


def save_registry(registry: dict[str, Signature]) -> None:
    ordered = {puzzle_id: list(sig) for puzzle_id, sig in sorted(registry.items())}
    REGISTRY_PATH.write_text(json.dumps(ordered, indent=2) + "\n")


def load_declined() -> list[Signature]:
    if not DECLINED_PATH.exists():
        return []
    raw = json.loads(DECLINED_PATH.read_text())
    return [tuple(tuple(step) for step in entry["signature"]) for entry in raw]


def decline_signature(signature: Signature, note: str = "") -> bool:
    """Records a signature as seen-and-rejected so later batches skip it.
    Returns False if it was already known. `note` is for the human
    reading the file later — why this trick wasn't worth keeping."""
    if not signature:
        return False
    existing = load_declined()
    if signature in existing:
        return False
    raw = json.loads(DECLINED_PATH.read_text()) if DECLINED_PATH.exists() else []
    raw.append({"note": note, "signature": [list(step) for step in signature]})
    DECLINED_PATH.write_text(json.dumps(raw, indent=2) + "\n")
    return True


def known_signatures() -> set[Signature]:
    """Everything a new candidate has to be different from: promoted
    puzzles plus explicitly declined tricks."""
    return set(load_registry().values()) | set(load_declined())


def register_puzzle(puzzle_id: str, result: dict) -> Signature:
    """Computes and persists `result`'s signature under `puzzle_id` in the
    registry, overwriting any existing entry for that id. Returns the
    signature."""
    registry = load_registry()
    signature = maneuver_signature(result)
    registry[puzzle_id] = signature
    save_registry(registry)
    return signature
