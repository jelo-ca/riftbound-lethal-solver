# Export Schema

Refines the JSON DAG sketch already in `riftbound-lethal-puzzle-plan.md`. This is the contract between `solver/export.py` and the web graph walker — the web layer does table lookup on this, no rules logic (per the core architecture decision).

```json
{
  "schema_version": 1,
  "puzzle_id": "ogn-001",
  "root": "state_hash_abc",
  "solution": ["action_id_1", "action_id_2", "..."],
  "nodes": {
    "state_hash_abc": {
      "battlefields": [ /* renderable BattlefieldState, JSON-friendly field names */ ],
      "players": [ /* renderable PlayerState */ ],
      "scores": [0, 0]
    }
  },
  "edges": {
    "state_hash_abc": [
      { "action": { "id": "action_id_1", "type": "MoveUnit", "label": "Move Vanguard Captain to Left" }, "to": "state_hash_def" }
    ]
  },
  "terminal": {
    "state_hash_xyz": "win",
    "state_hash_qrs": "dead_end"
  }
}
```

- `schema_version` — added in this pass, wasn't in the original sketch. The web layer consumes this directly; bump on any breaking field change so a stale cached puzzle JSON fails loudly instead of rendering wrong.
- `nodes` values are a **renderable projection** of `GameState`, not the raw dataclass — human/UI-friendly field names, no internal-only fields like `instance_id` sort keys.
- `terminal` only lists nodes that are actually terminal; non-terminal nodes are simply absent from the map (not an explicit `"in_progress"` value) — smaller payload, and absence-means-continue is the invariant the web layer checks.
- `edges` carries a human-readable `label` per action specifically so the web layer never has to synthesize move descriptions from raw state diffs.

Not re-covering the DAG enumeration/dedup process itself here — that's what `05-dfs-solver.md` + the canonical hash in `02-state-model.md` already produce; `export.py`'s job is walking the already-deduped state graph the solver's search visited and serializing it.
