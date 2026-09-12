# Riftbound Lethal Puzzle Project — Build Plan

**One-line description:** A Python rules engine and iterative-deepening DFS solver for Riftbound "find the winning line" puzzles. The solver precomputes each puzzle's full reachable state graph; a TypeScript front end walks that graph so players get real interactivity with zero rules logic in the browser.

**Timeline:** 6 weeks. Riot US SWE internship applications open in September and close end of October.

---

## Why this project

Riftbound's win condition is unusually puzzle-friendly. The 8th point cannot come from a single conquer unless you scored every battlefield that turn, so the obvious aggressivelets rena line often fails and the solution is a hold setup or a card effect instead. That is a built-in trap mechanic. The community already uses the term "lethal range" for scoring enough points in one turn, so the concept needs no explanation.

Nothing like this exists. Every other Riftbound tool niche (deck builders, card scanners, collection trackers, rules bots, daily card-guessing games) is already crowded.

---

## Core architecture decision: precomputed state graph

**Rules are implemented once, in Python. The browser never resolves rules.**

From a fixed starting position with a fixed energy budget, the set of reachable states is finite and small. Enumerate it once at authoring time, dedupe on canonical state hash, and ship it as static JSON: a DAG where each node is a state and each edge is a legal action with its resulting state.

The TS layer is a graph walker. Player clicks an action → follow the edge → render the new node.

**What this buys:**

| | |
|---|---|
| One rules implementation | No drift between two engines — the failure mode that silently produces wrong answers |
| Illegal moves impossible by construction | They aren't edges. Legal-action highlighting is free; undo is walking back up the graph |
| Strong policy posture | The browser does table lookup on precomputed data, not rules resolution |
| Python for the solver | Right language for search work |

**Graph size is the thing to watch.** At branching ~8-15 and depth 12, naive enumeration blows up. Mitigations:
- Aggressive state-hash dedup (most action orderings converge to the same state)
- Cap depth at solution length + 2-3
- Prune branches that have spent their energy with no path to lethal

If a puzzle's graph exceeds a few MB, it's too loose to be a good puzzle. **Size doubles as a quality filter.**

### Repo shape

```
solver/          Python — rules model, IDDFS, puzzle generation
  engine/        state, actions, scoring
  search.py      iterative-deepening DFS
  generate.py    sample → solve → filter
  export.py      position → reachable state DAG → JSON
puzzles/         generated JSON, one per puzzle
web/             TS — graph walker + board rendering, zero rules logic
```

---

## Hard constraints

### Policy

Riot's Riftbound digital tools policy names only two approved use cases: deck builders and card libraries, and states specific concern about projects enabling gameplay with automated rules, interactions, and resolutions.

**Be clear-eyed:** the puzzle-vs-play distinction does not hold mechanically. An engine that takes player actions and resolves them to determine a win is what the policy language describes; single-player and a fixed starting position are not carve-outs in the text.

**The defensible argument:** Possibility Storm has run MTG puzzles for years under Wizards' fan policy. Rift Atlas has a solo goldfish mode and is thriving unenforced. Authored puzzle content is transformative in the sense Riot's own monetization clause uses. This is a bet, not a reckless one.

**Build it to survive being wrong:**

1. **Static-first, interactive as a flag.** Build the static reveal version first and get it working. Add the interactive board on top, behind a feature flag. If a policy email ever arrives, flip the flag and the site degrades to static instead of going dark. Build the fallback even if it's never used.
2. **Stay clearly inside puzzle territory.** No deck import. No free board construction. No multiplayer. No matchmaking. No ranked ladder or Elo (named separately in the policy). Fixed authored positions only.
3. **Describe it accurately everywhere** — a puzzle and teaching tool, never a simulator.
4. **Register the app with Riot.** Send the scoping question in week 0 (does a puzzle with a precomputed state graph and no live rules resolution fall inside the policy?) and record the date sent. Being on record asking is worth a lot. Do not block on the answer — API key approvals have run 45 days to 6+ months for other developers.
5. **Address it in the writeup.** This is what converts risk into signal: you read the policy, here's where the project sits relative to it, here's the static fallback built for that reason. A reviewer respects a candidate who found the line and reasoned about it far more than one who never noticed it.

Required notice on the site and in the README:

> [Title] was created under Riot Games' "Legal Jibber Jabber" policy using assets owned by Riot Games. Riot Games does not endorse or sponsor this project.

### Simplifying assumptions

- **Opponent is tapped out.** No showdown reactions. Makes the search single-agent rather than adversarial — the difference between six weeks and six months.
- **Origins set only.** No cross-set interactions, no cards not hand-audited.
- **Full information.** Board state entirely visible, no deck randomness.

What the tapped-out assumption does *not* remove: combat still resolves (defenders deal damage), battlefield effects still apply to both players, and defender triggered abilities still fire.

**Architecture note:** build the engine so an opponent-response layer could slot in later. That turns the search into minimax rather than plain DFS, and you don't want to rewrite the core to get there.

### Data sources

Card data from Riftcodex or RiftScribe (community open APIs). Do not depend on the official Riot API — approval timelines make it unusable for a 6-week window.

---

## Engine design

### State model

```python
GameState:
  battlefields: [Battlefield, Battlefield]
    - units present (with controller)
    - controller
    - battlefield effect
  base: units per player
  units: might, keywords, ready/exhausted
  hand: cards
  resources: runes available, energy
  scores: [int, int]
  scored_this_turn: set[battlefield_id]   # CRITICAL
```

`scored_this_turn` is what makes the last-point rule work and is the field a naive model forgets.

Needs a **canonical hash** for dedup — order-independent over units within a zone, so equivalent states collapse.

### Action space

- Play a unit
- Move a readied unit to a battlefield (triggers showdown, auto-resolves under the tapped-out assumption)
- Play a spell or gear
- Activate legend ability
- Channel runes

### Scoring module

Write this as its own module with unit tests **before** writing any search. Source edge cases from RiftJudge rulings and the official core rules:

- Conquer at 7 points without having scored every battlefield that turn → draw a card instead of scoring
- Hold scores at the start of your turn
- Card effects can deliver the final point without restriction
- Some battlefields (e.g. Aspirant's Climb) raise the victory score

If this module is wrong, every puzzle published is wrong.

### Solver

Iterative-deepening DFS. Run depth 1, then 2, then 3, up to a depth cap.

- **Not BFS** — at branching factor ~8-15 and depth up to 12, the BFS frontier gets large. IDDFS uses depth-proportional memory and finds shortest solutions first, which is what "wins in the fewest actions" needs.
- Transposition table on canonical state hash
- Prune on remaining energy, on whether any unit can still reach a battlefield, and on dominance between equivalent states
- **Watch damage assignment.** Choice in combat damage assignment is the one place branching can blow up. Handle it deliberately.
- **Output the full winning line, not a boolean.** Needed for the solution reveal.

### Exporter

`export.py` takes a verified position and emits the reachable state DAG:

```json
{
  "puzzle_id": "...",
  "root": "state_hash",
  "solution": ["action_id", "..."],
  "nodes": { "state_hash": { /* renderable state */ } },
  "edges": { "state_hash": [ { "action": {...}, "to": "state_hash" } ] },
  "terminal": { "state_hash": "win" | "dead_end" }
}
```

Includes `dead_end` labels so the front end can tell a player they've reached an unwinnable state without doing any reasoning itself.

### No machine learning

This is exhaustive search, not a trained model.

1. **Correctness.** A puzzle site must be provably right. Search proves this line wins and no other does. The uniqueness filter requires exhaustiveness.
2. **No training data exists.** Creating it would require a solver — the thing it would supposedly replace.
3. **The space is small.** Tapped-out, one set, depth 6-12. Search finishes in milliseconds.

**Where ML earns a place later (v2, after real users):** predicting human *difficulty*. Once players have solved a few dozen puzzles, you have labeled data on how hard humans find positions the solver rates as equivalent depth. Training data is a byproduct of running the site.

---

## Week-by-week

### Week 0 — Scope and unblock
- Send Riot dev rel the scoping question; record the date
- Freeze card pool to Origins
- Pull card data from Riftcodex / RiftScribe
- Repo up with the legal notice in the README

### Week 1 — Rules model
- Implement `GameState`, canonical hash, and the action space
- Implement the scoring module
- **Write the scoring test suite from RiftJudge rulings.** This is the gate for everything downstream.

### Week 2 — Solver
- IDDFS with transposition table
- Pruning rules
- Returns full winning line
- Benchmark on hand-built positions with known answers

### Week 3 — Hand-authored puzzles, then generation
- **Build the local board editor first.** You need it to construct positions anyway, and it stays a dev tool — it never ships to the public site.
- Hand-author the first 6 puzzles, verify each with the solver. This is how you learn what makes a position interesting and how you catch rules-model bugs (you already know the intended answer).
- Then build generation: sample random legal positions, solve each, keep only those where:
  - a win exists
  - the solution takes ≥ 4-5 actions
  - **the obvious greedy line fails** ← this filter is what separates a puzzle from a board state
  - the winning line is essentially unique
  - the exported graph is under a few MB
- Expect to keep well under 1% of sampled positions
- **Hand-audit every survivor.** Generation produces candidates, not content.

### Week 4 — Site
- Astro or Next static export; board as SVG or plain HTML
- **Static reveal version first** — position, think, click reveal, read the line with an explanation of why the obvious play loses
- **Then the graph walker behind a flag** — click actions, board updates, undo, legal-action highlighting, win/dead-end detection from the exported labels
- **One puzzle per week, not per day.** Authoring cost is real; weekly is sustainable, daily is not.
- Legal notice in the footer

### Week 5 — Launch
- Submit to rift.tools
- Post first three puzzles to r/RiftboundTCG
- Share in community Discords
- **Highest-leverage move:** offer puzzles as a weekly content drop to Piltover Archive or riftbound.gg rather than competing for traffic. They have the audience; you have something they don't. A collaboration credit reads better than a solo site with forty visitors.

### Week 6 — The writeup
This is the actual internship deliverable, more than the site is.

- State encoding and canonical hashing
- Search and pruning strategy
- The precomputed-graph architecture and why it beats shipping a second engine
- How the rules model was validated against judge rulings
- Generation-and-filtering pipeline with hit-rate numbers
- The policy section (see above)
- Honest limitations: tapped-out assumption, single set, no hidden information
- Link from the README

---

## Cut list (in order, if behind)

1. Drop the graph walker — ship static reveal only (the flag already makes this one line)
2. Drop generation — hand-author 6 puzzles
3. Drop the site — post puzzles as images to Reddit with the solver repo linked
4. **Never drop the rules test suite**

## Kill criteria

If the rules model is not passing its scoring tests by the end of week 2, stop and pivot to the collection-gap acquisition optimizer. A wrong solver is worse than no project, and four weeks would remain.

## Failure mode to avoid

A site that tells a strong player their correct line is wrong gets dismantled in Discord within a day. Correctness beats volume, every time.
