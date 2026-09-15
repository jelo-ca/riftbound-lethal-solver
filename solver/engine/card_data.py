"""Build CardDefs from the ingested card cache instead of by hand.

Every card-data bug this project has had came from hand-transcription.
Five of fourteen cards carried wrong costs or Might — Yasuo at half his
printed Might silently reshaped a whole puzzle around a fight he could
not lose — and Legion Rearguard and Vanguard Captain were both recorded
with no keywords while printing [Accelerate] and [Legion]. The parts of a
card that are *structured* (costs, Might, domains, keywords) are exactly
the parts a human retypes badly and a machine copies perfectly, and
data/cards-ogn.json already holds all 352 printings of them.

WHAT THIS DOES NOT DO — and the distinction is the whole point. A
generated CardDef carries a card's STATS. It says nothing whatsoever
about whether the engine understands that card's TEXT. Faithful
Manufactor had a correct CardDef for weeks while its "when you play me"
trigger did nothing at all, and the board was silently wrong. Whether a
card's text is modelled is engine/coverage.py's question, and it is
deliberately kept in a separate module with a separate ledger. Generating
a CardDef must never be mistaken for clearing a card, so nothing here
imports or consults coverage.

REFUSES RATHER THAN GUESSES. Guessing is the failure mode this replaces,
so anything the cache can't answer unambiguously raises CardDataError
with the reason rather than inventing a plausible value:

  - Legend / Rune / Battlefield types, which CardDef's CardType cannot
    represent at all (72 printings);
  - null energy cost — the Recruit and Sprite tokens, which are minted by
    effects and never paid for, so there is no cost to read (4 printings);
  - two domains plus a Power cost, where which domain pays is genuinely
    ambiguous and CardDef holds only one power_domain (10 printings).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Optional

from . import card_names
from .cards import CardDef, CardType, Speed
from .state import Domain

# Cache keywords are lowercase and may carry the printed numeric suffix
# ("shield 2", "assault 3"); the engine's TRAIT_REGISTRY keys are
# capitalised ("Shield 2"). Everything else about the grammar is shared.
#
# [Action] and [Reaction] are deliberately NOT traits. They appear in the
# cache's keyword list but describe WHEN a card may be played, which the
# engine models as CardDef.speed — Ride the Wind carries speed="Action"
# and an empty keyword set, not a keyword called "Action".
SPEED_KEYWORDS: dict[str, Speed] = {"action": "Action", "reaction": "Reaction"}

REPRESENTABLE_TYPES: frozenset[str] = frozenset({"Unit", "Spell", "Gear"})

_OPEN_BATTLEFIELD = re.compile(r"you may play me to an open battlefield", re.I)
_ACCELERATE_RUNE = re.compile(r"\[Accelerate\][^)]*?:rb_rune_(\w+):", re.I)


class CardDataError(ValueError):
    """The cache cannot describe this card unambiguously. Carries the
    reason, because a caller deciding whether to skip a card or fix the
    data needs to know which of the two it is."""


@lru_cache(maxsize=1)
def _cache() -> dict[str, dict]:
    path = card_names.CACHE_PATH
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _normalise_keyword(raw: str) -> str:
    """"shield 2" -> "Shield 2". Only the name capitalises; the numeric
    suffix is the printed amount and passes through untouched."""
    name, _, amount = raw.strip().rpartition(" ")
    if name and amount.isdigit():
        return f"{name.capitalize()} {amount}"
    return raw.strip().capitalize()


def build_card_def(card_id: str) -> CardDef:
    """The CardDef for `card_id` as printed, or CardDataError explaining
    why the cache can't say."""
    card = _cache().get(card_id)
    if not isinstance(card, dict):
        return _fail(card_id, "not present in the card cache")

    card_type = card.get("type")
    if card_type not in REPRESENTABLE_TYPES:
        return _fail(card_id, f"type {card_type!r} has no CardDef representation")

    stats = card.get("stats") or {}
    energy = stats.get("energy")
    if not isinstance(energy, int):
        return _fail(card_id, "no printed Energy cost — minted by an effect, never paid for")

    domains = [d for d in (card.get("domains") or []) if isinstance(d, str)]
    power = stats.get("power") or 0
    power_domain: Optional[Domain] = None
    if power:
        if len(domains) != 1:
            return _fail(card_id, f"Power cost of {power} with domains {domains} — "
                                   "which domain pays is ambiguous")
        power_domain = domains[0]  # type: ignore[assignment]

    raw_keywords = [k.lower().strip() for k in (card.get("keywords") or []) if isinstance(k, str)]
    description = card.get("description") or ""

    speed: Speed = "Slow"
    for raw in raw_keywords:
        if raw in SPEED_KEYWORDS:
            speed = SPEED_KEYWORDS[raw]

    keywords = frozenset(
        _normalise_keyword(raw) for raw in raw_keywords if raw not in SPEED_KEYWORDS
    )

    accelerate_domain = None
    if any(k.startswith("accelerate") for k in raw_keywords):
        accelerate_domain = _accelerate_domain(card_id, description, domains)

    might = stats.get("might")
    return CardDef(
        card_id=card_id,
        card_type=card_type,  # type: ignore[arg-type]
        energy_cost=energy,
        power_cost=power,
        power_domain=power_domain,
        might=might if isinstance(might, int) else None,
        keywords=keywords,
        can_play_to_open_battlefield=bool(_OPEN_BATTLEFIELD.search(description)),
        speed=speed,
        accelerate_domain=accelerate_domain,
    )


def _accelerate_domain(card_id: str, description: str, domains: list[str]) -> Domain:
    """[Accelerate]'s extra rune, read from the printed cost symbol rather
    than assumed from the card's domain. Across all 14 printings the two
    agree, but reading the symbol is what makes that a verified fact
    instead of an assumption — and a disagreement means the data changed
    under us, which should stop the build rather than pass silently."""
    match = _ACCELERATE_RUNE.search(description)
    if not match:
        return _fail(card_id, "[Accelerate] with no rune symbol in its printed cost")
    printed = match.group(1).capitalize()
    if len(domains) == 1 and printed != domains[0]:
        return _fail(card_id, f"[Accelerate] rune {printed} disagrees with card domain {domains[0]}")
    return printed  # type: ignore[return-value]


def _fail(card_id: str, reason: str):
    raise CardDataError(f"{card_names.describe(card_id)}: {reason}")


def try_build_card_def(card_id: str) -> Optional[CardDef]:
    """build_card_def, or None where it would refuse — for callers walking
    the whole set who just want what's representable."""
    try:
        return build_card_def(card_id)
    except CardDataError:
        return None


def generatable_card_ids() -> list[str]:
    """Every printing the cache can describe, sorted."""
    return sorted(cid for cid in _cache() if try_build_card_def(cid) is not None)
