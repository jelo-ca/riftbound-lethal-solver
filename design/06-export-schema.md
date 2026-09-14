# Export Schema

Refines the JSON DAG sketch already in `riftbound-lethal-puzzle-plan.md`. This is the contract between `solver/export.py` and the web graph walker — the web layer does table lookup on this, no rules logic (per the core architecture decision).

```json
{
  "schema_version": 2,
  "puzzle_id": "ogn-001",
  "root": "state_hash_abc",
  "solution": {
    "state_hash_abc": "action_id_1",
    "state_hash_def": "action_id_2"
  },
  "nodes": {
    "state_hash_abc": {
      "battlefields": [ /* renderable BattlefieldState, JSON-friendly field names */ ],
      "players": [ /* renderable PlayerState */ ],
      "scores": [0, 0]
    }
  },
  "edges": {
    "state_hash_abc": [
      {
        "action": { "id": "action_id_1", "type": "MoveUnit", "label": "Move Vanguard Captain to Left" },
        "to": ["state_hash_def"],
        "adversarial": false
      }
    ]
  },
  "terminal": {
    "state_hash_xyz": "win",
    "state_hash_qrs": "dead_end"
  }
}
```

- `schema_version` — bumped to 2 in the combat-resolution pass (`09-combat-resolution.md`): `edges[...].to` changed shape and `solution` changed shape, both breaking. The web layer consumes `schema_version` directly; bump on any breaking field change so a stale cached puzzle JSON fails loudly instead of rendering wrong.
- `nodes` values are a **renderable projection** of `GameState`, not the raw dataclass — human/UI-friendly field names, no internal-only fields like `instance_id` sort keys.
- `terminal` only lists nodes that are actually terminal; non-terminal nodes are simply absent from the map (not an explicit `"in_progress"` value) — smaller payload, and absence-means-continue is the invariant the web layer checks.
- `edges` carries a human-readable `label` per action specifically so the web layer never has to synthesize move descriptions from raw state diffs.
- **Each action also carries `card_id`, `keywords`, `from_zone` and `to_zone`** — the structure behind the label, so nothing downstream has to parse prose to recover it. `from_zone`/`to_zone` are null for actions that aren't moves (a unit played from hand has a `to_zone` but no `from_zone`). `maneuvers.py` needs the zones to tell whether `[Ganking]` was doing anything (it only matters Battlefield-to-Battlefield, rule 810); the web layer needs them to animate a move. **This section of the doc drifted once already** — it described `nodes` as carrying `"scores": [0, 0]` and omitting internal fields like `instance_id`, and neither was true of what `export.py` actually emitted. Treat `solver/export.py`'s `render_*` functions as the contract and fix this file when they change.
- **`edges[...].to` is always a list, not a single string** (schema v2 change). Most actions have exactly one element — a deterministic outcome. An action that triggers combat with a genuine opponent damage-assignment choice (`09-combat-resolution.md`) has one element **per possible opponent response** and `"adversarial": true` — the player's actual resulting state after taking that action depends on which way the opponent split their damage, not on anything the player controls. The web layer decides how to present that (pick one to simulate a playthrough, or let the player explore each branch) — that's Week 4 UX, not this schema's concern; the schema's job is just to not hide that the branch exists.
- **`solution` is a flat map from `state_hash` to the recommended `action_id` at that state**, not an ordered list. This is deliberately not a linear path: since an adversarial edge can lead to multiple different states depending on the opponent, "the solution" is really a *strategy* — one recommended action for every state the player might actually find themselves in while following it, including every opponent-forced branch. A puzzle with no adversarial edges degenerates to exactly the old flat-list behavior, just keyed by state instead of by position — every state in the map has exactly one successor also in the map, forming a single chain. States not in the map are either a `"win"` terminal (nothing left to recommend) or simply not part of the strategy.

Not re-covering the DAG enumeration/dedup process itself here — that's what `05-dfs-solver.md` + the canonical hash in `02-state-model.md` already produce; `export.py`'s job is walking the already-deduped state graph the solver's search visited and serializing it.
