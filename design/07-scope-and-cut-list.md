# Scope and Cut List (v0)

The explicit boundary of what this solver implements. Every mechanic on the OUT list is a deliberate cut, not an oversight — re-adding one is a scope change that needs its own review pass, not a silent addition during coding.

## IN

- Origins (`OGN`) set only, and within it, only a hand-picked **whitelist** of ~15-30 cards chosen to support the first ~6 puzzles (Week 3 of the existing 6-week plan). Not full-set coverage. First-pass whitelist (~14 cards) and the 6 puzzle concepts it's derived from: [`08-puzzle-concepts.md`](08-puzzle-concepts.md).
- 2 battlefields, no special battlefield effects in v0 puzzles (no "Aspirant's Climb"-style score modifiers).
- Opponent tapped out — no defender-choice branching beyond required combat resolution.
- Full information, no randomness, no hidden zones.
- Action types: `PlayUnit`, `MoveUnit` (+ auto-resolved combat), `PlaySpell`, `PlayGear`.
- Scoring paths: Conquer, Hold, and at most one card-effect scoring path if a chosen puzzle needs it.
- Card effects that generate/add runes mid-turn (e.g. "when you play me, add a rune") — in scope, handled generically since the effect just mutates `RunePool` on the child state like any other field; no special solver logic required (see `02-state-model.md`). Still needs per-card review during whitelisting: untapped vs. exhausted, and domain.
- Keywords: whichever minimal set the whitelist actually needs, added one at a time as puzzles are authored — not a general keyword engine.

## OUT (this project, not just "later")

- Legend/champion activated abilities, except a hand-picked whitelist entry if a specific puzzle needs one.
- Multi-set interactions (Origins only, permanently, per the existing plan's policy posture).
- General keyword rules coverage — keywords are added to the engine on demand per puzzle, never speculatively.
- RiftScribe integration — Riftcodex is sufficient and verified live; RiftScribe stays an unwired fallback.
- **General adversarial/minimax opponent** (turn-taking, spell-casting, blocking decisions) — still out of scope. What *is* now implemented (`09-combat-resolution.md`) is a narrow, localized exception: the opponent's damage-assignment choice during combat is adversarial (an AND-node), since it's a mandatory rules procedure the opponent must go through even while otherwise tapped out — not a general opponent AI.
- **Resolved (2026-09-12):** "when you play me" triggers that move an *enemy* unit onto ground we hold (Blitzcrank), causing combat where we're the Defender, are now implemented via `abilities.UNIT_PLAY_TRIGGERS` — a generic, reusable "when played" registry (`PlayUnit.trigger_params`), not a one-off for this single card. `combat.py`'s "we are Defender" logic (written generically since the design pass) is now reachable through real action generation, proven by tests using the actual Blitzcrank wiring rather than a synthetic construction. Unblocks puzzle 6 ("Redirection"). `PlaySpell`-triggered enemy-unit moves (e.g. Charm) still aren't wired — same registry pattern would apply whenever a puzzle needs one.

## Resolved (2026-09-11, verified against the official Core Rules PDF)

All five items originally listed here as open are now resolved by pulling and grepping the actual Core Rules PDF (`https://cmsassets.rgpub.io/sanity/files/dsfx7636/news_live/e9ac8e3d33e0f78cef296f5945aba7bc1313b086.pdf`, ~43MB, extracted via `pdftotext`). Two of the five overturned what blog sources had said:

1. **Base vs. battlefield deployment** (rule 355.7/355.8) — units can be played to Base **or** directly to a battlefield the controller already controls. They enter exhausted (rule 143.4.a). `02-state-model.md` and `03-action-space.md` updated.
2. **Rune channeling** (rule 315.4/431) — mandatory automatic step, 2 runes off the top of the Rune Deck, no domain choice. **Not a chosen action**, and moot anyway for single-turn puzzles (starting rune pool is fixed at puzzle authoring time). `ChannelRune` removed from `03-action-space.md`.
3. **Dual-cost rune payment (correction)** — a rune produces Energy (Exhaust) **or** Power of its own domain (Recycle), never both (rule 164.2.b). The blog source claiming "same rune pays both" was wrong. `RunePool` and the action space's `rune_payment` field updated to reflect this.
4. **`scored_this_turn` semantics (correction)** — tracks *Scored* (Conquer or Hold), not Conquer alone (rule 471.1.b, 472-476). Two blog sources both said "must Conquer every battlefield," which is stricter than the actual rule — Holding one and Conquering the other satisfies the Final Point condition. `02-state-model.md` and `04-scoring-rules.md` updated.
5. **Marked damage / turn-boundary cleanup timing** — not fully chased down (lower stakes given the single-turn puzzle horizon and tapped-out assumption); noted as a minor remaining item in `04-scoring-rules.md`.

**Single-turn puzzle horizon** (confirmed by the user, consistent with the existing 6-week plan's "fixed starting position with a fixed energy budget"): removes Channel Phase, Awaken/rune-recovery, and Hold-as-a-live-action from the search entirely — see `02-state-model.md`.

## Resolved (2026-09-12, per direct rules clarification)

6. **Does Ganking's Battlefield→Battlefield restriction apply to spell-granted "Move" effects?** No — confirmed. Ganking's restriction (rule 810) is specific to a unit's own Standard Move. Spell-granted "Move" effects (Ride The Wind, Charm) default to moving a unit to any zone, including Battlefield→Battlefield, with no Ganking requirement — a spell states explicitly when it's narrower (e.g. Fight or Flight: "Move a unit from a battlefield to its base," restricted to that one direction). Implemented as `is_legal_ability_move_destination` in `actions.py`, separate from `is_legal_destination` (which still gates the unit's own Standard Move on Ganking).

## New open item (2026-09-12, flagged for whenever combat resolution gets built)

7. **"When I attack" / "when I defend" triggered-ability ordering.** Not yet relevant — combat resolution isn't implemented (puzzles 5 "Clear the Way" and 6 "Redirection" need it, `design/03-action-space.md`'s combat section). Flagging now so it isn't rediscovered late: when combat resolution is actually built, the order these triggers fire in relative to each other and to damage assignment needs to be nailed down explicitly, not assumed. Revisit `05-dfs-solver.md`'s damage-assignment-branching notes at that point.

## Review checkpoints

This whole `design/` set is meant to be reviewed before any `solver/engine/` code is written. Suggested order: `00` → `04` (rules-correctness track, since a wrong scoring module invalidates every puzzle) → `05` (solver mechanics) → `01`/`02`/`03`/`06` (plumbing). Flag disagreements per-doc; the open questions above are the known gaps, not the only things worth pushback on.
