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
    "ogn-168-298": "Fight or Flight — [Hidden][Action] \"Move a unit from a battlefield to "
                   "its base.\" Same unrestricted \"a unit... to its base\" shape as Maddened "
                   "Marauder — unrepresentable whenever the target is the opponent's, since "
                   "Zone can't say whose base. [Hidden] doesn't change this: the card is "
                   "unmodelled regardless of how it would be played.",
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
    "ogn-224-298": "Salvage — [Action] \"You may kill a gear. Draw 1.\" via "
                   "abilities.SALVAGE/actions.kill_gear. \"A gear\" is unqualified — "
                   "either player's, same convention as Orb of Regret's unqualified "
                   "\"a unit\" (engine/gear.py's module docstring). Draw is a no-op, no "
                   "Main Deck. Optional, so declining is always legal. Every Gear is now "
                   "a legal target, Treasure Trove included (gear-cluster-2, this pass): "
                   "actions.kill_gear fires gear.fire_gear_leaves_board_reactions itself, "
                   "so its \"when this leaves the board\" reaction is no longer dropped.",
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
    # Same ledger-hygiene shape as Vilemaw's Lair above: both were already
    # implemented in battlefields.py and covered by test_battlefields.py
    # before this pass, just never entered here — so they read as BLOCKING
    # despite being correctly modelled.
    "ogn-297-298": "Windswept Hillock — \"Units here have [Ganking]\" via "
                   "battlefields.BattlefieldEffect(grants=frozenset({'Ganking'})), read "
                   "through traits.resolved_traits and reachable in move legality via "
                   "actions.effective_keywords — covered by test_battlefields.py",
    "ogn-294-298": "Trifarian War Camp — \"Units here have +1 Might. (This includes "
                   "attackers.)\" via battlefields.BattlefieldEffect(flat_might_bonus=1), "
                   "read through traits.effective_might for both combat roles AND plain "
                   "(non-combat) damage, unlike Assault/Shield's role-gated bonus — "
                   "covered by test_battlefields.py",
    # Back-Alley Bar — a genuine MOVE-COMPLETION trigger, not a static
    # positional bonus, so it doesn't fit battlefields.py's BattlefieldEffect
    # shape at all (that module's own docstring: TRIGGERS stay out of it).
    # Hooked into abilities.apply_move_triggers instead — the same choke
    # point every completed move (Standard Move, EnterShowdown, ResolveCombat,
    # and every ability/spell that relocates a unit: Ride The Wind, Charm,
    # Blitzcrank, Maddened Marauder) already routes through for Yasuo
    # Windrider's move-count trigger, so no new hook was needed, just a
    # second condition alongside the existing one.
    "ogn-277-298": "Back-Alley Bar — \"When a unit moves from here, give it +1 Might "
                   "this turn.\" via abilities.apply_move_triggers/_grant_might, keyed off "
                   "the battlefield's own effect_id read from the post-move state (effect_id "
                   "is fixed at position setup and never changes as units enter or leave, so "
                   "reading it after the move is exactly as correct as before). Printed text "
                   "names no controller (\"a unit,\" not \"a friendly unit\" — contrast Reaver's "
                   "Row/Fortified Position below), so it fires for either player's mover; "
                   "verified reachable through search.legal_actions via a plain Standard Move.",
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
    # Stun (RULES ANSWER, project owner, 2026-09-18): a stunned unit's
    # Might is ignored when summing its SIDE's damage-dealing pool for the
    # Combat Damage Step (combat.side_damage_pool) — it stays in combat,
    # stays targetable, and its own death threshold (traits.effective_might)
    # is untouched. UnitInstance.stunned, same non-stacking "rest of this
    # single-turn puzzle" shape as buffed.
    "ogn-238-298": "Leona, Determined — [Shield] via traits.TRAIT_REGISTRY; mandatory "
                   "\"when I attack, stun an enemy unit here\" via abilities.ATTACK_TRIGGERS "
                   "and abilities.stun_unit, same targeted-trigger shape as Yasuo Remorseful/"
                   "Crackshot Corsair, extended (abilities._leona_is_legal/_candidates) to "
                   "fold in Radiant Dawn's mandatory buff choice when that Legend is present "
                   "(no resolution stack, so the compound trigger's whole choice lives in one "
                   "trigger_params tuple — same shape as Kinkou Monk's two-target buff)",
    "ogn-238a-298": "Leona, Determined — same card as ogn-238-298, alternate art",
    # Radiant Dawn: a passive "when you stun" observer, wired via the
    # shared abilities._stun_buff_choice_active gate (checked by Legend
    # identity in abilities.STUN_OBSERVER_LEGENDS, not by which card did
    # the stunning) into EVERY registered stunner — both Leona (whose own
    # target is always an enemy by her own text) and Udyr, Wildman (whose
    # "stun A UNIT" is unrestricted-controller, so the gate additionally
    # checks the chosen target is actually an enemy before the buff choice
    # applies). The buff target is a real choice (unlike observers.py's
    # deterministic play-trigger watchers), so it can't use that module's
    # shape; it's folded into the stunning trigger/ability's own params
    # instead, verified reachable through search.legal_actions offering
    # the extended-params form for both stunners.
    "ogn-261-298": "Radiant Dawn — Legend, \"when you stun one or more enemy units, buff a "
                   "friendly unit\" via abilities._stun_buff_choice_active, wired into every "
                   "registered stunner (Leona, Udyr)",
    "ogn-306-298": "Radiant Dawn — same Legend, alternate printing",
    "ogn-306-star-298": "Radiant Dawn — same Legend, alternate printing",
    # Udyr, Wildman: "Spend my buff: Choose one you've not chosen this
    # turn — Deal 2 to a unit at a battlefield / Stun a unit at a
    # battlefield / Ready me / Give me [Ganking] this turn." All four
    # modes reuse existing primitives (combat.deal_damage_to_unit,
    # abilities.stun_unit, ready_unit, grant_trait); the one new piece is
    # UnitInstance.modes_chosen_this_turn, recording which of his own
    # modes have already been picked this turn so a re-buffed Udyr can't
    # repeat one. The Stun mode routes through the same
    # abilities._stun_buff_choice_active gate as Leona, so Radiant Dawn
    # observes a stun he causes too when the target is actually an enemy.
    "ogn-157-298": "Udyr, Wildman — abilities.ABILITY_EFFECTS[UDYR_WILDMAN]; \"spend my buff\" "
                   "cost via spend_buff, mode restriction via "
                   "UnitInstance.modes_chosen_this_turn",
    # Reaction-speed sweep (this pass). See abilities.py's "More [Reaction]
    # spells" section for the implementations.
    "ogn-033-298": "Shakedown — [Reaction] \"Choose an enemy unit. Deal 6 to it unless "
                   "its controller has you draw 2.\" The \"unless\" is the TARGET's "
                   "controller's choice — the opponent, who never acts — so the option "
                   "is never exercised and the primary effect (6 damage) is unconditional. "
                   "Implemented via abilities.SPELL_EFFECTS as plain flat damage to an "
                   "enemy unit at a battlefield.",
    "ogn-048-298": "Meditation — [Reaction] \"As an additional cost to play this, you may "
                   "exhaust a friendly unit. If you do, draw 2. Otherwise, draw 1.\" Both "
                   "draw amounts are no-ops (no Main Deck), but the optional cost is a "
                   "real, independent state change: gear.ARENA_BAR's ability requires an "
                   "EXHAUSTED friendly unit to target, so paying this cost on a unit that "
                   "doesn't need to act again this turn (a defender, say) can make it "
                   "eligible for Arena Bar's buff. Implemented via abilities.SPELL_EFFECTS "
                   "with the exhaust as an optional targeted param; declining it is always "
                   "legal.",
    "ogn-108-298": "Convergent Mutation — [Reaction] \"Choose a friendly unit. This turn, "
                   "increase its Might to the Might of another friendly unit.\" via "
                   "abilities.SPELL_EFFECTS, reading traits.effective_might for both units "
                   "and applying the delta only when the reference is actually higher — "
                   "\"increase\" has no effect when it isn't.",
    "ogn-127-298": "Cannon Barrage — [Reaction] \"Deal 2 to all enemy units in combat.\" "
                   "\"In combat\" is read as \"at the battlefield hosting the currently "
                   "open showdown\" (state.showdown) — the only place this engine's model "
                   "has two controllers' units present at once. Legal only while a "
                   "showdown is open; implemented via abilities.SPELL_EFFECTS.",
    # [Hidden] cluster. [Hidden] itself is established as never worth
    # using (see INERT_FOR_LETHAL's Pakaa Cub entry) — hiding spends a
    # rune now to save Energy later, strictly worse in a single turn. Each
    # card below ALSO carries an ordinary [Action] speed marker (or, for
    # Teemo/Pack of Wonders, has a trigger that fires the same whether or
    # not Hidden was ever used), so it can simply be cast/played/activated
    # normally at its printed cost — Hidden changes nothing about whether
    # the engine understands the effect, only about one (never-correct)
    # way to have paid for it.
    "ogn-057-298": "Block — [Hidden][Action] \"Give a unit [Shield 3] and [Tank] this turn.\" "
                   "via abilities.SPELL_EFFECTS and grant_trait, reusing TRAIT_REGISTRY's "
                   "generic numeric form the same way Cleave's [Assault 3] already does",
    "ogn-213-298": "Hidden Blade — [Hidden][Action] \"Kill a unit at a battlefield. Its "
                   "controller draws 2.\" via abilities.SPELL_EFFECTS and kill_unit; the draw "
                   "is a no-op",
    "ogn-197-298": "Teemo, Scout — [Hidden] mandatory \"when you play me, give me +3 Might "
                   "this turn.\" via abilities.UNIT_PLAY_TRIGGERS; the trigger fires on being "
                   "played at all, not specifically \"from Hidden,\" so it's a plain mandatory "
                   "self-buff (same shape as Trifarian Gloryseeker) regardless of Hidden",
    "ogn-197a-298": "Teemo, Scout — same card as ogn-197-298, alternate printing",
    "ogn-181-298": "Pack of Wonders — Gear, \"Exhaust: Return another friendly gear, unit, or "
                   "[Hidden] card to its owner's hand.\" via gear.GEAR_ABILITIES; the [Hidden] "
                   "half of the target set is always empty since Hidden isn't modelled as a "
                   "zone at all (design/00-overview.md), which is an empty candidate slice, "
                   "not unmodelled state being ignored — the gear/unit halves are fully "
                   "implemented for real, matching Zaunite Bouncer's/Arena Bar's bounce shapes",
    "ogn-167-298": "Ember Monk — \"when you play a card from [Hidden], give me +2 Might this "
                   "turn.\" There is no PlayFromHidden action anywhere in this engine's action "
                   "space at all — Hidden is not modelled as a zone (design/00-overview.md), so "
                   "no card is ever placed there and no such play can ever be generated. This "
                   "trigger is therefore dead by CONSTRUCTION, independent of whether hiding "
                   "would ever be strategically worth it — it doesn't reopen the \"[Hidden] is "
                   "never correct\" argument, because the premise (a from-Hidden play existing "
                   "at all) is already false regardless of strategy.",
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
    # Choice-bearing [Conquer] triggers — engine/conquer.py's
    # GameState.pending_conquer_choice fan-out (2026-09-18), generalizing
    # past the deterministic-only CONQUER_TRIGGERS/BATTLEFIELD_EFFECTS
    # shape. See conquer.py's module docstring for why the choice is
    # modelled as a pending marker + ResolveConquerTrigger action rather
    # than a list-returning resolve_control_change.
    "ogn-298-298": "Zaun Warrens — Battlefield, \"when you conquer here, discard 1, then "
                   "draw 1\" via conquer.BATTLEFIELD_CONQUER_TRIGGERS (the battlefield-keyed "
                   "grammar this cluster adds). The discard is a real choice/cost (which "
                   "hand card); \"then draw 1\" is a no-op, same no-Main-Deck reasoning as "
                   "every other draw effect above (e.g. Watchful Sentry). Mandatory, so "
                   "there is no decline candidate — an empty hand still resolves, as the "
                   "single no-op \"discard nothing\" candidate.",
    "ogn-276-298": "Aspirant's Climb — Battlefield, \"Increase the points needed to win "
                   "the game by 1.\" A genuine change to the win condition, not a "
                   "Might-shaped static bonus — scoring.victory_score(state) reads "
                   "board-conditionally off this effect_id and both scoring.is_winning "
                   "and resolve_conquer's rule 474/475 Final Point gate consult it live "
                   "instead of the bare VICTORY_SCORE constant, so a board carrying this "
                   "battlefield needs 9 points (and 8 is no longer the Final Point) rather "
                   "than 8. Verified end to end via search.solve() in test_scoring.py: a "
                   "board that's a winning Conquer at Victory Score 8 stops being "
                   "solvable at the same depth once this battlefield raises the target.",
    "ogn-287-298": "Sigil of the Storm — Battlefield, \"when you conquer here, recycle one "
                   "of your runes\" via conquer.BATTLEFIELD_CONQUER_TRIGGERS. Recycling pays "
                   "Power (rule 164.2.b) — there's no separate \"produce a floating Power\" "
                   "effect independent of paying for something (state.py's RunePool docstring) "
                   "— so this is a real, mandatory, strictly negative cost: it spends one "
                   "domain's Power capacity (chosen among domains still able to be Recycled; "
                   "the specific physical rune doesn't matter, since RunePool.power_spent only "
                   "ever records domains) for the rest of the turn, for no offsetting benefit. "
                   "Not a no-op like Zaun Warrens' \"then draw 1\" — the choice of WHICH domain "
                   "to spend is real and can matter to what's affordable afterwards. Fizzles "
                   "(no candidate but the empty one) once every real-domain rune is already "
                   "spent, same convention as Zaun Warrens against an empty hand.",
    "ogn-112-298": "Kai'Sa, Evolutionary — [Ganking] (plain trait, already handled) "
                   "\"when I conquer, you may play a spell from your trash with Energy "
                   "cost less than your points, without paying its Energy cost. Then "
                   "recycle it (must still pay Power cost)\" via "
                   "conquer.CONQUER_TRIGGERS_WITH_CHOICE and "
                   "abilities.kaisa_evolutionary_candidates/_effect — the "
                   "Soulgorger/Spectral Matron trash-replay pattern aimed at "
                   "SPELL_EFFECTS instead of a unit. Restricted to trash spells whose own "
                   "resolution is a single, deterministic outcome, same restriction and "
                   "same direction as SPELL_KILL_REACTIONS' Immortal Phoenix (no spell "
                   "registered today needs the missing case). \"Recycle it\" reads as "
                   "leaving trash for good (the nonexistent Main Deck), the same Vision/ "
                   "Ekko convention used throughout this ledger.",
    "ogn-112a-298": "Kai'Sa, Evolutionary — same card as ogn-112-298, alternate art",
    # "Channel N runes exhausted" (RULING 1, project owner, 2026-09-18): no
    # Rune Deck exists in this engine, so a channelled rune's domain is
    # unknowable — it contributes Energy capacity only, never Power, via
    # state.add_runes. "...exhausted" means it arrives with that Energy
    # already spent, so each of these is a real but narrow effect: nothing
    # observable happens unless something readies runes later the SAME
    # turn (Ekko, Recurrent's Deathknell is the only such effect that fires
    # mid-turn — Sona and Targon's Peak both ready at END of turn and stay
    # INERT_FOR_LETHAL below).
    "ogn-216-298": "Soaring Scout — [Deathknell] \"Channel 1 rune exhausted\" via "
                   "deaths.DEATH_TRIGGERS and state.add_runes",
    "ogn-137-298": "Stormclaw Ursine — [Tank] via traits.TRAIT_REGISTRY, mandatory "
                   "\"when you play me, channel 1 rune exhausted\" via "
                   "abilities.UNIT_PLAY_TRIGGERS and state.add_runes",
    "ogn-230-298": "Albus Ferros — \"when you play me, spend any number of buffs. For "
                   "each buff spent, channel 1 rune exhausted\" via "
                   "abilities.UNIT_PLAY_TRIGGERS, the same 2**N-subset candidate shape "
                   "as Overt Operation's spend-and-ready choice; \"any number\" includes "
                   "zero, so this is optional rather than mandatory",
    "ogn-249-298": "Relentless Storm — Legend, \"When you play a [Mighty] unit, you may "
                   "exhaust me to channel 1 rune exhausted\" via "
                   "legends.LEGEND_OBSERVER_PLAY_TRIGGERS (a new registry, keyed by the "
                   "WATCHING Legend rather than the played card — observers.py's "
                   "deterministic-only shape can't carry this card's \"you may\" choice). "
                   "\"Mighty\" is 5+ EFFECTIVE Might, read at the moment the unit lands. "
                   "The channelled rune is real but narrow (RULING 1: Energy-only, "
                   "arriving already-exhausted) — see test_channel_runes.py's Ekko "
                   "interaction test for the case where it actually matters.",
    "ogn-300-298": "Relentless Storm — same Legend as ogn-249-298, alternate printing",
    "ogn-300-star-298": "Relentless Storm — same Legend as ogn-249-298, alternate printing",
    # "Channel N runes exhausted. If you can't/couldn't, draw 1." — the
    # fallback branch is dead text in THIS engine specifically: there is no
    # Rune Deck modelled at all (RULING 1), so "channel N runes exhausted"
    # is never something the engine can fail to do (contrast "draw," which
    # fails because the deck is EMPTY, not absent as a concept). Always the
    # primary clause, via abilities.SPELL_EFFECTS and state.add_runes.
    "ogn-134-298": "Mobilize — \"Channel 1 rune exhausted. If you can't, draw 1.\" — "
                   "the draw branch is unreachable in this model, see the comment "
                   "above; always channels",
    "ogn-138-298": "Catalyst of Aeons — \"Channel 2 runes exhausted. If you couldn't "
                   "channel 2 runes this way, draw 1.\" — same reasoning as Mobilize",
    # The Seals — RULING 2 (project owner, 2026-09-18): "Add 1 [domain] rune"
    # STATES its own domain, so it's a normal, real-domain rune via
    # state.add_runes and gear.SEAL_DOMAINS — none of RULING 1's
    # domain-less machinery applies, and nothing says "exhausted," so it
    # arrives ready.
    "ogn-040-298": "Seal of Rage — Gear, \"Exhaust: Add 1 Fury rune\" via "
                   "gear.GEAR_ABILITIES and state.add_runes",
    "ogn-081-298": "Seal of Focus — Gear, \"Exhaust: Add 1 Calm rune\", same shape",
    "ogn-120-298": "Seal of Insight — Gear, \"Exhaust: Add 1 Mind rune\", same shape",
    "ogn-163-298": "Seal of Strength — Gear, \"Exhaust: Add 1 Body rune\", same shape",
    "ogn-204-298": "Seal of Discord — Gear, \"Exhaust: Add 1 Chaos rune\", same shape",
    "ogn-245-298": "Seal of Unity — Gear, \"Exhaust: Add 1 Order rune\", same shape",
    # Gear-cluster-2 (this pass). See gear.py/abilities.py/traits.py for the
    # per-card sections these entries point at.
    "ogn-063-298": "Spirit's Refuge — Gear, \"When you play this, buff a friendly unit.\" via "
                   "abilities.GEAR_PLAY_TRIGGERS (the second registrant after Forge of the "
                   "Future); \"Friendly buffed units have [Deflect] if they didn't already\" "
                   "via traits.GEAR_CONDITIONAL_GRANTS, a new Gear-sourced, position-unscoped "
                   "conditional trait grant (Gear never occupies a battlefield, so this can't "
                   "be a co-located AURA_SOURCES-style grant) — checked in "
                   "traits.resolved_traits for every friendly unit, base included, not just "
                   "whichever one the play trigger buffed.",
    "ogn-021-298": "Sun Disc — Gear, \"[Legion] Exhaust: The next unit you play this turn "
                   "enters ready.\" via gear.GEAR_ABILITIES. [Legion]'s gate lives in the "
                   "EFFECT (no effect at all if cards_played_this_turn is 0 when activated), "
                   "not in is_legal — same convention as Dangerous Duo/Trifarian Gloryseeker: "
                   "activating a Gear ability for nothing is a legal, merely bad, play. The "
                   ">0 threshold (not abilities.legion_condition_met's >1) is that helper's "
                   "own documented \"cost-time Legion\" case: Sun Disc's Exhaust is an "
                   "ACTIVATED ability, not itself a play, so it never bumps "
                   "cards_played_this_turn the way a played card counts its own play as one "
                   "of the two. The one-shot \"next unit enters ready\" is a new "
                   "PlayerState.next_unit_enters_ready flag, consumed by the very next "
                   "actions.apply_play_unit call for that player (any unit, accelerated or "
                   "not) regardless of whether it actually changed anything observable.",
    "ogn-143-298": "Pirate's Haven — Gear, \"When you ready a friendly unit, give it +1 "
                   "Might this turn.\" Hooked directly into abilities.ready_unit — the one "
                   "shared operation every registered readying effect already routes through "
                   "(First Mate, Wildclaw Shaman, Overt Operation, Udyr's Ready mode), so no "
                   "call site needed touching. Fires only on a REAL exhausted-to-ready "
                   "transition (ready_unit's own no-op guard), matching \"when you ready\" — "
                   "readying an already-ready unit is not a second readying.",
    "ogn-032-298": "Ravenborn Tome — Gear, \"Exhaust: The next spell you play this turn "
                   "deals 1 Bonus Damage. (Each instance of damage the spell deals is "
                   "increased by 1.)\" \"Bonus Damage\" (also printed on Void Gate, "
                   "ogn-296-298, a Battlefield outside this pass's scope — a parallel agent "
                   "was working Battlefield cards concurrently and may have built shared "
                   "infrastructure for it; this entry's PlayerState.next_spell_bonus_damage "
                   "is scoped narrowly to Ravenborn Tome's OWN one-shot \"next spell\" "
                   "reading and does not assume or depend on whatever Void Gate needed) reads "
                   "here as: a one-shot flag (gear.GEAR_ABILITIES' activation sets it), added "
                   "to EVERY damage instance the next PlaySpell's registered effect deals — "
                   "abilities._bonus_damage is read at each of the SPELL_EFFECTS damage call "
                   "sites that deal damage at all (_flat_damage_effect, _falling_star_effect, "
                   "_singularity_effect, _unchecked_power_effect, _flurry_effect, "
                   "_shakedown_effect, _cannon_barrage_effect, _get_excited_effect, and "
                   "_mutual_damage's Challenge caller only — Carnivorous Snapvine's own call "
                   "into _mutual_damage is a UNIT_PLAY_TRIGGERS effect, not a spell, and "
                   "passes no bonus), then unconditionally cleared once per spell play in "
                   "resolve_spell_outcomes (the single choke point both PlaySpell resolution "
                   "paths already share) — consumed by the next spell whether or not it dealt "
                   "any damage, matching \"the next spell you play\" rather than \"the next "
                   "damage spell.\"",
    "ogn-186-298": "Treasure Trove — Gear, \"When this leaves the board, draw 1 and channel "
                   "1 rune exhausted. [Chaos rune], Exhaust: Kill this.\" Re-investigated "
                   "this pass (previously excluded from Salvage's kill-target candidates as "
                   "an unbuilt reaction — see the Salvage entry above): the rune-channel "
                   "subsystem this needed already exists (state.add_runes), and "
                   "gear.fire_gear_leaves_board_reactions is the new missing hook, called "
                   "from actions.kill_gear AND this module's own Pack of Wonders bounce "
                   "effect (both are \"leaves the board\" — a kill and a bounce). Draw is a "
                   "no-op; the channel is real (RULING 1: domain-less, Energy-only, arrives "
                   "already-exhausted). Its own \"[Chaos rune], Exhaust: Kill this\" is a "
                   "plain gear.GEAR_ABILITIES entry that calls actions.kill_gear on itself, "
                   "which correctly fires its own leaves-board reaction in turn.",
}

# Investigated during the gear-cluster-2 pass (2026-09-18) and left
# BLOCKING, on purpose — not merely not-yet-done. Each is a real subsystem
# gap, not a rules question; per this ledger's own rule, a half-covered
# card stays blocking rather than being shipped partially.
#
# ogn-098-298 Energy Conduit — "Exhaust: [Reaction] Add 1 Energy.
# (Abilities that add resources can't be reacted to.)" The natural
# encoding — a domain-less rune via state.add_runes, arriving READY (the
# text says nothing about "exhausted") — is UNSOUND, not merely
# unbuilt: a rune is a standing object that persists and can be readied
# by any later-this-turn effect (Ekko, Recurrent's Deathknell; Overt
# Operation; Udyr's Ready mode), so modelling "Add 1 Energy" as a rune
# would let a single activation be milked for MULTIPLE Energy across a
# turn with enough readying on the board — a resource the card never
# promised. "Add 1 [domain] RUNE" (the Seals, RULING 2) explicitly says
# "rune" and is meant to persist; this card doesn't. A correct model
# needs a genuinely separate, non-rune, un-readyable Energy counter
# threaded through actions.generate_rune_payments/payment_is_affordable/
# consume_runes — the core payment engine every action in the game pays
# through — which is a materially larger change than one card justifies
# this pass. (A Legend with the identical printed text, Hand of Noxus,
# exists in data/cards-ogn.json but has no entry anywhere in this
# codebase — legends.py, coverage.py, or elsewhere — despite this task's
# briefing describing it as "already investigated in a prior pass." No
# such investigation is present to reuse; this reasoning was derived
# fresh and would apply identically to Hand of Noxus if it's picked up
# later.) Left BLOCKING.
#
# ogn-060-298 Mask of Foresight — "When a friendly unit attacks or
# defends alone, give it +1 Might this turn." Genuinely different from
# Wielder of Water's already-HANDLED "while I'm attacking/defending
# alone" (traits.SELF_CONDITIONALS): that's a unit reading its OWN
# combat role, resolved fresh every effective_might call with no state
# to maintain. This card reacts to ANY friendly unit's combat as an
# EVENT (a one-time Might grant at the moment combat starts, not a
# standing condition), from a Gear with no board position of its own —
# nothing in this engine currently observes "a combat just started" as
# an event a non-participant can react to. abilities.ATTACK_TRIGGERS
# comes closest (Anivia, Yasuo Remorseful, Leona) but is keyed to the
# ATTACKING unit's own registered trigger, forced through the showdown
# mechanism specifically because that unit's mandatory trigger can kill
# the defender before damage assignment — Mask of Foresight would need
# EVERY combat (registered trigger or not) to pause and check "does the
# combatant's controller hold a Mask of Foresight," a broader hook than
# anything built for attack/defend triggers so far. A parallel agent may
# be building defend-triggers for Battlefield cards concurrently; this
# call was made independently since no coordination channel exists —
# worth checking whether that work already generalized ATTACK_TRIGGERS
# into a real "combat started" observer before rebuilding one. Left
# BLOCKING.
#
# ogn-077-298 Zhonya's Hourglass — "[Hidden] The next time a friendly
# unit would die, kill this instead. Recall that unit exhausted." (Note:
# NOT "prevent it, gains [Temporary]" — verified against the exact
# printed text, which differs from an earlier paraphrase.) This is a
# death-REPLACEMENT effect: every unit-removal call site (combat.py's
# apply_combat/resolve_showdown/deal_damage_to_unit, actions.kill_unit)
# would need to check, BEFORE removing a unit, whether this pending
# effect is armed, and if so redirect the whole removal (kill Zhonya's
# Hourglass instead, send the WOULD-be-dead unit to base exhausted, no
# move) rather than removing it as a normal death. Every prior "reacts to
# a death" mechanism in this engine (deaths.DEATH_TRIGGERS, Vanguard
# Helm below) fires AFTER removal, reading a state the death already
# produced — this needs to intercept BEFORE removal happens at all,
# which is a new class of hook, not an extension of an existing one, and
# touches every one of those call sites individually since none of them
# currently pauses to ask permission before killing. Left BLOCKING.
#
# ogn-152-298 Mistfall — "When you buff a friendly unit, you may pay
# Body and exhaust this to ready it." abilities.apply_buff is a genuine
# single choke point (14 call sites route through it: SPELL_EFFECTS,
# UNIT_PLAY_TRIGGERS, CONQUER_TRIGGERS, ABILITY_EFFECTS, Gear abilities,
# Legend abilities, observers), so detecting "a buff just happened" is
# not itself the hard part. What's hard: the reaction is OPTIONAL and
# must be offered right at that moment, on that specific just-buffed
# unit — not "any time later this turn," which is what a stray
# persistent state marker would risk becoming if left un-cleared while
# other actions happen in between; and unlike Radiant Dawn's stun
# observer (abilities._stun_buff_choice_active, wired into exactly TWO
# registered stunners), Mistfall's trigger is UNRESTRICTED by source —
# every one of apply_buff's 14 callers would need its own candidate
# generator extended with an "and also spend Mistfall" dimension, or a
# new generic "pending reaction window" abstraction (comparable in size
# to ShowdownState.attack_trigger_resolved or PendingConquerChoice) built
# from scratch for a trigger with no adversarial timing question behind
# it. Building that machinery for one card was judged out of scope this
# pass. Left BLOCKING.
#
# ogn-227-298 Symbol of the Solari — "If a combat where you are the
# attacker ends in a tie, recall ALL units instead. (Send them to base.
# Ties are calculated after combat damage is dealt.)" Tie DETECTION is
# genuinely small — combat.py's damage-assignment path already computes
# each side's resulting Might/damage, so "did both sides end this combat
# dead (or otherwise account for a tie by the rules' own definition)" is
# a cheap read after the fact. RECALL-INSTEAD-OF-DEATH is not: it is a
# full alternate resolution branch for the Combat Damage Step — instead
# of applying lethal damage and removing units normally, every unit in
# that combat (both sides, not just the loser) needs to be redirected to
# base, undoing whatever apply_combat/resolve_showdown already did or
# intercepting before it happens. This is real new combat surface, not a
# small addition bolted onto the existing damage-assignment path — being
# honest about the size rather than forcing a partial fit. Left BLOCKING.
#
# ogn-228-298 Vanguard Helm — "When a buffed friendly unit dies, buff
# another friendly unit." Needs BOTH an observer hook (reacts to ANY
# buffed unit dying, not just a card watching its own death) AND a
# choice (which OTHER friendly unit to buff). The conquer-trigger choice
# fan-out (conquer.py's PendingConquerChoice/ResolveConquerTrigger,
# generalizing past deterministic-only CONQUER_TRIGGERS) is a real
# candidate template for "a choice-bearing reaction to an event" and IS
# more tractable now than before that infrastructure existed — but
# conquer.py's pending-choice field is keyed to ONE specific event
# grammar (a control change at a named battlefield) and deliberately
# supports only one pending choice at a time; adapting the same SHAPE
# for "a unit died" would mean building an analogous
# PendingDeathReactionChoice hooked into deaths.fire_death_triggers (the
# unit-removal choke point, parallel to conquer's resolve_control_change)
# rather than reusing conquer.py's own field, since a board could
# plausibly need both a pending conquer choice and a pending death-
# reaction choice from unrelated events. That is a new, adjacent
# instance of the pattern, not literally hooking into existing conquer
# machinery — still a meaningful chunk of new state-machine surface for
# one card. Left BLOCKING with this updated note (previously blocking for
# "no template exists"; now blocking for "the template exists but still
# needs a parallel instance built, which this pass judged out of scope").

# Investigated alongside the choice-bearing [Conquer] cluster above and
# left BLOCKING, on purpose — not merely not-yet-done:
#
# ogn-252-298 Super Mega Death Rocket! — "Deal 5 to a unit. When you
# conquer, you may discard 1 to return this from your trash to your
# hand." Its conquer trigger is NOT this card conquering (it's a Spell,
# never a unit that could stand at a battlefield) and NOT a specific
# battlefield being conquered (its text names no battlefield) — it
# watches "you, the controller, conquered ANYTHING, from wherever this
# happens to be sitting," a THIRD event grammar neither
# CONQUER_TRIGGERS_WITH_CHOICE (unit-keyed) nor BATTLEFIELD_CONQUER_
# TRIGGERS (battlefield-keyed) can express — closer in shape to
# deaths.units_killed_between/SPELL_KILL_REACTIONS' "watch a generic
# event from trash" than to anything in conquer.py. Building that third
# grammar for one card was judged out of scope for this pass (per the
# task's own call: force a fit only if it's clean). Left blocking whole
# — even though "deal 5 to a unit" alone would be a trivial addition to
# the existing flat-damage-spell shape (Hextech Ray/Falling Comet), a
# half-read card is exactly as dangerous as an unread one.
#
# ogn-269-298/ogn-310-298/ogn-310-star-298 The Boss — "When a buffed unit
# you control would die, you may pay [rainbow] and exhaust me to spend
# its buff and recall it exhausted instead (send it to base; not a
# move). When you conquer, ready me." The conquer half is trivial (a
# deterministic CONQUER_TRIGGERS entry, no choice needed) and would have
# been free to add via this cluster's machinery. Left blocking anyway:
# the OTHER clause is a death-REPLACEMENT effect ("would die... instead")
# — a mechanism (interrupting removal before it happens, not reacting
# after) that doesn't exist anywhere in this engine and is explicitly out
# of scope for this pass. Per coverage.py's own rule, a half-covered card
# stays BLOCKING; clearing just the conquer clause here would be exactly
# the kind of partial-credit claim this ledger exists to prevent.
#
# DEFEND-TRIGGER CLUSTER (2026-09-18) — Fortified Position (ogn-279-298)
# and Reaver's Row (ogn-285-298) investigated together, left BLOCKING:
#
# ogn-279-298 Fortified Position — "When you defend here, choose a unit.
# It gains [Shield 2] this combat." ogn-285-298 Reaver's Row — "When you
# defend here, you may move a friendly unit here to base." Both need a
# "when you defend here" hook that doesn't exist: abilities.ATTACK_TRIGGERS
# is the only combat-timing trigger machinery built so far, and it only
# ever handles OUR OWN mandatory choice, because in every attack this
# engine can generate, the mover (and so the attacker) is always
# state.turn_player — the opponent never acts, so it never initiates a
# Standard Move. A DEFEND trigger inverts that: combat.determine_sides
# assigns the DEFENDER role to whoever DIDN'T move, which in the
# overwhelmingly common case (we attack into an enemy-held battlefield) is
# the OPPONENT, not us. So "choose a unit" / "you may move a friendly unit
# to base" would be the OPPONENT's choice in the case that actually comes
# up whenever we attack a Fortified Position/Reaver's Row the enemy holds
# — and an opponent choice has to be searched ADVERSARIALLY (an AND-branch
# over every candidate, the solver must still win regardless of which one
# they'd pick), the opposite of every choice-bearing mechanism built so
# far (ATTACK_TRIGGERS, CONQUER_TRIGGERS_WITH_CHOICE,
# BATTLEFIELD_CONQUER_TRIGGERS all resolve OUR OWN choice via an OR-branch,
# reusing search._dfs's ordinary loop). Reaver's Row is worse still: "you
# may move a friendly unit here to base" lets the DEFENDING player pull
# their own unit out of the fight entirely — a real, adversarial
# retreat/rescue option the solver would need to prove a lethal survives
# either way.
#
# A second, narrower path exists where WE'D be the defender instead:
# Blitzcrank's "move an enemy unit to here" (and Charm's redirect) can
# make an ENEMY unit the mover, flipping combat.determine_sides so OUR
# units become the defenders — reachable, and there the choice genuinely
# would be ours (OR-branch, same shape as every other trigger here). But
# Blitzcrank/Charm bypass ShowdownState entirely
# (combat.enumerate_combat_outcomes resolves atomically, with no "open
# showdown, then trigger" window the way open_showdown/ResolveShowdown
# gives ATTACK_TRIGGERS) — so even the reachable half would need its own
# hook, separate from whatever handles the common enemy-defends case.
# Building only the Blitzcrank-reachable half while leaving the far more
# frequent "we attack an enemy holding this battlefield" case unhandled
# would silently under-count the enemy's toughness in the common case —
# exactly the half-covered-card risk this ledger exists to catch. A full,
# correct defend-trigger subsystem needs BOTH an adversarial-choice
# AND-branch (new — nothing in search.py does this today, closer in shape
# to combat.enumerate_assignments' opponent-response enumeration than to
# any existing trigger registry) and a second hook for the atomic
# Blitzcrank/Charm path. That is a larger, differently-shaped subsystem
# than ATTACK_TRIGGERS, not a comparable extension of it, so both cards
# stay BLOCKING rather than risk an incorrect or one-sided partial model.
#
# ogn-296-298 Void Gate — "Spells and abilities affecting units here each
# deal 1 Bonus Damage. (Each instance of damage the spell deals is
# increased by 1.)" A genuinely new damage-modifier concept: "Bonus
# Damage" appears on exactly one OTHER card in the whole pool
# (ogn-032-298 Ravenborn Tome, a Gear: "Exhaust: The next spell you play
# this turn deals 1 Bonus Damage," same reminder text) and nowhere else —
# so this isn't Void Gate's own one-off text, it's a shared mechanic
# neither card currently has anywhere to plug into. Doing it correctly
# means adding +1 to EVERY damage INSTANCE a spell/ability deals to a unit
# standing at the affected battlefield — not a flat total, per the
# reminder text ("each instance"), so a card like Falling Star (two
# separate 3-damage instances) or Singularity (up to two units) would need
# the bonus applied per-instance, per-target, which means threading a
# "how much Bonus Damage applies here" parameter through every
# damage-dealing call site combat.py and abilities.py have (flat-damage
# spells, ATTACK_TRIGGERS' damage effects, deal_damage_to_all_at, on top
# of Void Gate's own positional gate) rather than adding one line to a
# single function. Scoped as a real, moderate-sized cross-cutting change,
# not a small hack — left BLOCKING with this writeup rather than force a
# partial version that only covers some damage sources. Worth revisiting
# together with Ravenborn Tome in a future pass, since building the
# concept once would clear both.


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
    "ogn-182-298": "Scrapheap — Gear, \"when this is played, discarded, or killed, "
                   "draw 1.\" All three triggers are the same no-op draw; found while "
                   "wiring kill-gear (checking what Gear reacts to its own death) but "
                   "inert regardless of whether anything can ever kill it.",
    "ogn-072-298": "Solari Shrine — Gear, \"when you kill a stunned enemy unit, you "
                   "may exhaust this to draw 1.\" Optional, and the payoff is the "
                   "same no-op draw whether or not [Stun] (unmodelled) ever fires — "
                   "inert regardless of the Stun subsystem's status.",
    "ogn-101-298": "Mushroom Pouch — Gear, \"AT THE START OF YOUR BEGINNING PHASE, "
                   "if you control a facedown card at a battlefield, draw 1.\" Same "
                   "pre-turn non-event as Dr. Mundo/Loose Cannon's Beginning Phase "
                   "triggers (already resolved before the Action Phase this engine "
                   "searches), and the draw would be a no-op regardless.",
    "ogn-180-298": "Fading Memories — Spell, \"Give a unit at a battlefield or a gear "
                   "[Temporary].\" [Temporary] kills its target at the start of the "
                   "controller's NEXT Beginning Phase, which a single-turn puzzle "
                   "never reaches (Sprite's precedent above) — true regardless of "
                   "which legal target is chosen, including a gear, so the whole "
                   "card is inert without needing the kill-gear mechanism at all.",
    "ogn-135-298": "Pakaa Cub — [Hidden] and nothing else. Hiding spends a rune "
                   "now to play for 0 Energy later; inside one turn that is "
                   "strictly worse than playing the card, and no Origins card "
                   "rewards holding fewer runes (verified across the set), so "
                   "hiding is never correct.",
    "ogn-278-298": "Bandle Tree — Battlefield, \"You may hide an additional card here.\" "
                   "Raises how many cards you're ALLOWED to pay Hidden's cost for at this "
                   "battlefield — it doesn't change what hiding buys (Pakaa Cub's argument "
                   "above: strictly worse than playing the card this turn, and nothing in "
                   "the pool rewards holding fewer runes), so permitting a SECOND "
                   "never-correct action is still never correct. Optional (\"you may\"), so "
                   "declining is always legal regardless.",
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
    "ogn-290-298": "The Arena's Greatest — Battlefield, \"At the start of each player's "
                   "first Beginning Phase, that player gains 1 point.\" Unlike Loose "
                   "Cannon's no-op draw, this genuinely grants something — but \"each "
                   "player's FIRST Beginning Phase\" happens at most once per player in "
                   "the whole game, and the position model's Beginning Phase is already "
                   "resolved before the Action Phase this engine searches (HANDOFF.md). "
                   "So either this is that player's first turn and the point was already "
                   "granted during the already-resolved Beginning Phase — meaning it's "
                   "already reflected in the starting PlayerState.score the puzzle hands "
                   "this engine, same as any other pre-turn effect — or it isn't their "
                   "first turn, in which case the trigger fired (or didn't) on an earlier "
                   "turn entirely outside this single-turn search and cannot fire again. "
                   "Either way, nothing observable can happen to score DURING the turn "
                   "being searched — this is a fact about it having already happened (or "
                   "already being permanently spent), not a no-op payload.",
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
    "ogn-007a-298": "Fury Rune — same as ogn-007-298, alternate printing",
    "ogn-042a-298": "Calm Rune — same as ogn-042-298, alternate printing",
    "ogn-089a-298": "Mind Rune — same as ogn-089-298, alternate printing",
    "ogn-126a-298": "Body Rune — same as ogn-126-298, alternate printing",
    "ogn-166a-298": "Chaos Rune — same as ogn-166-298, alternate printing",
    "ogn-214a-298": "Order Rune — same as ogn-214-298, alternate printing",
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
    "ogn-293-298": "The Grand Plaza — hold trigger only. Note this is an ALTERNATE "
                   "WIN CONDITION (\"if you have 7+ units here, you win the game\"); "
                   "it is inert only because the trigger cannot fire, so if Hold ever "
                   "becomes a live event this entry must be revisited first.",
    "ogn-288-298": "Startipped Peak — \"When you hold here, you may channel 1 rune "
                   "exhausted.\" Hold trigger only, same as the other battlefields "
                   "above — no Hold occurs during the turn being searched. (Its "
                   "\"channel 1 rune exhausted\" payload never matters here, since "
                   "the trigger that would fire it can't fire at all.)",
    # Beginning-Phase-only triggers, same non-event as Loose Cannon above.
    "ogn-284-298": "Obelisk of Power — \"At the start of each player's first "
                   "Beginning Phase, that player channels 1 rune.\" The Beginning "
                   "Phase is already resolved before the Action Phase this engine "
                   "searches, so this fires (if ever) before the position the "
                   "engine is asked about even exists.",
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
    # ogn-266-298 Siphon Power stays BLOCKING — not a rules question, a
    # card-data one. "Choose a battlefield. Give friendly units there +1
    # Might this turn and enemy units there -1 Might this turn, to a
    # minimum of 1 Might" would be a straightforward SPELL_EFFECTS entry
    # (Grand Strategem's target-free +Might plus Smoke Screen's floored
    # debuff, applied per-unit at one battlefield) — but its printed cost
    # carries a Power icon of 1 across TWO domains (Mind and Order), and
    # card_data.build_card_def refuses that as ambiguous by design (its own
    # module docstring: "two domains plus a Power cost, where which domain
    # pays is genuinely ambiguous" — 10 printings share this, ogn-266-298
    # among them). card_pool.card_def("ogn-266-298") is None. Non-negotiable
    # #2 forbids hand-writing a CardDef to route around that refusal, so
    # there is no CardDef to build a legal PlaySpell action against even if
    # the effect were written. Left BLOCKING with no coverage entry.
    #
    # ogn-241-298 Shen, Kinkou stays BLOCKING too, for a different reason.
    # Her printed text is [Shield 2] and [Tank] only — both already-generic
    # keywords with other HANDLED cards exercising them — but she is a
    # [Reaction]-speed UNIT, and her printed reminder text is the tell:
    # "Play any time, even before spells and abilities resolve, INCLUDING TO
    # A BATTLEFIELD YOU CONTROL" (every other [Reaction] card in the pool
    # carries the plain reminder with no such clause). That's the game
    # telling us a Reaction-speed Unit can reinforce an ONGOING fight, not
    # just enter at the normal Action-Phase window a Slow unit is confined
    # to. Investigated whether that's already reachable:
    #   - At board level she's already fully playable via the ordinary
    #     PlayUnit path (actions.is_legal_play_unit never checks
    #     card.speed at all) — same as any Slow unit, to base or a
    #     battlefield we control. That part needs no fix.
    #   - DURING an open showdown, though, search._showdown_actions
    #     generates ONLY PlaySpell candidates (via _playable_spells) plus
    #     ResolveShowdown — there is no PlayUnit path in there for ANY
    #     unit, [Reaction]-speed or not. Confirmed by reading, not
    #     assumed: no isinstance(action, PlayUnit) branch is reachable
    #     while state.showdown is not None.
    #   - Scoped a minimal fix (generate legal PlayUnit for [Reaction]
    #     units the same way _playable_spells does for spells) and found
    #     it isn't actually minimal: actions.apply_play_unit's battlefield-
    #     controller assignment (`new_controller = bf.controller if
    #     bf.controller is not None else player_index`) can't tell "open
    #     battlefield" (bf.controller is None, bf.units EMPTY — rule
    #     466.7.b, establishing control is correct) apart from "Contested
    #     mid-showdown battlefield" (bf.controller is None, bf.units
    #     NON-empty and mixed-controller — must stay Contested). Playing a
    #     reinforcement into the open showdown's own battlefield would hit
    #     the second case and get the first case's behavior: it would
    #     immediately assign the battlefield to state.turn_player, and
    #     scoring.resolve_control_change would read that as a genuine
    #     control change and fire resolve_conquer/conquer.
    #     fire_conquer_triggers — a Conquer point granted mid-combat,
    #     before the Combat Damage Step has even happened. That's scoring/
    #     conquer surface, which this pass was told to leave to the
    #     parallel conquer.py agent, and not a change to make under time
    #     pressure regardless. (combat.deal_damage_to_unit's OWN
    #     controller fallback doesn't have this bug — for a genuinely
    #     mixed-controller `remaining`, `len(controllers) == 1` is False
    #     and it already falls through to None correctly; this is
    #     specific to apply_play_unit's open-vs-Contested conflation.)
    # Per this ledger's own rule ("a half-covered card stays BLOCKING"),
    # a card whose full printed capability isn't reachable stays blocking
    # even though a large majority of her text has somewhere to go. Left
    # undone rather than shipped partially or risked against code another
    # agent owns in parallel.
    #
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
    "ogn-144-298": "Spoils of War — [Reaction] \"If an enemy unit has died this turn, "
                   "this costs 2 Energy less. Draw 2.\" The draw is a no-op with no Main "
                   "Deck regardless of what it cost to get there — a cheaper price on "
                   "nothing is still nothing, so the cost-reduction condition can never "
                   "matter for lethal either.",
    "ogn-145-298": "Unyielding Spirit — [Reaction] \"Prevent all spell and ability damage "
                   "this turn.\" The opponent never acts, so every spell/ability damage "
                   "source this prevention could ever apply to is OUR OWN — there is no "
                   "opposing damage to defend against. Casting it can only suppress "
                   "damage a solver chose to deal in the first place, which is strictly "
                   "worse than simply not dealing that damage (same final board, minus "
                   "the Energy/Body Power this costs) — including the one interaction "
                   "worth naming: preventing a kill would also stop it from being a kill, "
                   "which would deny Immortal Phoenix's spell-kill reaction (ogn-037-298) "
                   "its trigger rather than help it. Any winning line that casts this can "
                   "drop the cast (and whichever of its own spells it was shielding "
                   "against) and still win, so it cannot change whether lethal exists.",
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
    # ogn-101-298 Mushroom Pouch and ogn-182-298 Scrapheap already cleared
    # above (Gear-removal cluster's sweep) — same cards, found independently.
    "ogn-118-298": "Wraith of Echoes — \"The first time a friendly unit dies each turn, draw "
                   "1.\" No-op regardless of the \"first time\" gating, since the draw itself "
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
    "ogn-174-298": ("Sai Scout — [Vision] dead without Karma; \"you may play me to an open "
                    "battlefield\" via CardDef.can_play_to_open_battlefield (auto-derived from "
                    "the printed text, same generic mechanism as Sneaky Deckhand)",
                    _vision_inert_unless_karma),
    # Gemcraft Seer's printed text is "[Vision]... Other friendly units
    # have [Vision]" (verified against the cache directly — an earlier
    # scoping pass for this sweep described the aura as granting [Shield],
    # which the actual printing does not say). Vision is never a coded
    # mechanic in this engine either way (nothing reads the keyword for
    # combat/movement), so the aura granting it to other units collapses
    # into exactly the same "no Main Deck, unless Karma" question as her
    # own copy — no separate aura wiring needed, unlike Taric/Captain
    # Farron's genuinely combat-relevant [Shield]/[Assault] auras.
    "ogn-100-298": ("Gemcraft Seer — [Vision] (own copy, dead without Karma) plus \"other "
                    "friendly units have [Vision]\" — an aura granting the SAME "
                    "provably-inert-unless-Karma keyword, not a combat-relevant trait, so "
                    "the whole card reduces to the one condition",
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
    both hands, both players' Gear, battlefield effects, and Legends. A
    card only has to be PRESENT to matter — an unmodelled enemy unit
    standing on a battlefield changes combat just as much as one we could
    play, and the same is true of a pre-placed Gear: nothing requires it
    to have arrived via a scanned hand first. Found missing while wiring
    the kill-gear mechanism (2026-09-18) — a board seeded with an
    unclassified Gear directly in PlayerState.gear, never touching a hand,
    was silently invisible to blocking_cards() and would have bluffed."""
    found: set[str] = set()
    for player in state.players:
        found.update(u.card_id for u in player.base_units)
        found.update(player.hand)
        found.update(g.card_id for g in player.gear)
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
