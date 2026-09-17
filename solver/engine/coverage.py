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

  HANDLED               — every line of its printed text is implemented.
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
    # Cards whose entire text is keyword reminder text for keywords the
    # engine implements, or which print no text at all. Cleared in bulk
    # once [Tank] landed and card_data could supply stats without hand
    # transcription — nothing here needed new mechanics, only the two
    # things that were missing.
    "ogn-001-298": "Blazing Scorcher — [Accelerate] only",
    "ogn-054-298": "Sunlit Guardian — [Shield] and [Tank] only",
    "ogn-215-298": "Petty Officer — [Assault] only",
    "ogn-049-298": "Playful Phantom — no printed text",
    "ogn-088-298": "Mega-Mech — no printed text",
    "ogn-142-298": "Mountain Drake — no printed text",
    "ogn-175-298": "Shipyard Skulker — no printed text",
    "ogn-219-298": "Vanguard Sergeant — no printed text",
    "ogn-015-298": "Captain Farron — \"other friendly units here have [Assault]\" via "
                   "traits.AURA_SOURCES, the same shape as Taric",
    "ogn-082-298": "Whiteflame Protector — mandatory \"when you play me, give a unit "
                   "+8 Might\" via UNIT_PLAY_TRIGGERS; unlike the token-minting "
                   "triggers it still chooses a target, so it carries real params "
                   "rather than the parameterless sentinel",
    # The other two Recruit printings. Identical 1-Might colorless tokens to
    # the one already cleared; which art a token carries is not a rules fact.
    "ogn-272-298": "Recruit (NX) — same token as ogn-271-298",
    "ogn-273-298": "Recruit (ZN) — same token as ogn-271-298",
    # Buff-on-play. A buff is binary and worth +1 Might (UnitInstance.buffed);
    # abilities.apply_buff is the shared operation.
    "ogn-136-298": "Pit Rookie — \"buff another friendly unit\" via UNIT_PLAY_TRIGGERS",
    "ogn-217-298": "Trifarian Gloryseeker — [Legion]-gated self buff; the gate "
                   "suppresses the whole effect rather than shrinking it",
    "ogn-223-298": "Peak Guardian — self buff, then all other friendly units at the "
                   "same battlefield, conditional on having landed at one",
    "ogn-065-298": "Wizened Elder — \"while I'm buffed, +1 Might\" via "
                   "traits.SELF_CONDITIONALS",
    "ogn-133-298": "Flurry of Blades — [Reaction] \"deal 1 to all units at "
                   "battlefields\" via combat.deal_damage_to_all_at",
    "ogn-169-298": "Gust — [Reaction] bounce of a unit at 3 EFFECTIVE Might or less",
    "ogn-093-298": "Smoke Screen — [Reaction] -4 Might with the printed floor of 1",
    "ogn-017-298": "Iron Ballista — Gear, \"this enters exhausted; Exhaust: deal 2 "
                   "to a unit at a battlefield\" via engine/gear.py",
    "ogn-090-298": "Orb of Regret — Gear, \"Exhaust: give a unit -1 Might\"",
    "ogn-184-298": "The Syren — Gear, \"1 Energy, Exhaust: move a friendly unit at a "
                   "battlefield to your base\"",
    "ogn-009-298": "Hextech Ray — [Action] deal 3 to a unit at a battlefield",
    "ogn-085-298": "Falling Comet — [Action] deal 6 to a unit at a battlefield",
    "ogn-029-298": "Falling Star — two separate 3-damage instances, so both may be "
                   "aimed at the same unit",
    "ogn-172-298": "Rebuke — [Action] bounce a unit at a battlefield, either player's",
    "ogn-233-298": "Grand Strategem — [Action] +5 Might to every friendly unit, Base "
                   "included, with no target choice",
    "ogn-092-298": "Riptide Rex — mandatory play trigger, deal 6 to an enemy unit at a "
                   "battlefield",
    "ogn-234-298": "Harnessed Dragon — mandatory play trigger, kill an ENEMY unit "
                   "(narrower than Vengeance, which is unrestricted)",
    "ogn-125-298": "Bilgewater Bully — \"while I'm buffed, I have [Ganking]\" via "
                   "traits.SELF_CONDITIONALS; the grant reaches movement legality "
                   "because effective_keywords now delegates to resolved_traits",
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
    # The six Rune cards. Runes are modelled as domains in RunePool, not as
    # cards in a zone, and the Beginning Phase that channels them is
    # already resolved before the question is asked — so a Rune card can
    # never appear in a position the engine is asked about. They also print
    # no text, so there would be nothing to model even if one did.
    "ogn-007-298": "Fury Rune — runes are RunePool domains, not cards; no printed text",
    "ogn-042-298": "Calm Rune — as above",
    "ogn-089-298": "Mind Rune — as above",
    "ogn-126-298": "Body Rune — as above",
    "ogn-166-298": "Chaos Rune — as above",
    "ogn-214-298": "Order Rune — as above",
    # The three Reaction cards that reference an unresolved spell. They are
    # the only cards in the set that would need a resolution stack, and
    # they are dead here for a reason that has nothing to do with the
    # stack: the opponent never acts, so there is never an opposing spell
    # to counter or steal, and countering your own is never better than
    # not casting it.
    # "When you hold here" / "when I hold". Hold points are seeded into the
    # starting position and never scored live (the Beginning Phase is
    # resolved before the question is asked), so no Hold occurs during the
    # Action Phase being searched and these triggers cannot fire. Same
    # argument already accepted for Blitzcrank's third clause. Each card
    # below is ENTIRELY a hold trigger, so nothing else of theirs is left
    # unmodelled.
    "ogn-066-298": "Ahri, Alluring — \"when I hold, you score 1 point\"; no Hold "
                   "occurs during the turn being searched",
    "ogn-275-298": "Altar to Unity — hold trigger only",
    "ogn-280-298": "Grove of the God-Willow — hold trigger only",
    "ogn-281-298": "Hallowed Tomb — hold trigger only",
    "ogn-283-298": "Navori Fighting Pit — hold trigger only",
    "ogn-286-298": "Reckoner's Arena — hold trigger only",
    "ogn-288-298": "Startipped Peak — hold trigger only",
    "ogn-293-298": "The Grand Plaza — hold trigger only. Note this is an ALTERNATE "
                   "WIN CONDITION (\"if you have 7+ units here, you win the game\"); "
                   "it is inert only because the trigger cannot fire, so if Hold ever "
                   "becomes a live event this entry must be revisited first.",
    "ogn-045-298": "Defy — \"counter a spell\"; no opposing spell can ever exist",
    "ogn-064-298": "Wind Wall — \"counter a spell\"; as above",
    "ogn-080-298": "Mystic Reversal — \"gain control of a spell\"; as above",
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
# Cleared only while the predicate holds; blocking otherwise.
#
# Named "cleared" rather than "inert" because the two are not the same:
# Jeweled Colossus's [Shield] is genuinely implemented and does affect
# combat — only its [Vision] clause is conditionally dead. What the
# predicate decides is whether the engine understands the whole card, not
# whether the card does nothing.
CONDITIONALLY_CLEARED: dict[str, tuple[str, "object"]] = {
    "ogn-171-298": ("Mystic Poro — [Vision] only", _vision_inert_unless_karma),
    "ogn-086-298": ("Jeweled Colossus — [Shield] implemented, [Vision] dead without Karma",
                    _vision_inert_unless_karma),
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
    rule = CONDITIONALLY_CLEARED.get(card_id)
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
