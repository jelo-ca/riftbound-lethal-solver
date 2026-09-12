# Generation Pipeline

Week 3's "sample → solve → filter" half of the original 6-week plan, picked up now that all 6 hand-authored puzzles have exercised the engine. Per the discussion that led here: generation samples **only from the already-verified card pool** below, not the full 298-card Origins set — an unregistered card's special text simply doesn't fire (no crash, no wrong answer, see `07-scope-and-cut-list.md`'s "add mechanics on demand" policy), so this is a safety choice about hit-rate, not correctness.

## Verified card pool

| Card | `riftbound_id` | Role | Mechanic |
|---|---|---|---|
| Legion Rearguard | `ogn-010-298` | Vanilla body, 2 Might | none |
| Faithful Manufactor | `ogn-211-298` | Vanilla body, 2 Might | none |
| Vanguard Captain | `ogn-218-298` | Vanilla body, 3 Might | none (Legion trigger not implemented) |
| Sneaky Deckhand | `ogn-176-298` | Open-battlefield deploy | `CardDef.can_play_to_open_battlefield` |
| Ride The Wind | `ogn-173-298` | Move + ready | `SPELL_EFFECTS` |
| Caitlyn - Patrolling | `ogn-068-298` | Exhaust-cost removal | `ABILITY_EFFECTS` |
| Blitzcrank - Impassive | `ogn-067-298` | Redirect an enemy unit | `UNIT_PLAY_TRIGGERS` |
| Yasuo - Windrider | `ogn-205-298` | Move-count point | `MOVE_COUNT_TRIGGERS` |

Sneaky Deckhand hasn't actually been used in a hand-authored puzzle yet — its mechanism is unit-tested directly (`test_actions.py`) but this pipeline would be its first real exercise. Worth watching for surprises the first time generation actually produces a candidate using it.

## Sampling

A random puzzle candidate is built from:
- **Battlefields**: always exactly `"left"`/`"right"`, no special effects (matches scope doc — battlefield effects stay out).
- **Starting score**: fixed at 6, not 7. At 7 only a single point is needed and the Final Point restriction (471.1.b — the point that reaches 8 needs both battlefields Conquered *this turn* if scored via Conquer) barely gets exercised. At 6 the position needs two points in the same turn, which is what actually forces a real line (matches puzzle 1's "One Point Short" shape: 6→7→8, both Conquers same turn) and pushes toward the plan's ≥4-5 action target instead of one-move positions.
- **`scored_this_turn`**: randomly 0 or 1 of `{"left", "right"}` (simulating a battlefield already Held this turn) — never both, since if both are already Scored there's no Final Point tension left to create.
- **Our units** (2-4): each drawn from the pool above with its real Might/keywords, placed at Base or a battlefield the position already has us controlling. Always `exhausted=False` — Awaken readies every unit at turn start (rule 315.4/431), and a puzzle's root position IS turn start, so there's no legitimate story for one of OUR pre-placed units already sitting exhausted before the puzzle's own first action (only a unit freshly PLAYED this turn starts exhausted, rule 143.4.a — that's a different unit and a different action, already modeled correctly by `apply_play_unit`). Raised from 1-3 to 2-4 so there's enough material to actually reach a 4+ action line (see minimum length below) — with too few units, positions run out of legal actions before getting there.
- **Opponent units** (0-2): generic stat-lines (Might 1-5, no keywords — the opponent's identity doesn't matter the way ours does), placed as defenders on whichever battlefield isn't already fully ours.
- **Hand** (0-2 cards): drawn from the spell/ability-bearing subset of the pool (Ride The Wind is the only hand-played one currently), with exactly enough runes sampled to afford whatever's dealt.

This is a deliberately small, hand-tunable parameter set (ranges as constants in `generate.py`), not a general position-sampling framework — matching the project's whole "keep scope small" posture.

## Filters

1. **Solvable**: `search.solve()` within a small `max_depth` (default 6, matching every hand-authored puzzle so far). Reject if `None`.
2. **Minimum length**: keep only strategies with at least `MIN_STRATEGY_SIZE = 4` states — matches the original plan's "≥4-5 actions" target. Hand-authored puzzles ran 1-3 actions, but that reflected what was manually built to prove out mechanics, not a target for generated puzzles; 3-or-fewer is rejected as too short.
3. **Solution count** (replaces the earlier greedy-heuristic proposal — see below): at the shortest winning depth `d*` found in step 1, count DISTINCT COMPLETE winning strategies from root within `d*` — not just root's first move. Branching anywhere along a line counts, since a puzzle with one forced opener that then splits into several correct follow-ups is still "easy" in the sense this filter cares about. At an adversarial (combat) node, a strategy fixes one continuation per possible opponent response, so the count contributed there is the product of each response's own continuation count (`search.count_winning_strategies`/`_count_solutions`). Keep only if the total is in `[1, 3]`. Reject if `0` (shouldn't happen, `d*` came from a real solve) or `>3` (too many ways to win = too easy). This single count does the job of both "is it trivial" and "is it (near-)unique" — no separate uniqueness pass needed.
4. **Size**: export the candidate and check the JSON byte size against a threshold (default 2MB, generous relative to every hand-authored puzzle's actual size so far). Reject if exceeded — per the original plan, this doubles as a puzzle-quality filter (a huge graph means the position was too loose).

Survivors still get hand-audited before publishing, same as the original plan always intended — this produces *candidates*, not content.

## Rejected approach: greedy heuristic

Earlier draft of this doc proposed a hand-scripted "greedy player" simulation as the difficulty filter ("obvious line fails"). Dropped in favor of the solution-count filter above: a no-backtrack greedy simulation that's allowed to backtrack becomes equivalent in power to the real solver (it would just find any reachable win via heuristic move-ordering), and a no-backtrack one requires hand-defining "obvious," a fuzzy judgment call with no principled stopping point. Solution-count is objective, reuses existing search code, and measures the thing we actually care about (how many correct answers exist) instead of a proxy for it.

## Open questions (deliberately deferred, revisit once real hit-rate data exists)

- Whether the sampling ranges above (unit counts, exhaustion weighting, hand size) need further tuning once the very first sampling runs show what they actually produce.
- Whether the adversarial product-counting rule (see filter 3) needs a cap once a puzzle actually has heavy combat branching — right now every puzzle in scope is small enough that this can't blow up.
