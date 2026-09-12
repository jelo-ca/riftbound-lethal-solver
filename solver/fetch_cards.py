"""One-time script: pull the Origins (OGN) card pool from the Riftcodex API
and cache it to solver/data/cards_raw.json. See design/01-data-sources.md.

Not called by the solver, exporter, or tests — re-run manually when the
cache needs refreshing:

    python solver/fetch_cards.py
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://api.riftcodex.com"
SET_ID = "OGN"
PAGE_SIZE = 100
OUTPUT_PATH = Path(__file__).parent / "data" / "cards_raw.json"


def fetch_all_cards(set_id: str) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        url = f"{API_BASE}/cards?set_id={set_id}&page={page}&size={PAGE_SIZE}"
        request = urllib.request.Request(url, headers={"User-Agent": "rb-puzzles/0.1"})
        with urllib.request.urlopen(request) as response:
            payload = json.load(response)
        items.extend(payload["items"])
        if page >= payload["pages"]:
            break
        page += 1
    return items


def main() -> None:
    items = fetch_all_cards(SET_ID)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "set_id": SET_ID,
                "source": f"{API_BASE}/cards?set_id={SET_ID}",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "count": len(items),
                "items": items,
            },
            indent=2,
        )
    )
    print(f"Wrote {len(items)} cards to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
