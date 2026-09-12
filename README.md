# Riftbound Lethal Puzzle

A Python rules engine and iterative-deepening DFS solver for Riftbound "find the winning line" puzzles. The solver precomputes each puzzle's full reachable state graph; a TypeScript front end walks that graph so players get real interactivity with zero rules logic in the browser.

Full build plan: [`riftbound-lethal-puzzle-plan.md`](riftbound-lethal-puzzle-plan.md).

## Repo layout

```
solver/          Python — rules model, IDDFS, puzzle generation
  engine/        state, actions, scoring
puzzles/         generated JSON, one per puzzle
web/             TS — graph walker + board rendering, zero rules logic
```

## Status

Week 0 — scaffold only. No rules logic implemented yet.

## Legal

Riftbound Lethal Puzzle was created under Riot Games' "Legal Jibber Jabber" policy using assets owned by Riot Games. Riot Games does not endorse or sponsor this project.
