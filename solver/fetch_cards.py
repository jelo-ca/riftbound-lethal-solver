"""One-time/on-demand ingestion: pulls every Origins printing from
RiftScribe into `data/cards-ogn.json`, a verbatim dump of the API's card
objects keyed by card id. See design/01-data-sources.md.

Source note. design/01-data-sources.md named Riftcodex as primary and
RiftScribe as an unverified fallback. That is now inverted:
api.riftcodex.com times out on every path (verified against curl and
Python, sandboxed and not, while riftcodex.com itself answers in 0.2s on
the same Cloudflare IPs), and RiftScribe turns out to be the better
source anyway —

  * its `id` IS our card_id ("ogn-205-298"), so there is no mapping layer
  * `keywords` is a structured list, not prose to parse
  * `stats` is structured {energy, might, power}
  * it carries card art (CDN originals plus three thumbnail sizes)

Two request shapes, because the list endpoint returns a TRIMMED record:
`?limit=&offset=` gives the index (id, name, stats, art) 200 at a time
with an `x-total-count` header, while `/cards/{id}` is the only way to
get `description`, `keywords` and `tags`. So the index is two calls and
the details are one per printing.

This is DISPLAY data and reference material, never rules logic. Card
text is prose with inline bracketed keyword tags and no machine-readable
effect field, so every card the engine resolves stays hand-transcribed
in engine/card_pool.py. What the API IS good for is checking the parts
that are structured: auditing the pool against it found five of fourteen
cards with wrong costs or Might, one of them (Yasuo) at half his printed
Might, which had silently shaped a puzzle around a fight he could not
actually lose.

Never called at solve time or render time: run it, commit the result,
read the file everywhere else.

Run with: python -m solver.fetch_cards
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://riftscribe.gg/api"
SET_ID = "OGN"
# The index endpoint rejects limit>200 with a 422.
PAGE_LIMIT = 200
USER_AGENT = "rb-puzzles-ingest/1.0 (Riot Legal Jibber Jabber; contact via repo)"

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "cards-ogn.json"


def _get(url: str, timeout: int, retries: int, backoff: float) -> tuple[object, dict]:
    """One GET with retries, returning (payload, headers). RiftScribe is a
    fan project with no documented rate limits, so treat a transient
    failure as expected rather than exceptional."""
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response), dict(response.headers)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt < retries:
                delay = backoff * attempt
                print(f"    attempt {attempt}/{retries} failed ({type(exc).__name__}); "
                      f"retrying in {delay:.0f}s")
                time.sleep(delay)
    raise RuntimeError(f"giving up on {url} after {retries} attempts: {last}") from last


def fetch_index(base_url: str, timeout: int, retries: int, backoff: float) -> list[str]:
    """Every printing id in the set, via the paged index endpoint."""
    ids: list[str] = []
    offset = 0
    total: int | None = None
    while True:
        url = f"{base_url}/cards?set_id={SET_ID}&limit={PAGE_LIMIT}&offset={offset}"
        rows, headers = _get(url, timeout, retries, backoff)
        if not isinstance(rows, list):
            raise RuntimeError(f"expected a list from {url}, got {type(rows).__name__}")
        if total is None:
            total = int(headers.get("x-total-count", 0)) or None
        ids += [row["id"] for row in rows if row.get("id")]
        print(f"  index: {len(ids)}" + (f"/{total}" if total else ""))
        if not rows or (total is not None and len(ids) >= total) or len(rows) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
    if total is not None and len(ids) != total:
        print(f"  warning: index returned {len(ids)} ids but x-total-count said {total}")
    return ids


def fetch_all(timeout: int = 30, retries: int = 3, backoff: float = 5.0,
               delay: float = 0.1, base_url: str = BASE_URL) -> dict[str, dict]:
    """Full records for every printing, keyed by id. The per-card endpoint
    is the only one carrying `description`/`keywords`, so this is one
    request per printing after the index — slow but run once."""
    ids = fetch_index(base_url, timeout, retries, backoff)
    cards: dict[str, dict] = {}
    for position, card_id in enumerate(ids, start=1):
        payload, _ = _get(f"{base_url}/cards/{card_id}", timeout, retries, backoff)
        if isinstance(payload, dict) and payload.get("id"):
            cards[payload["id"]] = payload
        if position % 25 == 0 or position == len(ids):
            print(f"  details: {position}/{len(ids)}")
        if delay:
            time.sleep(delay)
    return cards


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Origins card data.")
    parser.add_argument("--base-url", default=BASE_URL,
                         help="API root, if the host or prefix moves again")
    parser.add_argument("--timeout", type=int, default=30, help="per-request timeout in seconds")
    parser.add_argument("--retries", type=int, default=3, help="attempts per request")
    parser.add_argument("--backoff", type=float, default=5.0, help="seconds * attempt between retries")
    parser.add_argument("--delay", type=float, default=0.1,
                         help="pause between detail requests, to stay polite")
    args = parser.parse_args()

    print(f"Fetching {SET_ID} printings from {args.base_url} ...")
    cards = fetch_all(timeout=args.timeout, retries=args.retries, backoff=args.backoff,
                       delay=args.delay, base_url=args.base_url)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(cards, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(cards)} cards to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
