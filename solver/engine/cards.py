"""Minimal card shape needed by legality checks.

Real card data will come from solver/data/cards_curated.json once the
curation step (design/01-data-sources.md) is built. This module just
defines the fields that cost/legality logic actually needs until then, so
actions.py doesn't have to guess at a schema prematurely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from .state import Domain

CardType = Literal["Unit", "Spell", "Gear"]

# When a card may be played, read off its own text:
#   "Slow"     - no marker on the card. Your turn only, and NOT during a
#                showdown (moving into an occupied battlefield starts one,
#                which is why you can't move in and then cast a Slow spell).
#   "Action"   - "[Action] (Play on your turn or in showdowns.)"
#   "Reaction" - "[Reaction] (Play any time, even before spells and
#                abilities resolve.)"
Speed = Literal["Slow", "Action", "Reaction"]


@dataclass(frozen=True)
class CardDef:
    card_id: str
    card_type: CardType
    energy_cost: int
    power_cost: int
    power_domain: Optional[Domain] = None  # None iff power_cost == 0
    might: Optional[int] = None  # Units only
    keywords: frozenset[str] = field(default_factory=frozenset)
    # Some units grant an exception to rule 355.8's default PlayUnit target
    # rule (Base or an already-controlled battlefield) via their own text —
    # e.g. Sneaky Deckhand: "You may play me to an open battlefield."
    can_play_to_open_battlefield: bool = False
    # Defaults to Slow because that's what an unmarked card is. Getting
    # this wrong in the permissive direction would invent lines that don't
    # exist, so the default is the restrictive one.
    speed: Speed = "Slow"
