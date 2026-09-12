# Puzzle Concepts (v0 sketch)

Six rough puzzle concepts, sourced from a live scan of the real Origins card pool (2026-09-11, all 298 base cards pulled via Riftcodex, `set_id=OGN`). Purpose: bound the whitelist and keyword set before hand-authoring starts (Week 3), not to lock exact numbers/positions yet — those get finalized during actual authoring.

Each concept names real cards with their `riftbound_id`. All obey the corrected rules from `04-scoring-rules.md`.

## 1. "One Point Short" — the flagship, teaches the core trap

Player at 7 points, controls neither battlefield at turn start (so `scored_this_turn` starts empty — no Hold fired this Beginning Phase). Obvious line: throw your best unit at the juicier battlefield, Conquer it, expect to win. **It doesn't** — you've Scored only one battlefield this turn, so the Final Point converts to a card draw (rule 474-476). Real solution: Conquer **both** battlefields this turn using two cheaper, separate actions instead of one big flashy one.

Candidate pieces: **Sneaky Deckhand** (`ogn-176-298`, 3E, "You may play me to an open battlefield") to take one battlefield directly without the two-step Base→Move dance, plus a unit already on board and readied (from the puzzle's starting position) to Conquer the other.

## 2. "Borrowed Time" — validates the Hold-or-Conquer correction

Player at 7, already holds battlefield A (Scored via Hold this Beginning Phase — baked into the starting position's `scored_this_turn`). Only battlefield B needs a Conquer to win. This is the exact case that would have been wrongly rejected as unsolvable if the model had kept the "must Conquer both" misreading from the blog sources — a single Conquer on B wins immediately since the Final Point condition is Scored-both, not Conquered-both.

Good early regression-style puzzle: cheap to author, directly exercises the correction, and should land well with a rules-literate Discord audience (per the existing plan's launch strategy).

## 3. "The Long Way Around" — a card-effect point sidesteps the restriction entirely

**Yasuo - Windrider** (`ogn-205-298`, 5E, [Ganking] — can move battlefield-to-battlefield): *"The third time I move in a turn, you score 1 point."* That's a card-effect point (rule 473 — exempt from the Conquer restriction). **Correction:** moving exhausts a unit (rule 145.1) — Ganking only removes the Battlefield→Battlefield destination restriction, it doesn't make moves free. So 3 moves in a turn isn't just "shuttle back and forth"; it needs 2 additional ready effects between moves (e.g. Ride The Wind, First Mate) to actually get 3 moves out of one turn. That makes this a genuinely harder puzzle than first sketched — good, since it also doubles as a second demonstration of concept 4's "extra action" trick, applied to a different payoff. Teaches: not every point needs Conquer or Hold — direct effects bypass the trap mechanic entirely.

## 4. "Extra Innings" — the hidden extra action

Setup: at 7, need both battlefields, have just enough Might/units to take both — except the needed second unit is already exhausted from an earlier necessary play (units enter exhausted, rule 143.4.a, so it looks one action short). Solution unlocks the "extra" action via **Ride The Wind** (`ogn-173-298`, 2E spell: "Move a friendly unit and ready it") or **First Mate** (`ogn-132-298`, 3E: "When you play me, ready another unit"). Classic "you had one more move than it looked like" lethal-puzzle shape.

## 5. "Clear the Way" — removal enables the conquer, exercises damage-assignment

Battlefield B is held by a defender tough enough that a naive attack doesn't take it this turn cleanly (Tank/Shield keyword, or just too much Might). Solution uses removal *before* moving in: **Caitlyn - Patrolling**'s exhaust ability (`ogn-068-298`: "Deal damage equal to my Might to a unit at a battlefield") or **Kog'Maw - Caustic**'s Deathknell (`ogn-190-298`: "Deal 4 to all units at my battlefield" on death). First puzzle to actually exercise the damage-assignment branch point flagged in `05-dfs-solver.md`.

## 6. "Redirection" — misdirect the blocker instead of fighting it

Opponent has one unit, currently defending battlefield A. You want both battlefields, but their one blocker can only be in one place — attacking it head-on is the trap. **Blitzcrank - Impassive** (`ogn-067-298`, 5E, [Tank]: "When you play me to a battlefield, you may move an enemy unit to here") pulls their blocker onto whichever battlefield Blitzcrank lands on, leaving the other open for a free Conquer. Teaches: reposition the problem rather than fight through it.

## Derived whitelist (first pass, ~14 cards)

| Card | `riftbound_id` | Role |
|---|---|---|
| Sneaky Deckhand | `ogn-176-298` | Direct-to-open-battlefield deploy |
| Yasuo - Windrider | `ogn-205-298` | Ganking + move-count card-effect point |
| First Mate | `ogn-132-298` | Ready another unit (extra-action enabler) |
| Ride The Wind | `ogn-173-298` | Move + ready a friendly unit (extra-action enabler) |
| Caitlyn - Patrolling | `ogn-068-298` | Exhaust-ability removal |
| Kog'Maw - Caustic | `ogn-190-298` | Deathknell AOE removal |
| Blitzcrank - Impassive | `ogn-067-298` | Forced enemy relocation |
| Vanguard Captain | `ogn-218-298` | Legion token generation (filler/blocker fodder) |
| Faithful Manufactor | `ogn-211-298` | Cheap token generation (filler) |
| Legion Rearguard | `ogn-010-298` | Cheap generic Conqueror body |
| Charm | `ogn-043-298` | Cheap enemy-unit reposition |
| Showstopper | `ogn-270-298` | Base→battlefield move + buff, cheap enabler |
| Cull the Weak | `ogn-209-298` | Cheap removal (both players kill a unit — needs opponent to have exactly one unit for determinism) |
| Super Mega Death Rocket! | `ogn-252-298` | Bigger single-target removal |

**Keywords needed:** Ganking, Tank, Shield, Legion, Deathknell, Assault (minor, might modifier only). All of these come with inline reminder text in `text.plain` (e.g. `[Tank] (I must be assigned combat damage first.)`) — the Riftcodex data makes the reminder text available directly, so hand-authoring these doesn't require a separate keyword rules lookup beyond confirming the reminder text is complete and accurate. Worth noting in `01-data-sources.md`.

**Explicitly not used:** any Legend/champion activated ability, any named-battlefield scoring effect (e.g. `The Grand Plaza`'s "7+ units here wins outright", `Aspirant's Climb`'s raised victory score) — confirms the `07-scope-and-cut-list.md` OUT list is achievable with real, interesting cards; v0 doesn't need battlefield effects to make good puzzles.

## Open items before hand-authoring (Week 3)

- Exact starting Might/board state per puzzle — not fixed here, this is a concept sketch only.
- Cull the Weak's "each player kills one of their units" requires the opponent to have exactly one unit for the puzzle to stay deterministic (full-information assumption) — flag this constraint when authoring puzzle 5's exact position if this card is used there.
- Confirm Ganking's exact wording doesn't require paying an additional cost per move beyond the unit's own actions (re-read `Windswept Hillock`/Yasuo text once authoring starts).

## Mechanics considered and rejected

**"Pull the opponent onto a battlefield you'll purposely lose, then reconquer it for an extra point."** Does not work — rule 471.1.b: *"A player may only Score, from either method, once per Battlefield per turn."* The cap is keyed to (player, battlefield, turn), not to control state. Losing and retaking the same battlefield in one turn Scores it exactly once, whichever Conquer/Hold happened first; the reconquer is a no-op for points, and it also doesn't re-trigger "when I conquer" abilities on that battlefield (rule 471.2.b, same once-per-turn cap). This includes the Hold+Conquer variant: holding a battlefield at the Beginning Phase and then Conquering the *same* battlefield later that turn is still only 1 point, not 2 — "from either method" means Hold and Conquer share one quota, not separate ones.

Do not author a puzzle around this premise — it would be rules-incorrect and exactly the kind of thing that gets a puzzle site dismantled in Discord (per the existing plan's stated failure mode). The legitimate version of "relocate the opponent's blocker" is concept 6: use it to clear contest off a *different* battlefield, not to double-score the same one.
