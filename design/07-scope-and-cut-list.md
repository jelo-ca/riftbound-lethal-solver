# Scope and Cut List (v0)

The explicit boundary of what this solver implements. Every mechanic on the OUT list is a deliberate cut, not an oversight — re-adding one is a scope change that needs its own review pass, not a silent addition during coding.

## IN

- Origins (`OGN`) set only, and within it, only a hand-picked **whitelist** of ~15-30 cards chosen to support the first ~6 puzzles (Week 3 of the existing 6-week plan). Not full-set coverage.
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

## Open questions — verify before Week 1 code freezes the state model

Source for all of these: official Core Rules PDF, linked via `playriftbound.com/en-us/rules-hub/` (direct asset link in [`01-data-sources.md`](01-data-sources.md) history — too large to fetch and summarize in this session, ~10MB+). Do not lock these from blog paraphrases.

1. **Base vs. battlefield deployment** — do units enter play at a base zone and then move to a battlefield, or can `PlayUnit` target a battlefield directly? Affects `02-state-model.md`'s `PlayerState.base_units` field and `03-action-space.md`'s `PlayUnit` legality.
2. **Rune channeling** — is gaining runes each turn a mandatory automatic step, or a chosen action with a domain decision? Affects whether `ChannelRune` belongs in the action space at all.
3. **Dual-cost rune payment** — can one physical rune satisfy both a card's Energy and Power cost in the same payment, or must they draw from separate runes? Affects `RunePool` legality-check logic for `PlayUnit`/`PlaySpell`/`PlayGear`.
4. **`scored_this_turn` reset timing** — confirmed it resets each turn, not confirmed exactly when (start of the turn player's turn vs. end of previous turn — likely equivalent but worth confirming there's no edge case at the turn boundary).
5. **Marked damage cleanup timing** — when does damage on units clear, if at all under the tapped-out assumption? Affects whether `UnitInstance.damage` needs to persist state across turns.

**Resolved with confidence** (two independent sources agreeing, see [`04-scoring-rules.md`](04-scoring-rules.md)): 2 battlefields, Conquer/Hold/card-effect scoring paths, and the last-point restriction applying only to Conquer.

## Review checkpoints

This whole `design/` set is meant to be reviewed before any `solver/engine/` code is written. Suggested order: `00` → `04` (rules-correctness track, since a wrong scoring module invalidates every puzzle) → `05` (solver mechanics) → `01`/`02`/`03`/`06` (plumbing). Flag disagreements per-doc; the open questions above are the known gaps, not the only things worth pushback on.
