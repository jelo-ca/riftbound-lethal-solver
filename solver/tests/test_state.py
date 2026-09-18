from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    UnitInstance,
    add_runes,
    canonical_key,
    energy_capacity,
    power_capacity,
    ready_runes,
    sorted_available,
)


def make_unit(card_id="ogn-211-298", instance_id=1, controller=0, might=1,
              keywords=frozenset(), exhausted=False, damage=0, is_token=True):
    return UnitInstance(
        card_id=card_id,
        instance_id=instance_id,
        controller=controller,
        might=might,
        keywords=keywords,
        exhausted=exhausted,
        damage=damage,
        is_token=is_token,
    )


def make_state(player0_base=frozenset(), player0_hand=(), player0_runes=(),
               player1_base=frozenset(), battlefield0_units=frozenset(),
               battlefield1_units=frozenset(), scored_this_turn=frozenset(),
               battlefield0_id="left", battlefield1_id="right"):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(
                base_units=player0_base,
                hand=player0_hand,
                runes=RunePool(available=player0_runes),
                score=0,
            ),
            PlayerState(
                base_units=player1_base,
                hand=(),
                runes=RunePool(available=()),
                score=0,
            ),
        ),
        battlefields=(
            BattlefieldState(battlefield_id=battlefield0_id, controller=None,
                              units=battlefield0_units, effect_id=None),
            BattlefieldState(battlefield_id=battlefield1_id, controller=None,
                              units=battlefield1_units, effect_id=None),
        ),
        scored_this_turn=scored_this_turn,
        cards_played_this_turn=0,
    )


def test_identical_states_hash_equal():
    s1 = make_state()
    s2 = make_state()
    assert canonical_key(s1) == canonical_key(s2)


def test_hand_order_does_not_matter():
    s1 = make_state(player0_hand=("ogn-209-298", "ogn-010-298"))
    s2 = make_state(player0_hand=("ogn-010-298", "ogn-209-298"))
    assert canonical_key(s1) == canonical_key(s2)


def test_rune_order_does_not_matter():
    s1 = make_state(player0_runes=("Order", "Fury", "Order"))
    s2 = make_state(player0_runes=("Fury", "Order", "Order"))
    assert canonical_key(s1) == canonical_key(s2)


def test_tokens_with_different_instance_ids_but_same_attributes_collapse():
    # Two Recruit tokens created in one order (ids 1, 2) vs the reverse
    # creation order (ids 5, 6) — same visible board, must hash equal.
    # This is the exact case the initial (buggy) design doc version would
    # have failed: keeping instance_id in the key would make these differ.
    tokens_a = frozenset({make_unit(instance_id=1), make_unit(instance_id=2)})
    tokens_b = frozenset({make_unit(instance_id=5), make_unit(instance_id=6)})
    s1 = make_state(battlefield0_units=tokens_a)
    s2 = make_state(battlefield0_units=tokens_b)
    assert canonical_key(s1) == canonical_key(s2)


def test_units_with_different_might_do_not_collapse():
    s1 = make_state(battlefield0_units=frozenset({make_unit(might=1)}))
    s2 = make_state(battlefield0_units=frozenset({make_unit(might=2)}))
    assert canonical_key(s1) != canonical_key(s2)


def test_units_with_different_keywords_do_not_collapse():
    s1 = make_state(battlefield0_units=frozenset({make_unit(keywords=frozenset())}))
    s2 = make_state(battlefield0_units=frozenset({make_unit(keywords=frozenset({"Tank"}))}))
    assert canonical_key(s1) != canonical_key(s2)


def test_battlefield_order_is_not_normalized():
    # Same content, but assigned to swapped battlefield identities — these
    # are genuinely different game states (battlefield identity/effect can
    # differ) and must NOT collapse.
    unit = make_unit()
    s1 = make_state(battlefield0_units=frozenset({unit}), battlefield1_units=frozenset())
    s2 = make_state(battlefield0_units=frozenset(), battlefield1_units=frozenset({unit}))
    assert canonical_key(s1) != canonical_key(s2)


def test_scored_this_turn_order_does_not_matter():
    s1 = make_state(scored_this_turn=frozenset({"left", "right"}))
    s2 = make_state(scored_this_turn=frozenset({"right", "left"}))
    assert canonical_key(s1) == canonical_key(s2)


# --- Domain-less runes (RULING 1, project owner, 2026-09-18) ---------------
#
# A "channel N runes" / "add 1 rainbow rune" effect can't draw a real domain
# from anywhere (no Rune Deck), so the sound reading is: Energy capacity
# only, NEVER Power capacity, regardless of domain. See RunePool's and
# add_runes's docstrings.


def test_domain_less_rune_adds_energy_capacity():
    pool = RunePool(available=("Fury",))
    channeled = add_runes(pool, (None,))
    assert energy_capacity(channeled) == 2


def test_domain_less_rune_never_pays_any_power_cost():
    pool = RunePool(available=("Fury",))
    channeled = add_runes(pool, (None,))
    # Not even a domain-free (rainbow) cost, despite "counts every domain"
    # being power_capacity(pool, None)'s usual meaning for REAL domains.
    assert power_capacity(channeled, None) == 1  # only the real Fury rune
    assert power_capacity(channeled, "Fury") == 1
    for domain in ("Fury", "Calm", "Mind", "Body", "Chaos", "Order"):
        assert power_capacity(channeled, domain) <= pool.available.count(domain)


def test_channel_1_rune_exhausted_arrives_with_zero_net_energy():
    """"Channel 1 rune exhausted" (~12 cards' exact phrasing) — the rune's
    own Energy is already spent the instant it arrives, and it can never
    pay Power, so it contributes nothing observable UNLESS something
    readies runes later this same turn."""
    pool = RunePool(available=("Fury",), energy_spent=1)  # already tapped out
    assert energy_capacity(pool) == 0
    channeled = add_runes(pool, (None,), exhausted=True)
    assert energy_capacity(channeled) == 0  # +1 available, +1 spent: net zero
    # A readying effect (e.g. Ekko, Recurrent's Deathknell) restores it —
    # the channelled rune is a REAL rune from here on, not inert forever.
    assert energy_capacity(ready_runes(channeled)) == 2


def test_domain_less_rune_readies_like_any_other():
    pool = add_runes(RunePool(available=()), (None,), exhausted=True)
    assert energy_capacity(pool) == 0
    assert energy_capacity(ready_runes(pool)) == 1


def test_sorted_available_orders_domain_less_rune_after_real_domains():
    # Regression guard for the None-vs-str TypeError plain sorted() would
    # raise; also pins the ordering so canonical_key/export.py agree.
    assert sorted_available(("Fury", None, "Calm")) == ["Calm", "Fury", None]


def test_canonical_key_handles_domain_less_rune_without_crashing():
    import dataclasses

    exhausted_pool = add_runes(RunePool(available=("Fury",)), (None,), exhausted=True)
    ready_pool = RunePool(available=exhausted_pool.available, energy_spent=0)
    s1 = make_state(player0_runes=("Fury",))
    s1 = dataclasses.replace(
        s1, players=(dataclasses.replace(s1.players[0], runes=exhausted_pool), s1.players[1])
    )
    s2 = dataclasses.replace(
        s1, players=(dataclasses.replace(s1.players[0], runes=ready_pool), s1.players[1])
    )
    # Same runes present, different amount of Energy already spent on the
    # domain-less one — a genuinely different position (canonical_key must
    # not crash comparing None against a domain str, and must tell them
    # apart, same as any other rune's energy_spent).
    assert canonical_key(s1) != canonical_key(s2)
