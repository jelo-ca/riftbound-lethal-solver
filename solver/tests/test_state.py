from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    UnitInstance,
    canonical_key,
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
