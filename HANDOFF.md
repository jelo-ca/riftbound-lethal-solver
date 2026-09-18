# Handoff — rb-puzzles solver

Paste the section below into a fresh session. Everything after it is
reference material that session can read on demand.

---

## THE PROMPT

You are continuing work on **rb-puzzles**, a Riftbound TCG lethal-solver
at `C:\Users\Jello\OneDrive\Desktop\Projects\rb-puzzles`.

**The MVP:** given any board of Origins cards, the engine either finds
lethal, proves there is none, or **names the cards it cannot reason
about**. Puzzle *generation* is explicitly deferred — do not work on it.

**Read first, in this order:** `HANDOFF.md` (this file, the sections
below), `solver/engine/coverage.py` (the safety mechanism and the whole
ledger), `findings.md` and `task_plan.md` (both gitignored, on disk).

**Current state:** branch `solver/coverage-ledger`, 36 commits ahead of
`solver/correct-card-data`. 618 tests pass in ~1s
(`py -m pytest solver/tests -q`). Coverage **115 of 298 cards (38.6%)**,
up from 90 this pass via four parallel clusters (play-restrictions,
conquer-triggers, buff-related, attack/defend-triggers), merged
sequentially with conflicts resolved by hand. One real regression was
caught at merge time, not shipped: Mageseeker Warden's old INERT
classification depended on Dune Drake staying BLOCKING, which the
attack-trigger cluster changed — reverted back to BLOCKING pending an
actual model of its "can't ready enemy units" restriction. Also picked
up two ledger-hygiene gaps (Yasuo Unforgiven, Vilemaw's Lair) that were
fully implemented and tested but missing their HANDLED entries.

**Your job:** raise coverage toward "any Origins board" without ever
letting the engine bluff. Work in card-shape clusters, not card by card.

**Non-negotiables** — these encode expensive lessons, do not relax them:

1. `coverage.py` defaults every unclassified card to **BLOCKING**. A card
   is only cleared by an explicit entry with a written reason. Never
   derive clearance from `CARD_POOL` membership.
2. **Never hand-write card stats.** Use `card_pool.card_def()`, which
   derives from `data/cards-ogn.json`. Hand transcription has produced
   every card-data bug this project has had, including one I made.
3. Comments explain **why**, never what. No `Co-Authored-By` or
   `Claude-Session` lines in commits.
4. Commit with an explicit pathspec — `git commit -m "..." -- <files>` —
   never a bare `git commit`. This is a shared checkout and a bare commit
   will sweep in another agent's staged work. It already happened once.
5. Leave `web/` alone. Another agent owns it.
6. The user has authoritative Riftbound rules knowledge. **Ask them**
   rather than researching or inferring. Batch questions where you can.
7. Explain each step and get a go-ahead before large changes.

---

## Position model (settled — do not re-litigate)

- **No Main Deck.** Position is hand + board. `draw` has nothing to draw.
- **Beginning Phase already resolved** ("ABCD done" — Awaken, Channel,
  Draw). The engine starts at the Action Phase with a fixed hand and
  fixed runes. This is what makes the question deterministic.
- **Hold is seeded**, never scored live. So "when you hold" triggers can
  never fire, which is why eight of them are classified inert.
- **The opponent never acts.** No opposing spell can exist to respond to.
- **Enemy-base movement is out of scope by decision** (2026-09-17).
  `Zone` is `"base"` or a battlefield id and cannot say *whose* base.
  Cards sending an ENEMY unit to its base stay BLOCKING. See
  `design/02-state-model.md`.

## Rules corrections that cost real time — do not undo

- **A rune pays Energy AND Power.** Exhaust for 1 Energy *and* Recycle
  for 1 Power of its domain, independently, either order. The repo
  previously recorded the opposite in four places, citing rule 164.2.b,
  and it roughly halved modelled resources. The card text settles it
  ("ready 4 friendly runes", "Recycle me to ready your runes", ~12 cards
  saying "channel 1 rune **exhausted**").
- **A buff is binary**, worth +1 Might, non-stacking. `UnitInstance.buffed`.
  Kept as state rather than folded into `might` because cards read it
  back. One printed exception exists: Lee Sin, Ascetic says "I can have
  any number of buffs" and stays blocked on it.
- **`[Tank]` and "assigned damage last"** are one mechanic — ordering
  constraints in `combat.assignable_targets`. Tank was registered as a
  known trait with two comments asserting it worked while `combat.py`
  never mentioned it.
- **No resolution stack is needed.** Of 21 Reaction cards, only three
  reference an unresolved spell (Defy, Wind Wall, Mystic Reversal) and
  all three are inert because the opponent never acts. For the other 18,
  "respond to my own spell" resolves in the same order as playing it
  first.

## The traps this codebase keeps falling into

Read these before trusting anything that looks finished.

1. **Two sources of truth for traits.** Fixed twice. `effective_might`
   once read `unit.keywords` directly, missing battlefield grants;
   `actions.effective_keywords` was a second, weaker resolver that missed
   auras and self-conditionals, so an earned `[Ganking]` couldn't
   actually move. Everything now goes through `traits.resolved_traits`.
   **Do not add a third path.**
2. **Registered but unimplemented.** Tank, and the whole Gear subsystem,
   both existed and did nothing. If you register a mechanic, ship a card
   that exercises it end to end, and test reachability through
   `search.legal_actions` — not just the registry.
3. **Guards get silently defanged.** A tripwire asserting "no Reaction
   card is in `CARD_POOL`" kept passing after cards started arriving via
   `card_def()`'s cache fallback instead. When you write a guard, check
   it still watches the thing that matters.
4. **Dead scaffolding.** `cards_played_this_turn` sat in state, in
   `canonical_key`, and in the export while nothing incremented it.
5. **Stale comments.** Several have asserted behaviour that was never
   implemented. Treat a comment as a claim to verify.

## Architecture in one pass

- `state.py` — `GameState`, `canonical_key`, `RunePool` (+ capacity
  helpers), `ready_runes`. Anything `canonical_key` treats as significant
  **must** also render in `export.py`, or two distinct positions collide.
- `traits.py` — `resolved_traits` (printed | battlefield | aura |
  self-conditional) and `effective_might`. **Non-circularity invariant:
  grants never read Might**, because Might is computed from the grants.
  Fiora stays unmodelled precisely because her condition reads Might.
- `combat.py` — damage assignment (lethal-first + Tank/last ordering),
  showdowns, `deal_damage_to_all_at`. Fires death triggers.
- `deaths.py` — `[Deathknell]`. Deferred imports, because `combat.py`
  imports it.
- `abilities.py` — spells, unit play triggers, activated abilities, plus
  shared operations: `apply_buff`, `spend_buff`, `grant_trait`,
  `ready_unit`, `_grant_might`, `_mutual_damage`.
- `gear.py` — Gear, wired into generation as of this session.
- `coverage.py` — **the safety mechanism.** `HANDLED` /
  `INERT_FOR_LETHAL` / `CONDITIONALLY_CLEARED` / everything else blocks.
- `lethal.py` — the MVP entry point. `find_lethal(board)` returns
  `lethal` / `no_lethal` / `unanswerable`, builds its own card table, and
  is falsy unless a real lethal was found.
- `search.py` — IDDFS. The transposition table records the **largest**
  budget a state was proven unwinnable with, since failing with more
  actions implies failing with fewer.

Registries today: 19 spells, 14 play triggers, 1 unit ability, 3 death
triggers, 4 gear abilities, 2 auras, 2 self-conditionals, 9 traits, 3
battlefield effects.

## What remains, by size

Run `scratchpad/concept_census.py` (recreate from `coverage.py` if gone)
for live numbers. Roughly:

| concept | cards | notes |
|---|---|---|
| deck / draw / discard | ~53 | mostly **inert** — no deck. Clear by argument, card by card |
| Reaction timing | ~60 | effects still need writing; the *timing* is done |
| buff-related | ~27 | mechanic exists; most are blocked on Gear/Legend/stacking |
| conquer triggers | ~21 | needs a conquer hook in `scoring.resolve_control_change` |
| Hidden zone | ~18 | probably **inert** — hiding costs a rune for no same-turn gain, and nothing rewards holding fewer runes (verified) |
| trash zone | ~13 | unmodelled zone |
| attack / defend triggers | ~13 | **blocked, see open questions** |
| play restrictions | ~12 | "opponents can't play cards" — moot, opponent never acts. Likely inert |
| channel runes | ~12 | no rune deck by decision; a channelled rune arrives exhausted with unknown domain |
| Legend zone | ~12 | `legends.py` exists, covers few abilities |

**Highest value first:** the deck cluster (~53 cards clearable by
*argument*, not code — cheapest coverage in the set), then Hidden and
play-restrictions on the same basis, then conquer triggers.

## Attack/defend trigger cluster — resolved 2026-09-17

Both blocking questions answered by the project owner and built:

1. **A defender killed by an attack trigger before the damage step is
   removed from combat entirely — it deals no combat damage.**
   `abilities.ATTACK_TRIGGERS` forces the move through the showdown
   mechanism with the trigger resolved before any damage-assignment
   option is computed, so a killed defender is simply absent from the
   live board by the time assignment happens. See
   `search._board_actions_with_showdown_entries` and
   `ShowdownState.attack_trigger_resolved`.
2. **`SelfConditional.condition` now takes a fourth `designation`
   argument** (the unit's combat role) for "while I'm attacking or
   defending alone" (Wielder of Water). Non-circularity holds — the
   condition reads only `designation`/board state, never `.might`.

Anivia, Yasuo Remorseful, Crackshot Corsair, Dune Drake, and Wielder of
Water are HANDLED. Volibear (damage-split composition), Ahri Inquisitive
(defend-half only reachable via Charm/Blitzcrank redirects), Leona
(needs a "stun" status decoupling lethal-Might from damage-dealt),
Warwick, Teemo, Twisted Fate, and Mask of Foresight (reacts to *any*
friendly unit's combat, not just its own) remain BLOCKING on real
subsystem gaps — not rules questions.

## Verification checklist for any change

```
py -m pytest solver/tests -q            # 559 pass, ~1.2s
py -m pytest solver/tests -m slow       # 3 generation tests, ~7min
for n in 001 002 003 004 005 006 007; do py -m solver.author_puzzle_$n; done
git diff --stat puzzles/                # expect NO change unless intended
```

If a puzzle's node or terminal count moves, you changed behaviour.
Find out why before committing. If you add a field to `UnitInstance` or
`PlayerState`, expect every export to churn — verify the diff is *only*
the new field plus hash renames.
