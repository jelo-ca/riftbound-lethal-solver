"""Display names and printed text for card ids, read from the ingested
Riftcodex cache at `data/cards-ogn.json` (see solver/fetch_cards.py).

Strictly display data. Nothing here participates in legality, scoring or
search — the engine's rules facts live in card_pool.py, hand-transcribed,
because the API's card text is unstructured prose with no machine-
readable effect field (design/01-data-sources.md). Keeping the two apart
is what stops a fan API's wording from silently becoming a rules source.

The cache is optional by design. It's a network artifact that can be
absent on a fresh clone, or stale when a new printing appears, so every
lookup falls back to the card id itself and the solver behaves
identically either way. Only presentation degrades.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "cards-ogn.json"

# Ids the engine invents that have no printing behind them. The generated
# opponent body is a plain Might-N stat-stick standing in for "whatever
# the opponent has there", not a real card.
PLACEHOLDER_NAMES: dict[str, str] = {
    "generic-opponent": "Opponent Unit",
}


@lru_cache(maxsize=1)
def _cache() -> dict[str, dict]:
    if not CACHE_PATH.exists():
        return {}
    try:
        loaded = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def is_available() -> bool:
    """Whether the ingested cache is present and readable. Callers that
    want to warn a human ("run python -m solver.fetch_cards") can ask;
    callers that just want a label should call display_name and take the
    fallback."""
    return bool(_cache())


def display_name(card_id: str) -> str:
    """A human-readable name, falling back to `card_id` itself when the
    cache is missing or doesn't know it — so output is always printable
    and never raises."""
    if card_id in PLACEHOLDER_NAMES:
        return PLACEHOLDER_NAMES[card_id]
    card = _cache().get(card_id)
    if isinstance(card, dict):
        name = card.get("name")
        if isinstance(name, str) and name:
            return name
    return card_id


def card_text(card_id: str) -> str | None:
    """The printed rules text as plain prose, or None when unknown.

    Prose for a reader, never a rules source — see this module's
    docstring."""
    card = _cache().get(card_id)
    if not isinstance(card, dict):
        return None
    # RiftScribe (current source) carries a flat `description`. The nested
    # text.plain below is Riftcodex's shape, kept only so an older cache
    # still reads — when the source switched, this function silently
    # returned None for every card, and nothing noticed because it feeds
    # display and nothing else.
    description = card.get("description")
    if isinstance(description, str) and description:
        return description
    text = card.get("text")
    if isinstance(text, dict):
        plain = text.get("plain")
        if isinstance(plain, str) and plain:
            return plain
    return None


def describe(card_id: str) -> str:
    """`display_name`, with the id appended when it differs — the form
    worth printing in a trace or an audit, where knowing which printing
    matters as much as the name."""
    name = display_name(card_id)
    return name if name == card_id else f"{name} ({card_id})"
