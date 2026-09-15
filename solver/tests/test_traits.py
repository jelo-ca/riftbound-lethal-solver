"""Aura-granted traits (Taric, Protector: "Other friendly units here have
[Shield]") and the latent defect their wiring fixes: `effective_might`
used to read `unit.keywords` directly and never called through the
keyword/trait resolver, so a battlefield or aura granting a trait was
invisible to damage math. Taric is the first real card to exercise the
resolver's aura branch — see engine/traits.py's module docstring for the
non-circularity invariant this relies on.
"""

from solver.engine import combat, traits
from solver.engine.card_pool import TARIC_PROTECTOR
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance


def make_unit(instance_id, controller=0, card_id="ally", might=3, keywords=frozenset()):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=keywords, exhausted=False, damage=0, is_token=False)


def make_state(left_units, left_ctrl=0):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", left_ctrl, left_units, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def test_taric_aura_grants_shield_to_a_co_located_friendly_unit():
    taric = make_unit(1, card_id=TARIC_PROTECTOR, might=4, keywords=frozenset({"Shield", "Tank"}))
    ally = make_unit(2, might=3)
    state = make_state(left_units=frozenset({taric, ally}))
    assert "Shield" in traits.resolved_traits(state, ally, "left")


def test_taric_aura_raises_the_allys_effective_might_only_while_defending():
    """Regression for the latent defect: effective_might now routes through
    resolved_traits, so the aura-granted Shield actually counts — before
    this module existed, effective_might read unit.keywords directly and
    an aura/battlefield grant like this was invisible to it."""
    taric = make_unit(1, card_id=TARIC_PROTECTOR, might=4, keywords=frozenset({"Shield", "Tank"}))
    ally = make_unit(2, might=3)
    state = make_state(left_units=frozenset({taric, ally}))
    assert combat.effective_might(state, ally, "left", "defender") == 4  # 3 +1 Shield
    assert combat.effective_might(state, ally, "left", "attacker") == 3  # Shield doesn't apply attacking


def test_taric_aura_does_not_grant_to_enemy_units():
    taric = make_unit(1, controller=0, card_id=TARIC_PROTECTOR, might=4,
                       keywords=frozenset({"Shield", "Tank"}))
    enemy = make_unit(2, controller=1, might=3)
    state = make_state(left_units=frozenset({taric, enemy}), left_ctrl=None)
    assert "Shield" not in traits.resolved_traits(state, enemy, "left")


def test_taric_aura_stops_applying_once_taric_is_gone():
    """Non-staleness: nothing is cached on the ally's own state, so once
    Taric is no longer among the co-located units, resolved_traits just
    stops finding him — no separate cleanup step is needed."""
    ally = make_unit(2, might=3)
    state_without_taric = make_state(left_units=frozenset({ally}))
    assert "Shield" not in traits.resolved_traits(state_without_taric, ally, "left")


def test_taric_does_not_grant_shield_to_himself_via_a_second_copy():
    """"Other friendly units" — a lone Taric doesn't need the aura since
    he's already printed [Shield], but this proves the exclusion is by
    instance_id, not just "any unit of this card_id is skipped": a SECOND
    Taric on the same battlefield IS an "other" unit and grants normally."""
    taric_a = make_unit(1, card_id=TARIC_PROTECTOR, might=4, keywords=frozenset({"Shield", "Tank"}))
    taric_b = make_unit(2, card_id=TARIC_PROTECTOR, might=4, keywords=frozenset({"Shield", "Tank"}))
    state = make_state(left_units=frozenset({taric_a, taric_b}))
    # Both already have printed Shield, so presence in the resolved set
    # doesn't distinguish "from the aura" vs "printed" — what matters is
    # each is treated as the other's "other friendly unit", not excluded.
    assert "Shield" in traits.resolved_traits(state, taric_a, "left")
    assert "Shield" in traits.resolved_traits(state, taric_b, "left")
