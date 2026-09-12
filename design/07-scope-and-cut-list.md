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
- Damage-assignment complexity beyond single-blocker combat, until a whitelisted card actually forces the issue.
- General keyword rules coverage — keywords are added to the engine on demand per puzzle, never speculatively.
- RiftScribe integration — Riftcodex is sufficient and verified live; RiftScribe stays an unwired fallback.
- Adversarial/minimax opponent — the state model leaves room for it (per the existing plan's architecture note) but v0 does not implement it.

## Resolved (2026-09-11, verified against the official Core Rules PDF)

All five items originally listed here as open are now resolved by pulling and grepping the actual Core Rules PDF (`https://cmsassets.rgpub.io/sanity/files/dsfx7636/news_live/e9ac8e3d33e0f78cef296f5945aba7bc1313b086.pdf`, ~43MB, extracted via `pdftotext`). Two of the five overturned what blog sources had said:

1. **Base vs. battlefield deployment** (rule 355.7/355.8) — units can be played to Base **or** directly to a battlefield the controller already controls. They enter exhausted (rule 143.4.a). `02-state-model.md` and `03-action-space.md` updated.
2. **Rune channeling** (rule 315.4/431) — mandatory automatic step, 2 runes off the top of the Rune Deck, no domain choice. **Not a chosen action**, and moot anyway for single-turn puzzles (starting rune pool is fixed at puzzle authoring time). `ChannelRune` removed from `03-action-space.md`.
3. **Dual-cost rune payment (correction)** — a rune produces Energy (Exhaust) **or** Power of its own domain (Recycle), never both (rule 164.2.b). The blog source claiming "same rune pays both" was wrong. `RunePool` and the action space's `rune_payment` field updated to reflect this.
4. **`scored_this_turn` semantics (correction)** — tracks *Scored* (Conquer or Hold), not Conquer alone (rule 471.1.b, 472-476). Two blog sources both said "must Conquer every battlefield," which is stricter than the actual rule — Holding one and Conquering the other satisfies the Final Point condition. `02-state-model.md` and `04-scoring-rules.md` updated.
5. **Marked damage / turn-boundary cleanup timing** — not fully chased down (lower stakes given the single-turn puzzle horizon and tapped-out assumption); noted as a minor remaining item in `04-scoring-rules.md`.

**Single-turn puzzle horizon** (confirmed by the user, consistent with the existing 6-week plan's "fixed starting position with a fixed energy budget"): removes Channel Phase, Awaken/rune-recovery, and Hold-as-a-live-action from the search entirely — see `02-state-model.md`.

## Review checkpoints

This whole `design/` set is meant to be reviewed before any `solver/engine/` code is written. Suggested order: `00` → `04` (rules-correctness track, since a wrong scoring module invalidates every puzzle) → `05` (solver mechanics) → `01`/`02`/`03`/`06` (plumbing). Flag disagreements per-doc; the open questions above are the known gaps, not the only things worth pushback on.
