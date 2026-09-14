# Scoring Rules

This module gates everything downstream. Per the existing 6-week plan's kill criteria: if this isn't passing tests by end of Week 2, the project pivots. Write it with unit tests before any search code exists.

## Confirmed rules (2026-09-11, verified against the official Core Rules PDF)

PDF: `https://cmsassets.rgpub.io/sanity/files/dsfx7636/news_live/e9ac8e3d33e0f78cef296f5945aba7bc1313b086.pdf` (via playriftbound.com/en-us/rules-hub/, last updated 2026-07-16). Rule numbers below are cited from that document (extracted via `pdftotext`, grepped by section).

- **2 battlefields per game.** Win at 8 points (1v1) — Victory Score, rule 198.1.
- **Scoring (rule 469.1/471):** a player Scores a battlefield in one of two ways — **Conquer** (gain Control of a battlefield not yet Scored this turn) or **Hold** (maintain Control of a battlefield not yet Scored this turn, checked during the Beginning Phase). **A battlefield can only be Scored once per player per turn, by either method** (rule 471.1.b) — Conquer and Hold both feed the *same* `scored_this_turn` tracking, they are not separate counters.
- **Card-effect points:** some effects grant points directly, bypassing the battlefield system entirely (rule 473).
- **Last-point restriction (rule 472-476, the trap mechanic this whole project is built around):** when a Conquer would gain a point while the player's total is 1 point from Victory Score or higher: **if the player has Scored every battlefield this turn, they gain the Final Point; otherwise they draw a card instead.**
  - **Correction from the initial design pass:** the condition is "Scored every battlefield" (Conquer *or* Hold), not "Conquered every battlefield." Two blog sources both said Conquer specifically — that's stricter than the actual rule. Concretely: Holding one battlefield this turn and Conquering the other satisfies the condition; you don't need to Conquer both.
- **This restriction applies only to points gained through Conquer** (rule 473: "points Gained from sources that are not Conquer are not beholden to these restrictions"). Hold and card-effect points at 8 win instantly, no additional condition.
- **Single-turn puzzle scope (per `02-state-model.md`):** Hold is checked during the Beginning Phase, before the puzzle's live turn starts — so any Hold-driven entries in `scored_this_turn` (and any resulting score) are part of the puzzle's starting position, not a live search outcome. Only Conquer and card-effect scoring are things the solver's action sequence can produce.

## Still open (lower stakes — didn't chase further this pass)

1. Exact instant `scored_this_turn` is considered "for this turn" relative to cleanup boundaries — doesn't matter for a single-turn puzzle (there's no next turn to reset into), but worth a sanity check when writing the scoring test suite.
2. Marked-damage cleanup timing — when/whether damage clears. Minor for v0 given the tapped-out assumption and single-turn horizon; revisit only if a whitelisted puzzle card cares.

## Decision flow

```mermaid
flowchart TD
    A[Action resolves] --> B{Conquer or\ncard effect?}
    B -->|Conquer, battlefield not\nyet Scored this turn| C[Mark battlefield in\nscored_this_turn]
    B -->|Card effect| E[Gain 1 pt, no restriction]
    C --> F{Current score >= 7?\nrule 474/475: "1 point from\nVictory Score or higher"}
    F -->|no| Z[Gain 1 pt, continue]
    F -->|yes, this is the\nFinal Point attempt| G{scored_this_turn ==\nall battlefields?}
    G -->|yes| WIN[Gain Final Point — Win]
    G -->|no| DRAW[No point — draw a card instead]
    E --> H{New total >= Victory Score\nand highest?}
    H -->|yes| WIN2[Win]
    H -->|no| Z2[Continue]

    S[Start of turn\npre-resolved, not searched] -.-> D[Hold: for each battlefield\ncontrolled + not yet Scored\nthis turn, gain 1 pt, mark Scored]
    D -.-> A
```

Hold is drawn dashed/pre-resolved: it seeds the puzzle's starting `scored_this_turn` and score, it isn't an action the solver's search takes.

Source: [`diagrams/04-scoring-flow.mmd`](diagrams/04-scoring-flow.mmd)

## The Hold invariant (constraint on every starting position)

Because Hold is pre-resolved into the starting position, a well-formed position must satisfy:

> **Every battlefield the turn player controls is already in `scored_this_turn`.**

It follows from the rules above rather than adding to them. There are only two ways to be standing on a battlefield mid-turn — held since the start of the turn (Hold scored it in the Beginning Phase) or taken during this turn (Conquer scored it) — and rule 471.1.b caps it at one point per battlefield per player per turn. So control implies spent.

The invariant is **one-directional**. `scored_this_turn` may legitimately name battlefields the turn player does *not* control: one Conquered earlier this turn and since lost stays Scored (puzzle 4 is built on that shape), as does one merely Held at turn start and subsequently taken by the opponent.

**Why it's enforced rather than documented.** Without it, a position admits a *revolving door*: move your last unit off a battlefield you control (rule 468 makes it Uncontrolled), move another unit back in, and the None→you transition reads as a fresh Conquer worth a point — repeatable, on ground you never lost. `resolve_conquer` always refused this when `scored_this_turn` was seeded correctly, but nothing checked the seeding, so it was reachable from any position that forgot it. Both the generator (which sampled `scored_this_turn` as a coin flip, unconnected to the board) and two hand-authored puzzles produced it; puzzles 7 and 8 were built entirely on the door and were withdrawn.

It is now checked in `scoring.unseeded_holds` and enforced at `export_puzzle`, the single gate every puzzle passes through — hand-authored or generated — rather than left to each author script's discretion.

## Test suite plan (Week 1 gate, per existing 6-week plan)

Rules are now sourced from the official Core Rules PDF (rule numbers cited above), not blog paraphrase — safe to write the real test suite against these. Categories:
- Conquer to exactly 8 with `scored_this_turn` already covering the *other* battlefield via **Hold** (not Conquer) this turn → win. This is the case that would have been missed entirely if the model had kept the "must Conquer both" assumption from the blog sources.
- Conquer to exactly 8 with `scored_this_turn` covering both battlefields via Conquer → win.
- Conquer to exactly 8 with neither/only-this battlefield in `scored_this_turn` → no point, draw a card instead, score stays at 7.
- Card effect to exactly 8 → win, no restriction, regardless of `scored_this_turn` state.
- A battlefield already in `scored_this_turn` cannot be Scored again this turn by either method (rule 471.1.b) — Conquering or Holding it a second time in the same turn is a no-op for scoring purposes.
- RiftJudge rulings (if any exist for edge cases beyond what the core rules text covers) — check separately, not sourced in this pass.
