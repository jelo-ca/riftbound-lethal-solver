"""Which cards the engine actually understands — and the refusal that
keeps it from bluffing about the rest.

The goal this serves: "given any Origins board, can the engine find
lethal." Origins has 298 distinct cards and the engine models a couple
of dozen. An engine that silently treats unmodelled text as absent can't
answer that question at all, because you can't tell its good answers
from its bad ones. Volibear, Furious reads as a plain 9-Might body —
no [Deflect 2], no "when I attack, deal 5 damage split among enemy units
here" — and the solver will happily report a line that his trigger
blows up, or miss the lethal his trigger creates.

So: BLOCKING IS THE DEFAULT. A card is only cleared by being written
into one of the two tables below, and anything unlisted refuses. Adding
a card to CARD_POOL is NOT enough — Faithful Manufactor sat in CARD_POOL
for weeks with a CardDef and a "when you play me" trigger that did
nothing, which is exactly the failure this table exists to stop. That's
why HANDLED is an explicit assertion with a note on HOW the text is
covered, not something derived from the registries.

Two ways a card is cleared:

  HANDLED          — every line of its printed text is implemented.
  INERT_FOR_LETHAL — it has text, but that text provably cannot change
                     whether lethal exists this turn. Single-turn puzzles
                     never reach a next Beginning Phase, never draw, and
                     never resolve a Hold (Hold points are seeded into
                     the starting position, not scored live), so whole
                     categories of text are unreachable by construction.

Both are keyed by card_id with a human-readable reason, and both are
checked against the card cache by the tests, so a typo or a renamed
printing fails loudly instead of quietly clearing the wrong card.
"""

from __future__ import annotations

from typing import Literal, Optional

from . import card_names
from .state import GameState

Classification = Literal["handled", "inert", "blocking"]


# card_id -> how the text is covered. Only cards whose text is FULLY
# implemented belong here; partial coverage is blocking, since a half-read
# card is exactly as dangerous as an unread one.
HANDLED: dict[str, str] = {
    "ogn-010-298": "Legion Rearguard — [Accelerate] via actions.play_unit_cost",
    "ogn-013-298": "Pouty Poro — [Deflect] via traits.deflect_tax",
    "ogn-043-298": "Charm — abilities.SPELL_EFFECTS",
    "ogn-052-298": "Stalwart Poro — [Shield] via traits.TRAIT_REGISTRY",
    "ogn-154-298": "Primal Strength — abilities.SPELL_EFFECTS ([Action] speed modelled)",
    "ogn-173-298": "Ride the Wind — abilities.SPELL_EFFECTS ([Action] speed modelled)",
    "ogn-176-298": "Sneaky Deckhand — can_play_to_open_battlefield",
    "ogn-188-298": "Zaunite Bouncer — abilities.UNIT_PLAY_TRIGGERS",
    "ogn-190-298": "Kog'Maw, Caustic — [Deathknell] via deaths.DEATH_TRIGGERS",
    "ogn-205-298": "Yasuo, Windrider — [Ganking] + abilities.MOVE_COUNT_TRIGGERS",
    "ogn-210-298": "Daring Poro — [Assault] via traits.TRAIT_REGISTRY",
    "ogn-211-298": "Faithful Manufactor — abilities.UNIT_PLAY_TRIGGERS",
    "ogn-218-298": "Vanguard Captain — [Legion] gate + UNIT_PLAY_TRIGGERS",
    "ogn-229-298": "Vengeance — abilities.SPELL_EFFECTS",
    "ogn-239-298": "Machine Evangel — [Deathknell] via deaths.DEATH_TRIGGERS",
    "ogn-271-298": "Recruit token — vanilla, no text to model",
}


# card_id -> why its text cannot change whether lethal exists this turn.
# These are rules judgements, not derivations; each one needs an argument
# that holds for a SINGLE TURN specifically.
INERT_FOR_LETHAL: dict[str, str] = {
    "ogn-096-298": "Watchful Sentry — [Deathknell] Draw 1. A drawn card can't be "
                   "played: no Main Deck is modelled, so the draw has no content.",
    "ogn-114-298": "Progress Day — Draw 4. Same: no deck, nothing arrives.",
    "ogn-178-298": "Undercover Agent — [Deathknell] Discard 2 then draw 2. Hand "
                   "churn only; no deck modelled.",
}


def classify(card_id: str) -> Classification:
    if card_id in HANDLED:
        return "handled"
    if card_id in INERT_FOR_LETHAL:
        return "inert"
    return "blocking"


def blocking_reason(card_id: str) -> str:
    """Why the engine won't reason about this card, quoting its own text
    so the refusal is actionable rather than just a card id."""
    text = card_names.card_text(card_id)
    if not text:
        return f"{card_names.describe(card_id)}: not in the coverage ledger"
    flattened = " ".join(text.split())
    if len(flattened) > 160:
        flattened = flattened[:157] + "..."
    return f"{card_names.describe(card_id)}: unmodelled text — \"{flattened}\""


def card_ids_present(state: GameState) -> set[str]:
    """Every card id the board depends on: units anywhere (both players),
    both hands, battlefield effects, and Legends. A card only has to be
    PRESENT to matter — an unmodelled enemy unit standing on a battlefield
    changes combat just as much as one we could play."""
    found: set[str] = set()
    for player in state.players:
        found.update(u.card_id for u in player.base_units)
        found.update(player.hand)
        if player.legend is not None:
            found.add(player.legend.card_id)
    for bf in state.battlefields:
        found.update(u.card_id for u in bf.units)
        if bf.effect_id is not None:
            found.add(bf.effect_id)
    return found


def blocking_cards(state: GameState, ignore: Optional[set[str]] = None) -> list[str]:
    """Reasons the engine cannot answer for this board, one per card,
    sorted for stable output. Empty means every card present is either
    handled or provably irrelevant to a single-turn lethal.

    `ignore` exempts synthetic ids the engine invents rather than draws
    from the set (generate.py's "generic-opponent" stat-stick), which have
    no printing behind them and no text to miss.
    """
    exempt = (ignore or set()) | set(card_names.PLACEHOLDER_NAMES)
    return sorted(
        blocking_reason(card_id)
        for card_id in card_ids_present(state)
        if card_id not in exempt and classify(card_id) == "blocking"
    )
