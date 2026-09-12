# Solver + DFS System — Design Overview

Status: **design review, no code written yet.** This directory is the thing to review before any implementation cycles start.

This covers the *solver* half of the project (`solver/` in the repo). Site/graph-walker design is unchanged from `riftbound-lethal-puzzle-plan.md` Week 4 and is not re-covered here.

## Scope statement (v0)

Small on purpose — every mechanic added here is a mechanic that must be modeled, tested, and kept correct forever.

- **Origins (`OGN`) set only**, and within it, only a **hand-picked whitelist** of cards needed for the first puzzles — not full-set rules coverage.
- **2 battlefields**, no special battlefield effects in v0 puzzles.
- **Opponent tapped out** — no defender-choice branching beyond required combat resolution (per `riftbound-lethal-puzzle-plan.md`).
- **Full information**, no hidden zones, no randomness.

Full detail: [`07-scope-and-cut-list.md`](07-scope-and-cut-list.md).

## Documents in this set

| Doc | Covers |
|---|---|
| [`01-data-sources.md`](01-data-sources.md) | Which APIs we pull card data from, verified live, schema, ingestion pipeline |
| [`02-state-model.md`](02-state-model.md) | `GameState` shape, canonical hashing for dedup |
| [`03-action-space.md`](03-action-space.md) | Legal action types and how they're generated |
| [`04-scoring-rules.md`](04-scoring-rules.md) | Conquer/Hold/last-point rules, the module every puzzle's correctness depends on |
| [`05-dfs-solver.md`](05-dfs-solver.md) | IDDFS algorithm, transposition table, pruning |
| [`06-export-schema.md`](06-export-schema.md) | Puzzle JSON DAG format shipped to the web layer |
| [`07-scope-and-cut-list.md`](07-scope-and-cut-list.md) | Explicit v0 boundaries and open rules questions needing verification |
| [`08-puzzle-concepts.md`](08-puzzle-concepts.md) | 6 sketched puzzle concepts (real Origins cards) that bound the whitelist and keyword set |
| [`09-combat-resolution.md`](09-combat-resolution.md) | Combat damage assignment, and the AND-node needed for adversarial defender choice |

## System diagram

```mermaid
flowchart LR
    subgraph Data["Data pipeline (01)"]
        API[Riftcodex API]
        RAW[cards_raw.json]
        WL[Hand-authored whitelist\n+ ability overrides]
        CUR[cards_curated.json]
        API --> RAW --> CUR
        WL --> CUR
    end

    subgraph Engine["Rules engine"]
        STATE[GameState + canonical hash\n(02)]
        ACT[Action space\n(03)]
        SCORE[Scoring module\n(04)]
    end

    subgraph Search["Solver (05)"]
        IDDFS[IDDFS + transposition table]
    end

    subgraph Author["Authoring (Week 3, not this doc set)"]
        HAND[Hand-authored positions]
    end

    EXPORT[export.py\nDAG -> JSON (06)]
    WEB[Web graph walker\n(unchanged, Week 4 plan)]

    CUR --> STATE
    HAND --> STATE
    STATE --> ACT --> IDDFS
    STATE --> SCORE --> IDDFS
    IDDFS --> EXPORT --> WEB
```

Source: [`diagrams/00-system.mmd`](diagrams/00-system.mmd)
