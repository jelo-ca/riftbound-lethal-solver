from solver.engine.abilities import BLITZCRANK_IMPASSIVE, is_legal_unit_play_trigger
from solver.engine.actions import PlayUnit, RunePayment
from solver.engine.cards import CardDef
from solver.engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance
from solver.search import legal_actions

BLITZCRANK_CARD = CardDef(card_id=BLITZCRANK_IMPASSIVE, card_type="Unit", energy_cost=0,
                           power_cost=0, might=5, keywords=frozenset({"Tank"}))


def make_unit(card_id, instance_id, controller=0, might=3, keywords=frozenset(), exhausted=False):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=keywords, exhausted=exhausted, damage=0, is_token=False)


def make_root(enemy_might=3, ally_might=None):
    """"left" is ours (an existing ally there), open enough to play
    Blitzcrank into; "right" holds one enemy unit for the redirect
    target."""
    units_at_left = set()
    if ally_might is not None:
        units_at_left.add(make_unit("ally", 10, controller=0, might=ally_might))
    enemy = make_unit("enemy", 20, controller=1, might=enemy_might)
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(), hand=(BLITZCRANK_IMPASSIVE,),
                        runes=RunePool(available=()), score=0),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", 0, frozenset(units_at_left), None),
            BattlefieldState("right", 1, frozenset({enemy}), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def test_declining_the_trigger_is_always_legal():
    root = make_root()
    action = PlayUnit(card_id=BLITZCRANK_IMPASSIVE, target_zone="left",
                       rune_payment=RunePayment(energy_runes=(), power_runes=()), trigger_params=())
    assert is_legal_unit_play_trigger(root, action, BLITZCRANK_CARD)


def test_redirect_candidates_appear_in_legal_actions():
    root = make_root()
    cards = {BLITZCRANK_IMPASSIVE: BLITZCRANK_CARD}
    actions = legal_actions(root, cards)
    triggered = [a for a in actions if isinstance(a, PlayUnit) and a.card_id == BLITZCRANK_IMPASSIVE and a.trigger_params]
    assert len(triggered) >= 1
    assert all(a.trigger_params[0] == 20 for a in triggered)  # the enemy unit at "right"


def test_redirect_causes_combat_we_are_defender_and_kill_the_weak_enemy():
    """Enemy Might 3 vs our Blitzcrank (Might 5, alone at "left" once
    played): we easily kill it, it can't kill Blitzcrank back (3 < 5).
    Direct mechanics check (not a full puzzle - no win condition is set
    up here, that's the actual puzzle's job): confirms the redirect
    really moves the enemy unit, triggers real combat with us as
    Defender, and resolves correctly through the genuine action-
    generation path (not the synthetic construction test_combat.py uses).
    """
    from solver.engine import abilities

    root = make_root(enemy_might=3)
    cards = {BLITZCRANK_IMPASSIVE: BLITZCRANK_CARD}
    triggered = [
        a for a in legal_actions(root, cards)
        if isinstance(a, PlayUnit) and a.card_id == BLITZCRANK_IMPASSIVE and a.trigger_params
    ]
    assert len(triggered) == 1  # single enemy unit, single our_assignment option (kill it, 5 > 3)
    action = triggered[0]

    outcomes = abilities.resolve_unit_play_trigger_outcomes(root, action, BLITZCRANK_CARD)
    assert len(outcomes) == 1  # enemy Might 3 has only one place to put its damage (Blitzcrank alone)
    result = outcomes[0]

    left = result.battlefields[0]
    right = result.battlefields[1]
    assert not any(u.controller == 1 for u in left.units)  # enemy dead, no longer at "left"
    assert any(u.controller == 0 and u.might == 5 for u in left.units)  # Blitzcrank survived
    assert right.units == frozenset()  # "right" now empty
    assert left.controller == 0


def test_redirect_produces_a_genuine_opponent_choice_via_real_generation():
    """A fragile ally (Might 1) is already at "left" alongside where
    Blitzcrank will land. Once redirected there, the enemy unit (Might 4,
    pool enough to fully lethal either target) can choose to kill the
    fragile ally OR dump its damage on Blitzcrank instead (never both:
    lethal-first means committing to one). This proves the REAL
    Blitzcrank generation path produces a genuine multi-outcome AND-node
    (not just the synthetic one test_combat.py constructs directly) -
    the actual adversarial search over these outcomes is already proven
    correct there.
    """
    from solver.engine import abilities

    root = make_root(enemy_might=4, ally_might=1)
    cards = {BLITZCRANK_IMPASSIVE: BLITZCRANK_CARD}
    triggered = [
        a for a in legal_actions(root, cards)
        if isinstance(a, PlayUnit) and a.card_id == BLITZCRANK_IMPASSIVE and a.trigger_params
    ]
    assert triggered

    # Across all of our (defender) assignment candidates, the enemy's
    # possible responses must include both "ally dies, Blitzcrank fine"
    # and "Blitzcrank takes it, ally survives" for at least one of them -
    # i.e. a genuine choice exists somewhere in the generated action set.
    saw_ally_death = False
    saw_ally_survival = False
    for action in triggered:
        outcomes = abilities.resolve_unit_play_trigger_outcomes(root, action, BLITZCRANK_CARD)
        for outcome in outcomes:
            left_controllers_and_ids = {u.instance_id for u in outcome.battlefields[0].units}
            if 10 in left_controllers_and_ids:
                saw_ally_survival = True
            else:
                saw_ally_death = True
    assert saw_ally_death and saw_ally_survival
