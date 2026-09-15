"""Deriving CardDefs from the cache instead of retyping them.

The load-bearing test here is the CARD_POOL cross-check: every card the
engine already carries by hand must come back identical from the cache.
A mismatch is either a generator bug or a transcription bug, and this
project has had five of the latter — Yasuo recorded at half his printed
Might silently reshaped a puzzle around a fight he could not lose.
"""

import dataclasses

import pytest

from solver.engine.card_data import (
    CardDataError,
    build_card_def,
    generatable_card_ids,
    try_build_card_def,
)
from solver.engine.card_pool import CARD_POOL

RECRUIT_TOKEN = "ogn-271-298"


# --- the cross-check ---


def test_generated_card_defs_match_the_hand_written_pool():
    """Field for field, for every card the engine carries by hand."""
    mismatches = []
    for card_id, hand_written in sorted(CARD_POOL.items()):
        generated = try_build_card_def(card_id)
        if generated is None:
            continue  # refusals are asserted separately below
        for f in dataclasses.fields(hand_written):
            hand_value = getattr(hand_written, f.name)
            cache_value = getattr(generated, f.name)
            if hand_value != cache_value:
                mismatches.append(f"{card_id}.{f.name}: hand={hand_value!r} cache={cache_value!r}")
    assert not mismatches, "hand-written pool disagrees with the cache:\n" + "\n".join(mismatches)


def test_the_only_pool_card_the_cache_cannot_describe_is_the_token():
    """Tokens are minted by effects and never paid for, so there is no
    printed cost to read. Pinned explicitly so a future refusal of some
    OTHER pool card can't hide inside a silent skip."""
    refused = [cid for cid in CARD_POOL if try_build_card_def(cid) is None]
    assert refused == [RECRUIT_TOKEN]


# --- keyword normalisation ---


def test_numeric_keyword_suffixes_survive_normalisation():
    """The cache prints "deflect 2"; the engine's TRAIT_REGISTRY grammar
    is "Deflect 2". Losing the number would silently halve the trait."""
    volibear = build_card_def("ogn-041-298")
    assert "Deflect 2" in volibear.keywords


def test_plain_keywords_capitalise():
    assert build_card_def("ogn-052-298").keywords == frozenset({"Shield"})  # Stalwart Poro


def test_action_and_reaction_become_speed_not_keywords():
    """They describe WHEN a card is playable, which the engine models as
    CardDef.speed. Leaking them into keywords would put two non-traits
    into the trait vocabulary."""
    ride_the_wind = build_card_def("ogn-173-298")
    assert ride_the_wind.speed == "Action"
    assert ride_the_wind.keywords == frozenset()


def test_an_unmarked_card_is_slow():
    assert build_card_def("ogn-229-298").speed == "Slow"  # Vengeance


# --- fields read off the printed text ---


def test_accelerate_domain_comes_from_the_printed_rune_symbol():
    rearguard = build_card_def("ogn-010-298")
    assert "Accelerate" in rearguard.keywords
    assert rearguard.accelerate_domain == "Fury"
    assert rearguard.power_cost == 0  # the Fury requirement is NOT a power cost


def test_cards_without_accelerate_have_no_accelerate_domain():
    assert build_card_def("ogn-052-298").accelerate_domain is None


def test_open_battlefield_exception_is_detected():
    assert build_card_def("ogn-176-298").can_play_to_open_battlefield is True  # Sneaky Deckhand


def test_ordinary_cards_cannot_deploy_to_an_open_battlefield():
    assert build_card_def("ogn-052-298").can_play_to_open_battlefield is False


# --- refusals: the cache is not allowed to guess ---


def test_legends_runes_and_battlefields_are_refused():
    """CardDef's CardType is Unit/Spell/Gear — these have no
    representation at all, so producing one would be fabrication."""
    for card_id in ("ogn-247-298", "ogn-294-298"):  # Daughter of the Void, Trifarian War Camp
        with pytest.raises(CardDataError, match="no CardDef representation"):
            build_card_def(card_id)


def test_a_card_with_no_printed_energy_cost_is_refused():
    with pytest.raises(CardDataError, match="no printed Energy cost"):
        build_card_def(RECRUIT_TOKEN)


def test_two_domains_plus_a_power_cost_is_refused_as_ambiguous():
    """CardDef holds one power_domain. Which of the two pays is a real
    ambiguity, and picking one would be a coin flip dressed as data."""
    with pytest.raises(CardDataError, match="ambiguous"):
        build_card_def("ogn-248-298")  # Icathian Rain, Fury+Mind, 3 Power


def test_two_domains_with_no_power_cost_is_fine():
    """No Power cost means no domain has to be chosen, so multi-domain
    alone is not ambiguous."""
    assert try_build_card_def("ogn-256-298") is not None  # Fox-Fire, Calm+Mind, no Power


def test_an_unknown_card_id_is_refused():
    with pytest.raises(CardDataError, match="not present"):
        build_card_def("ogn-999-298")


def test_refusals_say_which_card_and_why():
    """A caller has to be able to tell "skip this card" from "fix this
    data" without reading the source."""
    with pytest.raises(CardDataError) as exc:
        build_card_def("ogn-248-298")
    message = str(exc.value)
    assert "ogn-248-298" in message and "Icathian Rain" in message


# --- set-wide sanity, as a tripwire on the data ---


def test_the_bulk_of_the_set_generates():
    """Guards against a schema change quietly gutting the generator: if
    the cache's field names moved, this collapses long before anything
    downstream notices."""
    generatable = generatable_card_ids()
    assert len(generatable) > 250, f"only {len(generatable)} of 352 printings generate"
    assert all(try_build_card_def(cid) is not None for cid in generatable)


def test_every_gear_card_generates():
    """Relevant to the Gear subsystem work: its 30 cards are all
    describable, so that effort needs no hand-transcription."""
    from solver.engine.card_data import _cache

    gear = [cid for cid, c in _cache().items() if c.get("type") == "Gear"]
    assert gear
    assert all(try_build_card_def(cid) is not None for cid in gear)
