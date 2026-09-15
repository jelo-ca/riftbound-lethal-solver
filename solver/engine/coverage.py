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
    "ogn-067-298": "Blitzcrank, Impassive — [Tank] via combat.assignable_targets, "
                   "play trigger via UNIT_PLAY_TRIGGERS. Its third clause, \"when I "
                   "hold, return me to my owner's hand\", is unreachable rather than "
                   "implemented: Hold is seeded into the starting position and never "
                   "scored live, so no Hold occurs during the turn being searched.",
    "ogn-068-298": "Caitlyn, Patrolling — \"assigned combat damage last\" via "
                   "combat.DAMAGE_LAST_CARD_IDS, activated ability via ABILITY_EFFECTS",
    "ogn-074-298": "Taric, Protector — [Shield] and [Tank] via traits/combat, "
                   "\"other friendly units here have [Shield]\" via traits.AURA_SOURCES",
    "ogn-110-298": "Ekko, Recurrent — [Accelerate] via play_unit_cost, [Deathknell] "
                   "\"recycle me to ready your runes\" via deaths.DEATH_TRIGGERS and "
                   "state.ready_runes",
    "ogn-229-298": "Vengeance — abilities.SPELL_EFFECTS",
    "ogn-239-298": "Machine Evangel — [Deathknell] via deaths.DEATH_TRIGGERS",
    "ogn-271-298": "Recruit token — vanilla, no text to model",
}


# card_id -> why its text cannot change whether lethal exists this turn.
# These are rules judgements, not derivations; each one needs an argument
# that holds for a SINGLE TURN specifically.
#
# The position model they all lean on (settled 2026-09-15): there is no
# Main Deck, and the Beginning Phase is already resolved before the
# question is asked. So "draw" has nothing to draw, and no effect that
# only pays off on a later turn can ever pay off.
INERT_FOR_LETHAL: dict[str, str] = {
    "ogn-096-298": "Watchful Sentry — [Deathknell] Draw 1. No Main Deck, so the "
                   "draw has no content and cannot add a playable card.",
    "ogn-114-298": "Progress Day — Draw 4. Same: no deck, nothing arrives.",
    "ogn-178-298": "Undercover Agent — [Deathknell] Discard 2 then draw 2. The "
                   "draw is empty; the discard only shrinks our own hand, which "
                   "a solver would never choose and which cannot create lethal.",
    "ogn-083-298": "Consult the Past — Draw 2. No deck.",
    "ogn-099-298": "Garbage Grabber — an activated ability whose whole effect is "
                   "Draw 1. With no deck it does nothing, so it is never worth "
                   "activating regardless of its trash cost.",
    "ogn-135-298": "Pakaa Cub — [Hidden] and nothing else. Hiding spends a rune "
                   "now to play for 0 Energy later; inside one turn that is "
                   "strictly worse than playing the card, and no Origins card "
                   "rewards holding fewer runes (verified across the set), so "
                   "hiding is never correct.",
    "ogn-274-298": "Sprite — [Temporary] and nothing else. It dies at the start "
                   "of your next Beginning Phase, which a single turn never "
                   "reaches.",
    "ogn-073-298": "Sona, Harmonious — \"ready 4 friendly runes AT THE END OF YOUR "
                   "TURN\". The lethal question is settled during the Action Phase; "
                   "runes readied after it can't pay for anything. Contrast Ekko, "
                   "whose readying fires mid-turn on death and is therefore real.",
    "ogn-289-298": "Targon's Peak — \"when you conquer here, ready 2 runes AT THE "
                   "END OF THIS TURN\". Same: the readying lands after every action "
                   "that could have used it.",
}


KARMA_CHANNELER = "ogn-235-298"


def _vision_inert_unless_karma(present: set[str]) -> bool:
    """[Vision] looks at the top of the Main Deck and may recycle it. With
    no deck there is nothing to look at and nothing to recycle, so it does
    nothing observable — UNLESS Karma, Channeler is on the board. She is
    the only card in Origins that triggers on recycling ("when you recycle
    one or more cards, buff a friendly unit"), which would turn a Vision
    into a Might buff and therefore into something that can change lethal.
    """
    return KARMA_CHANNELER not in present


# card_id -> (reason, predicate over the card ids present on the board).
# Inert only while the predicate holds; blocking otherwise. Board-dependent
# because some text is dead on its own and live next to one specific card.
CONDITIONALLY_INERT: dict[str, tuple[str, "object"]] = {
    "ogn-171-298": ("Mystic Poro — [Vision] only", _vision_inert_unless_karma),
}


def classify(card_id: str, present: Optional[set[str]] = None) -> Classification:
    """Static classification, plus the board-conditional entries when
    `present` (the card ids on the board) is supplied. Without `present` a
    conditionally-inert card reports blocking — the safe direction, since
    the condition is unverified rather than known to hold."""
    if card_id in HANDLED:
        return "handled"
    if card_id in INERT_FOR_LETHAL:
        return "inert"
    rule = CONDITIONALLY_INERT.get(card_id)
    if rule is not None and present is not None:
        _, is_inert = rule
        if is_inert(present):
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
    present = card_ids_present(state)
    return sorted(
        blocking_reason(card_id)
        for card_id in present
        if card_id not in exempt and classify(card_id, present) == "blocking"
    )
