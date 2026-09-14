# `data/`

Ingested reference data, shared by the solver and the web layer. Produced by a script, committed to the repo, never fetched at solve time or render time.

## `cards-ogn.json`

Every Origins printing from [RiftScribe](https://riftscribe.gg), keyed by card id (e.g. `ogn-205-298`), stored verbatim as the API returned it. **352 printings, ~0.9 MB.**

RiftScribe rather than Riftcodex, which `design/01-data-sources.md` originally named as primary: `api.riftcodex.com` times out on every path (checked with curl and Python, sandboxed and not, while `riftcodex.com` itself answers in 0.2s from the same Cloudflare IPs). RiftScribe is also the better fit — its `id` *is* our `card_id`, `keywords` is a structured list rather than prose, and it carries card art.

```
python -m solver.fetch_cards
```

Two index requests (`?limit=200&offset=`) plus one per printing, because the list endpoint returns a trimmed record and only `/cards/{id}` carries `description`, `keywords` and `tags`. A few minutes, run once. Re-run only when the set gains printings — not when a puzzle uses a new card, since the cache already holds all of them.

**Committed on purpose.** A fresh clone, a CI run, and an offline build all need names without touching the network, and these are fan projects with no uptime guarantee — the original source went dark entirely mid-project. Caching aggressively is what `design/01-data-sources.md` asks for, and it means card data can never block work again.

### Who reads it

| consumer | via | for |
|---|---|---|
| solver | `solver/engine/card_names.py` | action labels in the exported puzzle JSON |
| web | `web/scripts/fetch-card-names.mjs` | derives `web/src/data/card-names.json`, trimmed to cards the puzzles reference |

The web layer reads the trimmed derivative rather than this file — the browser needs a dozen cards, not the whole set.

### What it is not

**Not a rules source.** `keywords` is structured and `stats` is trustworthy — auditing the pool against them caught five of fourteen cards with wrong costs or Might. But card *text* is unstructured prose: keyword mentions are inline bracketed tags and there is no machine-readable effect field, so nothing in it can drive legality or scoring. Every card the engine actually resolves is hand-transcribed in `solver/engine/card_pool.py`, and that stays true no matter how complete this file gets. Only `stats` (energy/power/might), `domains` and `keywords` are structured enough to trust, and even those are reference material to check the hand-written pool against rather than inputs to it.

**Optional.** Every lookup falls back to the raw card id, so an absent or stale cache degrades presentation and nothing else. The engine and its tests behave identically without it.

## Legal

RiftScribe data and card art are used under Riot Games' "Legal Jibber Jabber" policy, same as the rest of the project. See the repo README.
