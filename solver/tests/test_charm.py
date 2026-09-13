from solver.engine import abilities
from solver.engine.abilities import CHARM, is_legal_play_spell
from solver.engine.actions import PlaySpell, RunePayment
from solver.engine.cards import CardDef
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from solver.search import legal_actions, solve

CHARM_CARD = CardDef(card_id=CHARM, card_type="Spell", energy_cost=1,
                      power_cost=1, power_domain="Calm", keywords=frozenset())
CHARM_PAYMENT = RunePayment(energy_runes=("Fury",), power_runes=("Calm",))


def make_unit(instance_id, controller, might=2, keywords=frozenset(), exhausted=False):
    return UnitInstance(card_id="enemy" if controller == 1 else "ogn-010-298",
                         instance_id=instance_id, controller=controller, might=might,
                         keywords=keywords, exhausted=exhausted, damage=0, is_token=False)


def _root(left_units=frozenset(), right_units=frozenset(), left_ctrl=None, right_ctrl=None):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(CHARM,), runes=RunePool(available=("Fury", "Calm")), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", left_ctrl, left_units, None),
            BattlefieldState("right", right_ctrl, right_units, None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def test_charm_moves_an_enemy_unit_to_an_empty_battlefield_no_combat():
    enemy = make_unit(1, controller=1)
    root = _root(left_units=frozenset({enemy}), left_ctrl=1)
    action = PlaySpell(card_id=CHARM, params=(1, "right"), rune_payment=CHARM_PAYMENT)
    assert is_legal_play_spell(root, action, CHARM_CARD)

    outcomes = abilities.resolve_spell_outcomes(root, action, CHARM_CARD)
    assert len(outcomes) == 1
    new_state = outcomes[0]
    assert new_state.battlefields[0].units == frozenset()
    assert new_state.battlefields[0].controller is None
    assert next(iter(new_state.battlefields[1].units)).instance_id == 1
    assert new_state.battlefields[1].controller == 1


def test_charm_redirect_into_our_ground_triggers_combat_we_are_defender():
    enemy = make_unit(1, controller=1, might=3)
    ours = make_unit(2, controller=0, might=5)
    root = _root(left_units=frozenset({enemy}), left_ctrl=1, right_units=frozenset({ours}), right_ctrl=0)
    action = PlaySpell(card_id=CHARM, params=(1, "right", ((1, 3),)), rune_payment=CHARM_PAYMENT)
    assert is_legal_play_spell(root, action, CHARM_CARD)

    outcomes = abilities.resolve_spell_outcomes(root, action, CHARM_CARD)
    assert len(outcomes) == 1  # our unit (might 5) alone as defender - one opponent response
    new_state = outcomes[0]
    right = new_state.battlefields[1]
    assert right.controller == 0  # our unit (might 5) survives, enemy (might 3) dies
    assert len(right.units) == 1
    assert next(iter(right.units)).controller == 0


def test_charm_cannot_target_a_friendly_unit():
    friendly = make_unit(1, controller=0)
    root = _root(left_units=frozenset({friendly}), left_ctrl=0)
    action = PlaySpell(card_id=CHARM, params=(1, "right"), rune_payment=CHARM_PAYMENT)
    assert not is_legal_play_spell(root, action, CHARM_CARD)


def test_charm_cannot_target_a_zone_the_unit_is_already_in():
    enemy = make_unit(1, controller=1)
    root = _root(left_units=frozenset({enemy}), left_ctrl=1)
    action = PlaySpell(card_id=CHARM, params=(1, "left"), rune_payment=CHARM_PAYMENT)
    assert not is_legal_play_spell(root, action, CHARM_CARD)


def test_charm_appears_in_legal_actions_when_affordable():
    enemy = make_unit(1, controller=1)
    root = _root(left_units=frozenset({enemy}), left_ctrl=1)
    cards = {CHARM: CHARM_CARD}
    actions = legal_actions(root, cards)
    charm_actions = [a for a in actions if isinstance(a, PlaySpell) and a.card_id == CHARM]
    assert any(a.params[0] == 1 and a.params[1] == "right" for a in charm_actions)


def test_charm_redirect_denies_opponent_when_our_defender_would_die():
    """Mirrors test_combat.py's AND-node proof, but reached through Charm
    (a spell) instead of a unit's own Standard Move — confirms PlaySpell
    genuinely routes through the AND-node now, not just deterministic
    spells. Our lone defender (Might 2) dies to the redirected enemy
    (Might 3) regardless of our assignment choice, so redirecting should
    never be part of a winning solve() line here."""
    enemy = make_unit(1, controller=1, might=3)
    ours = make_unit(2, controller=0, might=2)
    root = _root(left_units=frozenset({enemy}), left_ctrl=1, right_units=frozenset({ours}), right_ctrl=0)
    cards = {CHARM: CHARM_CARD}
    assert solve(root, cards, max_depth=2) is None
