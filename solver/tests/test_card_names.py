"""Display names read from the ingested Riftcodex cache.

The cache is optional on purpose: it is a committed network artifact that
can be absent on a fresh clone or stale when a printing appears, so every
lookup falls back to the card id and nothing in the engine depends on it.
These tests pin that the fallback is total — a missing, unreadable or
partial cache degrades presentation and nothing else.
"""

import json

import pytest

from solver.engine import card_names


@pytest.fixture(autouse=True)
def clear_cache_memo():
    """The loader memoises, so every test has to start from cold."""
    card_names._cache.cache_clear()
    yield
    card_names._cache.cache_clear()


@pytest.fixture
def cache_at(tmp_path, monkeypatch):
    def write(payload):
        path = tmp_path / "cards-ogn.json"
        path.write_text(payload if isinstance(payload, str) else json.dumps(payload),
                        encoding="utf-8")
        monkeypatch.setattr(card_names, "CACHE_PATH", path)
        card_names._cache.cache_clear()
        return path
    return write


SAMPLE = {
    "ogn-205-298": {
        "name": "Yasuo - Rider of the Wind",
        "text": {"plain": "The third time I move in a turn, you score 1 point."},
        "classification": {"type": "Unit"},
    },
}


def test_names_resolve_when_the_cache_has_the_card(cache_at):
    cache_at(SAMPLE)
    assert card_names.display_name("ogn-205-298") == "Yasuo - Rider of the Wind"
    assert card_names.card_text("ogn-205-298").startswith("The third time I move")
    assert card_names.is_available()


def test_a_missing_cache_falls_back_to_the_card_id(tmp_path, monkeypatch):
    monkeypatch.setattr(card_names, "CACHE_PATH", tmp_path / "absent.json")
    card_names._cache.cache_clear()
    assert card_names.display_name("ogn-205-298") == "ogn-205-298"
    assert card_names.card_text("ogn-205-298") is None
    assert not card_names.is_available()


def test_an_unreadable_cache_falls_back_rather_than_raising(cache_at):
    """A truncated or half-written file must not take the exporter down
    with it."""
    cache_at("{ this is not json")
    assert card_names.display_name("ogn-205-298") == "ogn-205-298"
    assert not card_names.is_available()


def test_an_id_the_cache_does_not_know_falls_back(cache_at):
    cache_at(SAMPLE)
    assert card_names.display_name("ogn-999-298") == "ogn-999-298"
    assert card_names.card_text("ogn-999-298") is None


def test_engine_invented_ids_get_a_readable_placeholder(cache_at):
    """The generated opponent body has no printing behind it — it stands
    in for "whatever the opponent has there"."""
    cache_at(SAMPLE)
    assert card_names.display_name("generic-opponent") == "Opponent Unit"


def test_describe_keeps_the_id_alongside_the_name(cache_at):
    cache_at(SAMPLE)
    assert card_names.describe("ogn-205-298") == "Yasuo - Rider of the Wind (ogn-205-298)"
    # ...and doesn't say it twice when there's no name to add.
    assert card_names.describe("ogn-999-298") == "ogn-999-298"


def test_a_card_with_no_text_is_not_an_error(cache_at):
    cache_at({"ogn-010-298": {"name": "Legion Rearguard"}})
    assert card_names.display_name("ogn-010-298") == "Legion Rearguard"
    assert card_names.card_text("ogn-010-298") is None
