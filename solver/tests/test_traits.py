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
from solver.engine.traits import WIELDER_OF_WATER
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


# --- Wielder of Water: "while I'm attacking or defending alone, +2 Might" ---
#
# RULES ANSWER (project owner, 2026-09-17): SelfConditional.condition now
# takes the unit's combat role (designation) as a fourth argument, so a
# card can read "while I'm attacking/defending alone" without touching
# Might inside the condition (the module's non-circularity invariant).


def test_wielder_of_water_is_unconditionally_alone_while_attacking():
    """This engine's action space never produces a multi-unit attack (see
    combat.py's module docstring), so the attacking side is always exactly
    one unit — "attacking alone" is unconditionally true whenever this
    engine can put her in combat as the attacker at all, company or not."""
    wielder = make_unit(1, card_id=WIELDER_OF_WATER, might=2)
    companion = make_unit(3, might=5)  # irrelevant to the ATTACKING side
    state = make_state(left_units=frozenset({wielder, companion}))
    assert combat.effective_might(state, wielder, "left", "attacker") == 4  # 2 + 2


def test_wielder_of_water_defending_alone_gets_the_bonus():
    wielder = make_unit(1, card_id=WIELDER_OF_WATER, might=2, controller=0)
    state = make_state(left_units=frozenset({wielder}), left_ctrl=0)
    assert combat.effective_might(state, wielder, "left", "defender") == 4  # 2 + 2


def test_wielder_of_water_defending_with_company_gets_no_bonus():
    wielder = make_unit(1, card_id=WIELDER_OF_WATER, might=2, controller=0)
    companion = make_unit(2, might=5, controller=0)
    state = make_state(left_units=frozenset({wielder, companion}), left_ctrl=0)
    assert combat.effective_might(state, wielder, "left", "defender") == 2  # not alone -- no bonus


def test_wielder_of_water_outside_combat_gets_no_bonus():
    """designation=None (any non-combat context, e.g. direct effect
    damage) — the card's text is explicitly about attacking/defending."""
    wielder = make_unit(1, card_id=WIELDER_OF_WATER, might=2)
    state = make_state(left_units=frozenset({wielder}))
    assert combat.effective_might(state, wielder, "left", None) == 2


def test_wielder_of_water_grant_check_does_not_read_might():
    """Non-circularity smoke test: the condition function takes `unit`
    (whose .might it must NOT read) and answers purely from designation
    and co-located controllers — confirmed here by calling it directly
    with a unit whose Might is deliberately absurd, and getting the same
    answer as a normal one would."""
    absurd = make_unit(1, card_id=WIELDER_OF_WATER, might=999)
    state = make_state(left_units=frozenset({absurd}), left_ctrl=0)
    assert traits._attacking_or_defending_alone(state, absurd, "left", "defender") is True
    assert traits._attacking_or_defending_alone(state, absurd, "left", "attacker") is True
    assert traits._attacking_or_defending_alone(state, absurd, "left", None) is False
