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


# OUT OF SCOPE BY DECISION (2026-09-17), not merely unimplemented.
#
# Zone is "base" or a battlefield id, with no way to express WHOSE base,
# so a card that sends an ENEMY unit to its own base has nowhere to put
# it. Extending Zone to name both bases would touch the whole state model
# and was weighed against what it buys: the only movement toward an
# enemy base comes from movement spells and abilities the player casts,
# which is a narrow slice.
#
# Cards in this class stay BLOCKING, so a board containing one is refused
# rather than mis-solved. "Friendly unit to YOUR base" is unaffected and
# works today (The Syren, Machine Evangel).
ZONE_MODEL_OUT_OF_SCOPE: dict[str, str] = {
    "ogn-191-298": "Maddened Marauder — \"move a unit from a battlefield to its "
                   "base\" is unrepresentable when the unit is the opponent's",
}


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
    "ogn-004-298": "Cleave — [Action] grant [Assault 3] via abilities.grant_trait; a "
                   "trait rather than flat Might, so it is worth nothing on defence",
    "ogn-105-298": "Singularity — deal 6 to each of up to two DISTINCT units",
    "ogn-206-298": "Back to Back — [Reaction] +2 Might to two distinct friendly units",
    "ogn-016-298": "Dangerous Duo — [Legion]-gated play trigger, +2 Might to a unit",
    "ogn-132-298": "First Mate — play trigger, ready another unit (not itself, which "
                   "is what stops it undoing its own entering exhausted)",
    "ogn-141-298": "Kinkou Monk — play trigger, buff up to two other friendly units",
    "ogn-069-298": "Last Stand — double PRINTED Might (the conditional and positional "
                   "parts of effective Might aren't the unit's own to double), and "
                   "grant [Temporary], which is recorded even though inert",
    "ogn-123-298": "Unchecked Power — exhaust all friendly units, then 12 to every "
                   "unit at a battlefield; the self-exhaust is a real cost",
    "ogn-128-298": "Challenge — SIMULTANEOUS mutual damage; both Mights are read "
                   "before either lands, so a dying unit still deals its damage",
    "ogn-046-298": "En Garde — [Reaction] +1 Might, doubled when the target is the "
                   "only unit WE control in its zone (enemies there don't count)",
    "ogn-149-298": "Carnivorous Snapvine — play trigger, simultaneous mutual damage "
                   "with itself as one side, so it can trade itself for a bigger body",
    "ogn-124-298": "Arena Bar — Gear, \"Exhaust: buff an EXHAUSTED friendly unit\"",
    "ogn-212-298": "Forge of the Future — Gear, mandatory \"when you play this, play a "
                   "1 Might Recruit token at your base\" via abilities.GEAR_PLAY_TRIGGERS "
                   "(the first Gear play-trigger; PlayGear gained its own trigger_params "
                   "field for it). Its \"Kill this: Recycle up to 4 cards from trashes\" "
                   "is inert by argument, not code: \"recycle\" a card means returning it "
                   "to the Main Deck (established by Vision/Ekko's identical reading), "
                   "which is a no-op with no deck, and nothing in the pool reacts to a "
                   "Gear dying — so activating it costs a permanent for zero benefit, "
                   "and a solver never would. Optional, so declining it is always legal.",
    "ogn-125-298": "Bilgewater Bully — \"while I'm buffed, I have [Ganking]\" via "
                   "traits.SELF_CONDITIONALS; the grant reaches movement legality "
                   "because effective_keywords now delegates to resolved_traits",
    # Trash zone (state.PlayerState.trash) — starts empty at position
    # setup, fills live during the turn as units die or spells resolve.
    # See state.py's field comment and deaths.fire_death_triggers.
    "ogn-109-298": "Dr. Mundo, Expert — Might scales with trash size via "
                   "traits.TRASH_COUNT_MIGHT. \"At the start of your Beginning Phase, "
                   "recycle 3 from your trash\" fires before the Action Phase this "
                   "engine searches, and trash starts empty, so it's a pre-turn "
                   "non-event",
    "ogn-036-298": "Vi, Destructive — \"Recycle 1 from your trash: give me +1 Might "
                   "this turn\" via ABILITY_EFFECTS; the recycled card IS the cost, "
                   "same shape as Sett Brawler's spend-a-buff ability",
    "ogn-165-298": "Cemetery Attendant — mandatory \"when you play me, return a unit "
                   "from your trash to your hand\" via UNIT_PLAY_TRIGGERS; unreachable "
                   "(not offered) rather than a fizzled no-op when trash has no units, "
                   "same convention as Harnessed Dragon against an empty board",
    "ogn-170-298": "Morbid Return — [Action] \"return a unit from your trash to your "
                   "hand\" via SPELL_EFFECTS",
    "ogn-196-298": "Soulgorger — optional play trigger, \"play a unit from your trash, "
                   "ignoring its Energy cost\" via actions.play_unit_from_trash. "
                   "Restricted to trash units with NO UNIT_PLAY_TRIGGERS entry of their "
                   "own (play_unit_from_trash never dispatches a replayed unit's own "
                   "\"when you play me\" text) — restrictive, not permissive.",
    "ogn-198-298": "The Harrowing — [Action] same effect as Soulgorger, via "
                   "SPELL_EFFECTS; the replayed unit's Power payment comes from what "
                   "The Harrowing's OWN cost leaves behind, same \"pay from what's "
                   "left\" shape as [Deflect]'s trigger tax.",
    "ogn-226-298": "Spectral Matron — optional play trigger, \"play a unit costing "
                   "<=3 Energy and <=1 Power (any domain) from your trash, ignoring "
                   "its cost\" (project owner, 2026-09-18, on the bare rainbow icon's "
                   "meaning). Waives the WHOLE cost, unlike Soulgorger/The Harrowing — "
                   "reuses play_unit_from_trash with an empty RunePayment. Same "
                   "no-own-play-trigger restriction on the replayed candidate.",
    "ogn-037-298": "Immortal Phoenix — [Assault 2] (TRAIT_REGISTRY's generic numeric "
                   "form), optional reaction \"when you kill a unit with a spell, pay "
                   "1 Energy, 1 Fury to play me from your trash\" via "
                   "abilities.SPELL_KILL_REACTIONS. The kill is detected as a diff "
                   "(deaths.units_killed_between) rather than per-spell bookkeeping, so "
                   "it's real for damage spells too, not just outright-kill ones — "
                   "restricted to spells whose own resolution is a single outcome "
                   "(true of every registered spell today).",
    # [Conquer] triggers — engine/conquer.py, hooked into
    # scoring.resolve_control_change.
    "ogn-164-298": "Sett, Brawler — \"when I'm played and when I conquer, buff me\" "
                   "via UNIT_PLAY_TRIGGERS and conquer.CONQUER_TRIGGERS (both share "
                   "abilities.apply_buff, so a Sett who is already buffed correctly "
                   "gets nothing from the second trigger), \"spend my buff: give me "
                   "+4 Might\" via ABILITY_EFFECTS",
    "ogn-164a-298": "Sett, Brawler — same card as ogn-164-298, alternate art",
    "ogn-147-298": "Wildclaw Shaman — \"you may spend a buff to buff me and ready me\" "
                   "via UNIT_PLAY_TRIGGERS; the buff-spend target must already carry a "
                   "buff, which also rules out targeting itself (it just entered)",
    "ogn-151-298": "Lee Sin, Centered — \"other buffed friendly units at my battlefield "
                   "have +2 Might\" via traits.BUFF_MIGHT_AURA_SOURCES, a co-located "
                   "conditional Might aura alongside AURA_SOURCES' trait grants",
    "ogn-151a-298": "Lee Sin, Centered — same card, alternate printing",
    "ogn-153-298": "Overt Operation — \"for each friendly unit, you may spend its buff "
                   "to ready it, then buff all friendly units\" via SPELL_EFFECTS; the "
                   "per-unit spend choice is independent, so candidates are the full "
                   "powerset of currently-buffed friendly units, not a capped count",
    "ogn-240-298": "Sett, Kingpin — [Tank] handled; \"+1 Might for each buffed friendly "
                   "unit at my battlefield\" (itself included) via "
                   "traits.SELF_COUNT_MIGHT, a counting variant of SelfConditional's "
                   "boolean condition — the count reads unit.buffed on each occupant, "
                   "never Might, so the non-circularity invariant holds",
    "ogn-240a-298": "Sett, Kingpin — same card, alternate printing",
    "ogn-257-298": "Blind Monk — Legend, \"1 Energy, Exhaust: Buff a friendly unit\" via "
                   "legends.LEGEND_ABILITIES, same shape as Yasuo, Unforgiven",
    "ogn-304-298": "Blind Monk — same Legend, alternate printing",
    "ogn-304-star-298": "Blind Monk — same Legend, alternate printing",
    # Ledger-hygiene fixes: implemented and tested since before this pass,
    # just never added to the ledger. Leaving them off cost nothing but
    # missed coverage (the safe direction), unlike the Warden regression
    # above, which cost correctness.
    "ogn-259-298": "Yasuo, Unforgiven — Legend, \"2 Energy, Exhaust: Move a friendly "
                   "unit to or from its base\" via legends.LEGEND_ABILITIES, the same "
                   "generic dispatch (search.py) that makes Blind Monk reachable",
    "ogn-305-298": "Unforgiven — same Legend as ogn-259-298, alternate printing",
    "ogn-305-star-298": "Unforgiven — same Legend as ogn-259-298, alternate printing",
    "ogn-267-298": "Bounty Hunter — Legend, \"Exhaust: Give a unit [Ganking] this turn\" "
                   "via legends.LEGEND_ABILITIES and abilities.grant_trait; unrestricted "
                   "target, same reading as Vengeance's \"kill a unit\"",
    "ogn-265-298": "Herald of the Arcane — Legend, \"1 Energy, Exhaust: Play a 1 Might "
                   "Recruit unit token\" via legends.LEGEND_ABILITIES and "
                   "mint_token_unit. Prints no zone (unlike Faithful Manufactor's "
                   "\"here\" or Machine Evangel's \"into your base\") — restricted to "
                   "Base pending a definitive reading; restrictive, not permissive.",
    "ogn-295-298": "Vilemaw's Lair — \"Units can't move from here to base\" via "
                   "battlefields.BattlefieldEffect(blocks_move_to_base=True), exercised "
                   "in puzzle 7 and covered directly by test_battlefields.py",
    # Observer triggers — "when you play ANOTHER unit," fired at whoever is
    # already on the board watching, from actions.apply_play_unit (the one
    # choke point every genuine unit-from-hand play routes through). See
    # engine/observers.py.
    "ogn-139-298": "Cithria of Cloudfield — \"when you play another unit, buff me\" "
                   "via observers.OBSERVER_PLAY_TRIGGERS; excludes her own play via "
                   "an instance_id check, so she never buffs off her own arrival",
    # "When I attack" triggers (RULES ANSWER, project owner, 2026-09-17): a
    # trigger that kills the defender before the Combat Damage Step removes
    # it from combat entirely — it deals no combat damage. abilities.py's
    # ATTACK_TRIGGERS registry forces the combat through the showdown
    # mechanism with the trigger resolved BEFORE any damage-assignment
    # option is computed, so a killed defender is simply gone from
    # combat.showdown_assignment_options's live board by the time
    # assignment happens. See search._board_actions_with_showdown_entries
    # and abilities.ATTACK_TRIGGERS's own module comment.
    "ogn-148-298": "Anivia, Primal — mandatory \"when I attack, deal 3 to all enemy units "
                   "here\" via abilities.ATTACK_TRIGGERS, resolved before damage assignment",
    "ogn-076-298": "Yasuo, Remorseful — mandatory \"when I attack, deal damage equal to my "
                   "Might to an enemy unit here\" via abilities.ATTACK_TRIGGERS; the amount "
                   "is read at trigger time via traits.effective_might",
    "ogn-076a-298": "Yasuo, Remorseful (alt art) — same card as ogn-076-298",
    "ogn-130-298": "Crackshot Corsair — mandatory \"when I attack, deal 1 to an enemy unit "
                   "here\" via abilities.ATTACK_TRIGGERS",
    "ogn-131-298": "Dune Drake — mandatory \"when I attack, give me +2 Might this turn if "
                   "there is a ready enemy unit here\" via abilities.ATTACK_TRIGGERS; the "
                   "trigger always fires, its effect is merely conditional",
    # "While I'm attacking or defending alone" (RULES ANSWER, project
    # owner, 2026-09-17): SelfConditional.condition now takes the unit's
    # combat role (designation) as a fourth argument. "Attacking alone" is
    # unconditionally true in this engine (combat.py: the attacking side
    # is always exactly one unit); "defending alone" is checked for real,
    # against co-located controllers, the same shape as En Garde.
    "ogn-055-298": "Wielder of Water — \"while I'm attacking or defending alone, +2 Might\" "
                   "via traits.SELF_CONDITIONALS with the new designation parameter",
    # Generic discard mechanism (actions.discard_from_hand) — a card
    # leaving hand for trash by discard, real (never a no-op: it shrinks a
    # resource-limited hand) unlike "draw," which has no Main Deck to draw
    # from. observers.fire_observer_discard_triggers fires "when you
    # discard" watchers off the same choke point apply_play_unit's
    # observer call already uses for "when you play."
    "ogn-003-298": "Chemtech Enforcer — [Assault 2] (numeric TRAIT_REGISTRY form), mandatory "
                   "\"when you play me, discard 1\" via abilities.UNIT_PLAY_TRIGGERS and "
                   "actions.discard_from_hand",
    "ogn-020-298": "Scrapyard Champion — [Legion]-gated mandatory \"discard 2, then draw 2\"; "
                   "Legion suppresses the WHOLE effect when unmet (no discard at all), same "
                   "reading as Vanguard Captain's token count going to zero rather than one; "
                   "the draw is a no-op (no Main Deck), the discard is real via "
                   "actions.discard_from_hand",
    "ogn-202-298": "Jinx, Rebel — \"when you discard one or more cards, ready me and give me "
                   "+1 Might this turn\" via observers.OBSERVER_DISCARD_TRIGGERS, fired once per "
                   "discard EVENT (not once per card) from actions.discard_from_hand's callers",
    "ogn-202a-298": "Jinx, Rebel — same card as ogn-202-298, alternate art",
    "ogn-019-298": "Raging Soul — \"if you've discarded a card this turn, I have [Assault] and "
                   "[Ganking]\" via traits.SELF_CONDITIONALS reading state.cards_discarded_this_turn "
                   "(new GameState field, bumped by actions.discard_from_hand, same shape as "
                   "cards_played_this_turn feeding legion_condition_met)",
    "ogn-008-298": "Get Excited! — [Action] \"Discard 1. Deal its Energy cost as damage to a unit "
                   "at a battlefield.\" via abilities.SPELL_EFFECTS and actions.discard_from_hand; "
                   "the damage amount is read off the DISCARDED card's own printed Energy cost "
                   "(card_pool.card_def), so which card is discarded is a real, scored choice, "
                   "not free to ignore the way a no-op draw is",
    # "Draw" or "if killed, draw" is a no-op (no Main Deck) with nothing
    # else worth modelling on top; each reduces to an existing generic
    # spell shape (abilities.FLAT_DAMAGE_SPELLS / the unrestricted-target
    # Might-grant pattern), same convention as Watchful Sentry's draw.
    "ogn-005-298": "Disintegrate — [Action] \"Deal 3 to a unit at a battlefield.\" via "
                   "abilities.FLAT_DAMAGE_SPELLS; \"if this kills it, draw 1\" is a no-op "
                   "regardless of the kill (no Main Deck)",
    "ogn-024-298": "Void Seeker — [Action] \"Deal 4 to a unit at a battlefield.\" via "
                   "abilities.FLAT_DAMAGE_SPELLS; \"draw 1\" is a no-op",
    "ogn-058-298": "Discipline — [Reaction] \"Give a unit +2 Might this turn.\" via "
                   "abilities.SPELL_EFFECTS, same unrestricted-anywhere target shape as "
                   "Primal Strength; \"draw 1\" is a no-op",
    "ogn-095-298": "Stupefy — [Reaction] \"Give a unit -1 Might this turn, to a minimum of 1 "
                   "Might.\" via abilities.SPELL_EFFECTS, same shape as Smoke Screen; \"draw 1\" "
                   "is a no-op",
    "ogn-192-298": "Mindsplitter — mandatory \"when you play me, choose an opponent, they reveal "
                   "their hand, choose a card from it, they discard it\" via UNIT_PLAY_TRIGGERS and "
                   "actions.discard_from_hand applied to the OPPONENT's hand/controller — reusing "
                   "the real mechanism rather than arguing it inert matters here specifically "
                   "because it correctly fires an enemy-controlled \"when you discard\" watcher "
                   "(a hypothetical enemy Jinx, Rebel) exactly as the real rules would, instead of "
                   "silently under-crediting the opponent's board",
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
    "ogn-087-298": "Lecturing Yordle — [Tank] (generic TRAIT_REGISTRY keyword) plus a mandatory "
                   "\"when you play me, draw 1\"; the only non-keyword text is that draw, a "
                   "no-op with no Main Deck, so nothing is left half-covered",
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
    "ogn-251-298": "Loose Cannon — Legend, \"AT THE START OF YOUR BEGINNING PHASE, "
                   "draw 1 if you have <=1 card in hand\". The Beginning Phase is "
                   "already resolved before the Action Phase this engine searches — "
                   "same pre-turn non-event as Sona/Targon's Peak, and the draw would "
                   "be a no-op anyway (no Main Deck).",
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
    # Play-restriction cards: text that limits what the OPPONENT can do.
    # The opponent never acts, so a restriction on their plays is already
    # true before the card exists — nothing it forbids could have happened
    # anyway. Each entry below is checked against its full printed text so
    # a restriction bundled with a real effect doesn't get cleared for free.
    "ogn-018-298": "Noxus Saboteur — \"Your opponents' [Hidden] cards can't be "
                   "revealed here.\" A reveal happens only when the opponent plays "
                   "their own hidden card as a Reaction, and the opponent never "
                   "acts, so this can never be triggered regardless of the "
                   "restriction. (Separately, Hidden is not modelled as a zone at "
                   "all — design/00-overview.md: \"no hidden zones\" — so there is "
                   "no reveal event in this engine for either player.)",
    "ogn-026-298": "Brynhir Thundersong — \"When you play me, opponents can't play "
                   "cards this turn.\" That is the entire text. The opponent never "
                   "acts, so the restriction holds vacuously whether or not this "
                   "card is played; the mandatory play trigger has no observable "
                   "effect on the search.",
    # ogn-070-298 Mageseeker Warden was cleared here once (2026-09-17) on the
    # argument that its "spells/abilities can't ready enemy units" clause
    # was vacuous because the only card reading an enemy unit's ready state,
    # Dune Drake, was itself BLOCKING. That argument's own note said to
    # revisit if Dune Drake was ever implemented — it now is (see the
    # attack-trigger entries below), so a board with Warden + First Mate +
    # Dune Drake is a real case the restriction could change, and Warden's
    # ready-restriction itself still isn't modelled. Back to BLOCKING until
    # that restriction is actually built.
    # [Conquer] triggers whose text needs no new subsystem — see
    # engine/conquer.py for the ones that do.
    "ogn-039-298": "Kai'Sa, Survivor — [Accelerate], and \"when I conquer, draw 1\". "
                   "No Main Deck, so the draw has no content.",
    "ogn-039a-298": "Kai'Sa, Survivor — same card as ogn-039-298, alternate art",
    "ogn-291-298": "The Candlelit Sanctum — \"when you conquer here, look at the top "
                   "two cards of your Main Deck. You may recycle one or both.\" No "
                   "Main Deck, so there is nothing to look at and nothing to recycle.",
    "ogn-071-298": "Party Favors — \"Each OTHER player chooses Cards or Runes. For each "
                   "player that chooses Cards, you and that player each draw 1. For each "
                   "player that chooses Runes, you and that player each channel 1 rune "
                   "exhausted.\" Every branch is gated on the OPPONENT making a choice, and "
                   "the opponent never acts in this model — there is no decision node for "
                   "them at all, so neither branch is ever entered, for either player. "
                   "Distinct from the play-restriction cluster above (a restriction on the "
                   "opponent that holds vacuously): here the gate is on an opponent CHOICE "
                   "that never happens, so the whole spell — including our own half of the "
                   "payoff — simply never resolves.",
    "ogn-282-298": "Monastery of Hirana — \"when you conquer here, you may spend a "
                   "buff to draw 1.\" Spending a buff is a real cost (a genuine "
                   "-1 Might) for a draw that does nothing with no Main Deck, so a "
                   "solver would never take the option; it's optional (\"you may\"), "
                   "so declining it is always legal, and the option can never help "
                   "find a lethal that declining it wouldn't also find.",
    # Deck/rune-deck cluster: every clause here reads a zone (the Main
    # Deck, or — Twisted Fate's case — the Rune Deck) that this engine
    # never models, so there is nothing for any of these effects to act
    # on regardless of how elaborate the printed text looks.
    "ogn-062-298": "Reinforce — \"Look at the top 5 cards of your Main Deck. You may banish "
                   "a unit from among them, then play it... Recycle the remaining cards.\" No "
                   "Main Deck, so there are no top 5 cards to look at, nothing to banish or "
                   "play, and nothing to recycle.",
    "ogn-115-298": "Promising Future — \"Each player looks at the top 5 cards of their Main "
                   "Deck, chooses one, then recycles the rest. Starting with the next player, "
                   "each player plays those cards...\" No Main Deck for either player, so "
                   "there is nothing to look at, choose, recycle, or subsequently play.",
    "ogn-183-298": "Stacked Deck — [Action] \"Look at the top 3 cards of your Main Deck. Put "
                   "1 into your hand and recycle the rest.\" No Main Deck, so there is "
                   "nothing to look at, put into hand, or recycle.",
    "ogn-160-298": "Dazzling Aurora — Gear, \"At the end of your turn, reveal cards from the "
                   "top of your Main Deck until you reveal a unit. Play it... and recycle the "
                   "rest.\" Doubly dead: it fires AFTER the turn this engine searches ends "
                   "(same argument as Sona/Targon's Peak), and there is no Main Deck to reveal "
                   "from even if it fired mid-turn. Playing the Gear itself is fully generic "
                   "(no \"when you play this\" text, no activated ability).",
    "ogn-194-298": "Nocturne, Horrifying — [Ganking] (generic TRAIT_REGISTRY keyword) plus "
                   "\"When you look at cards from the top of your deck (and don't draw them) "
                   "and see me, you may play me for rainbow.\" No Main Deck, so a player never "
                   "looks at cards from the top of it — this alternate-play trigger can never "
                   "fire, regardless of whether any OTHER card's deck-look effect exists on "
                   "the board (they're all no-ops for the identical reason).",
    "ogn-200-298": "Twisted Fate, Gambler — mandatory \"when I attack, reveal the top rune of "
                   "your rune deck, then recycle it. Do one of the following based on its "
                   "domain...\" There is no Rune Deck in this model (state.RunePool holds the "
                   "runes a player channelled during the already-resolved Beginning Phase, not "
                   "a deck to reveal from — see state.ready_runes's docstring), so there is no "
                   "top rune to reveal and none of the three domain branches (including a Stun "
                   "branch — the parallel stun-mechanic work is not needed here) can ever "
                   "execute. Not registered in abilities.ATTACK_TRIGGERS: since the trigger "
                   "produces no observable effect under any domain, forcing the showdown "
                   "through the trigger-resolution machinery would change nothing, so leaving "
                   "her unregistered is exactly as correct as registering a no-op would be.",
    "ogn-242-298": "Baited Hook — Gear, whose entire text is one activated ability: \"Kill a "
                   "friendly unit. Look at the top 5 cards of your Main Deck. You may banish a "
                   "unit from among them... and play it... Then recycle the rest.\" Killing your "
                   "own unit is a real, strictly negative cost; the payoff is entirely a "
                   "Main-Deck look with no deck to look into. A solver would never activate it, "
                   "same reasoning as Garbage Grabber's activated Draw 1 — left unregistered "
                   "in gear.GEAR_ABILITIES, which is never offered as a legal action.",
    "ogn-101-298": "Mushroom Pouch — Gear, \"At the start of your Beginning Phase, if you "
                   "control a facedown card at a battlefield, draw 1.\" The Beginning Phase is "
                   "already resolved before the Action Phase this engine searches (same "
                   "pre-turn non-event as Sona/Loose Cannon), and the draw is a no-op regardless. "
                   "Playing the Gear itself is fully generic.",
    "ogn-118-298": "Wraith of Echoes — \"The first time a friendly unit dies each turn, draw "
                   "1.\" No-op regardless of the \"first time\" gating, since the draw itself "
                   "does nothing.",
    "ogn-182-298": "Scrapheap — Gear, \"When this is played, discarded, or killed, draw 1.\" "
                   "No-op regardless of which of the three triggers it, since the draw itself "
                   "does nothing.",
    "ogn-292-298": "The Dreaming Tree — Battlefield, \"When a player chooses a friendly unit "
                   "here with a spell for the first time each turn, they draw 1.\" No-op "
                   "regardless of the triggering spell; battlefields.py has no entry for this "
                   "effect_id, and an unregistered effect_id correctly grants nothing (see "
                   "battlefields._effect's None-returning default), so leaving it unregistered "
                   "is the right call, not a gap.",
    "ogn-201-298": "Invert Timelines — \"Each player discards their hand, then draws 4.\" The "
                   "draw is a no-op (no Main Deck), but discarding OUR OWN entire hand is a "
                   "real, strictly negative cost with no offsetting benefit — no card in the "
                   "pool reads hand size or rewards an empty hand. So this card is never a "
                   "necessary part of a winning line: any strategy that plays it is dominated "
                   "by the same strategy without it, same shape as Monastery of Hirana's "
                   "buff-for-nothing. (The OPPONENT's hand also empties and refills with 4 "
                   "no-op draws, which changes nothing either, per \"opponent never acts.\")",
    "ogn-044-298": "Clockwork Keeper — \"As you play me, you may pay a Calm rune as an "
                   "additional cost. If you do, draw 1.\" An optional extra rune payment for a "
                   "no-op payoff (no Main Deck) — a solver would never pay it, and declining "
                   "is always legal, same dominance shape as Monastery of Hirana.",
    "ogn-156-298": "Sabotage — \"Choose an opponent. They reveal their hand. Choose a "
                   "non-unit card from it, and recycle that card.\" \"Recycle\" means returning "
                   "the card to the (nonexistent) Main Deck — the same no-op zone transition as "
                   "every other \"recycle\" text in the pool — so the card leaves the opponent's "
                   "hand into nowhere tracked, unlike a real discard (contrast Mindsplitter, "
                   "which uses the word \"discard\" and IS modelled for real via "
                   "actions.discard_from_hand, precisely because a real discard can trigger an "
                   "enemy \"when you discard\" watcher and recycling cannot).",
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
