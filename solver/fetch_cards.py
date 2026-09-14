"""One-time/on-demand ingestion: bulk-pulls every Origins printing from
Riftcodex into `data/cards-ogn.json`, a verbatim dump of the API's card
objects keyed by `riftbound_id`. See design/01-data-sources.md.

Bulk rather than per-card on purpose. The set is ~350 printings and the
endpoint pages 100 at a time, so the whole thing is four requests —
fewer than looking up the dozen-odd ids the puzzles happen to reference,
and it never needs re-running when a puzzle introduces a new card. It
also gives pool expansion something to read: choosing which Origins
cards to implement next means looking at names, costs, domains and text
for all of them, not just the ones already in play.

This is DISPLAY data and reference material, never rules logic. The
API's card text is unstructured prose — keyword mentions appear inline
as bracketed tags, there is no structured effect field — so every card
the engine actually resolves stays hand-transcribed in
engine/card_pool.py. Nothing here feeds legality or scoring, and the
solver runs correctly with this file absent.

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

BASE_URL = "https://api.riftcodex.com"
SET_ID = "OGN"
PAGE_SIZE = 100  # the endpoint's documented maximum
USER_AGENT = "rb-puzzles-ingest/1.0 (+https://github.com/; Riot Legal Jibber Jabber)"

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "cards-ogn.json"


def _get(url: str, timeout: int, retries: int, backoff: float) -> dict:
    """One GET with retries. Riftcodex is a fan project with no documented
    rate limits and has been observed returning 502s and hanging, so a
    transient failure is expected rather than exceptional."""
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt < retries:
                delay = backoff * attempt
                print(f"    attempt {attempt}/{retries} failed ({type(exc).__name__}); "
                      f"retrying in {delay:.0f}s")
                time.sleep(delay)
    raise RuntimeError(f"giving up on {url} after {retries} attempts: {last}") from last


def _cards_from_page(payload: object) -> list[dict]:
    """The endpoint has been seen returning either a bare list or an
    envelope around one; accept both rather than guessing."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "data", "cards", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise RuntimeError(f"unrecognised page shape: {type(payload).__name__} "
                       f"{list(payload)[:8] if isinstance(payload, dict) else ''}")


def fetch_all(timeout: int = 30, retries: int = 3, backoff: float = 5.0,
               max_pages: int = 20) -> dict[str, dict]:
    """Every Origins printing, keyed by `riftbound_id` (e.g.
    "ogn-205-298"). Printings with no riftbound_id are skipped — that id
    is the only thing puzzle JSON refers to cards by."""
    cards: dict[str, dict] = {}
    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}/cards?set_id={SET_ID}&page={page}&size={PAGE_SIZE}"
        print(f"  page {page} ...")
        batch = _cards_from_page(_get(url, timeout, retries, backoff))
        if not batch:
            break
        for card in batch:
            riftbound_id = card.get("riftbound_id")
            if riftbound_id:
                cards[riftbound_id] = card
        if len(batch) < PAGE_SIZE:
            break
    else:
        raise RuntimeError(f"still returning full pages after {max_pages}; "
                           "raise max_pages or check for a pagination change")
    return cards


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=30, help="per-request timeout in seconds")
    parser.add_argument("--retries", type=int, default=3, help="attempts per request")
    parser.add_argument("--backoff", type=float, default=5.0, help="seconds * attempt between retries")
    args = parser.parse_args()

    print(f"Fetching {SET_ID} printings from {BASE_URL} ...")
    cards = fetch_all(timeout=args.timeout, retries=args.retries, backoff=args.backoff)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(cards, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(cards)} cards to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
