# `data/`

Ingested reference data, shared by the solver and the web layer. Produced by a script, committed to the repo, never fetched at solve time or render time.

## `cards-ogn.json`

Every Origins printing from [Riftcodex](https://api.riftcodex.com), keyed by `riftbound_id` (e.g. `ogn-205-298`), stored verbatim as the API returned it.

```
python -m solver.fetch_cards
```

Four paginated requests for the whole set. Re-run only when the set gains printings — not when a puzzle uses a new card, since the cache already holds all of them.

**Committed on purpose.** A fresh clone, a CI run, and an offline build all need names without touching the network, and Riftcodex is a fan project with no uptime guarantee (it was returning 502s and timeouts when this was written). Caching aggressively is what `design/01-data-sources.md` asks for.

### Who reads it

| consumer | via | for |
|---|---|---|
| solver | `solver/engine/card_names.py` | action labels in the exported puzzle JSON |
| web | `web/scripts/fetch-card-names.mjs` | derives `web/src/data/card-names.json`, trimmed to cards the puzzles reference |

The web layer reads the trimmed derivative rather than this file — the browser needs a dozen cards, not the whole set.

### What it is not

**Not a rules source.** Card text here is unstructured prose: keyword mentions are inline bracketed tags and there is no machine-readable effect field, so nothing in it can drive legality or scoring. Every card the engine actually resolves is hand-transcribed in `solver/engine/card_pool.py`, and that stays true no matter how complete this file gets. Only `attributes` (energy/power/might) and `classification.domain` are structured enough to trust, and even those are reference material rather than inputs.

**Optional.** Every lookup falls back to the raw card id, so an absent or stale cache degrades presentation and nothing else. The engine and its tests behave identically without it.

## Legal

Riftcodex data is used under Riot Games' "Legal Jibber Jabber" policy, same as the rest of the project. See the repo README.
