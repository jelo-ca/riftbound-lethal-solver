"""[Hidden]-related cards where Hidden itself is irrelevant to whether
the engine understands the card: each one below also carries an ordinary
[Action] speed marker, or has a "when you play me" trigger that fires the
same regardless of how the card was played, so it's simply cast/played at
its printed cost like any other card. [Hidden] is established as never
worth using (coverage.py) — nothing here re-litigates that; it only
verifies the OTHER clause each card prints.
"""

from solver.engine import abilities
from solver.engine.abilities import (
    BLOCK,
    HIDDEN_BLADE,
    TEEMO_SCOUT,
    is_legal_unit_play_trigger,
    resolve_unit_play_trigger_outcomes,
)
from solver.engine.actions import PlaySpell, PlayUnit, RunePayment
from solver.engine.card_pool import card_def
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from solver.search import legal_actions


def unit(instance_id, controller=0, might=3, card_id="u", keywords=frozenset()):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=keywords, exhausted=False, damage=0, is_token=False)


def state_with(left=frozenset(), base=frozenset(), hand=(), runes=("Fury",) * 12):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base, hand=hand, runes=RunePool(available=runes), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, left, None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def cast(card_id, params, state):
    card = card_def(card_id)
    payment = RunePayment(energy_runes=("Fury",) * card.energy_cost,
                          power_runes=(card.power_domain,) * card.power_cost)
    action = PlaySpell(card_id=card_id, params=params, rune_payment=payment)
    return abilities.resolve_spell_outcomes(state, action, card)[0]


# --- Block ---


def test_block_grants_shield_3_and_tank():
    st = state_with(left=frozenset({unit(1, might=2)}), hand=(BLOCK,), runes=("Calm",) * 2)
    out = cast(BLOCK, (1,), st)
    target = next(u for u in out.battlefields[0].units if u.instance_id == 1)
    assert "Shield 3" in target.keywords
    assert "Tank" in target.keywords


# --- Hidden Blade ---


def test_hidden_blade_kills_its_target():
    st = state_with(left=frozenset({unit(1, might=3)}), hand=(HIDDEN_BLADE,),
                     runes=("Order",) * 3)
    out = cast(HIDDEN_BLADE, (1,), st)
    assert 1 not in {u.instance_id for u in out.battlefields[0].units}


# --- Teemo, Scout ---


def _teemo_action(root):
    card = card_def(TEEMO_SCOUT)
    payment = RunePayment(energy_runes=("Chaos",) * card.energy_cost, power_runes=())
    return PlayUnit(card_id=TEEMO_SCOUT, target_zone="base", rune_payment=payment,
                     trigger_params=("buff",))


def test_teemo_scout_buffs_itself_three_might_on_play():
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(TEEMO_SCOUT,),
                        runes=RunePool(available=("Chaos", "Chaos")), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    card = card_def(TEEMO_SCOUT)
    action = _teemo_action(root)
    assert is_legal_unit_play_trigger(root, action, card)
    outcomes = resolve_unit_play_trigger_outcomes(root, action, card)
    assert len(outcomes) == 1
    teemo = next(u for u in outcomes[0].players[0].base_units)
    assert teemo.might == card.might + 3


def test_teemo_scout_only_the_triggered_form_is_a_legal_action():
    """Mandatory ("when you play me" isn't "you may") — the bare
    trigger_params=() PlayUnit must not survive, proving the mechanism is
    reachable end-to-end through search.legal_actions."""
    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(TEEMO_SCOUT,),
                        runes=RunePool(available=("Chaos", "Chaos")), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )
    cards = {TEEMO_SCOUT: card_def(TEEMO_SCOUT)}
    play_unit_actions = [a for a in legal_actions(root, cards) if isinstance(a, PlayUnit)]
    assert len(play_unit_actions) == 1
    assert play_unit_actions[0].trigger_params == ("buff",)
