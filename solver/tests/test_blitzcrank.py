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


def make_root(enemy_might=3, ally_might=1):
    """"left" holds an ally of ours, which is what makes it a legal
    PlayUnit target (rule 355.7/355.8: you may only play to a battlefield
    you have UNITS on); "right" holds one enemy unit as the redirect
    target.

    The ally is not optional set dressing. An earlier version of this
    fixture defaulted to no ally and just set controller=0, giving a
    battlefield controlled-but-empty — a state no real line can produce,
    since every path that empties a battlefield also clears its
    controller. Playing Blitzcrank there was only ever legal against that
    impossible position."""
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
    """Enemy Might 3 redirected onto "left", where Blitzcrank (Might 5)
    lands beside our ally: our combined pool kills it outright no matter
    how it assigns its own damage, and Blitzcrank is too big for Might 3
    to kill back. Direct mechanics check (not a full puzzle - no win
    condition is set up here, that's the actual puzzle's job): confirms
    the redirect really moves the enemy unit, triggers real combat with
    us as Defender, and resolves through the genuine action-generation
    path rather than the synthetic construction test_combat.py uses.

    Asserted across EVERY outcome rather than assuming a single one: the
    enemy still gets to choose whom to damage, so the branch count is its
    business - what matters is that the redirect removes it regardless.
    """
    from solver.engine import abilities

    root = make_root(enemy_might=3)
    cards = {BLITZCRANK_IMPASSIVE: BLITZCRANK_CARD}
    triggered = [
        a for a in legal_actions(root, cards)
        if isinstance(a, PlayUnit) and a.card_id == BLITZCRANK_IMPASSIVE and a.trigger_params
    ]
    assert triggered
    action = triggered[0]

    outcomes = abilities.resolve_unit_play_trigger_outcomes(root, action, BLITZCRANK_CARD)
    assert outcomes
    for result in outcomes:
        left = result.battlefields[0]
        right = result.battlefields[1]
        assert not any(u.controller == 1 for u in left.units)  # enemy dead, no longer at "left"
        assert any(u.controller == 0 and u.might == 5 for u in left.units)  # Blitzcrank survived
        assert right.units == frozenset()  # "right" now empty
        assert left.controller == 0


def _ally_outcomes(root, card):
    """Whether the enemy's possible responses include the fragile ally
    surviving, dying, or both — across every generated redirect."""
    from solver.engine import abilities

    cards = {BLITZCRANK_IMPASSIVE: card}
    triggered = [
        a for a in legal_actions(root, cards)
        if isinstance(a, PlayUnit) and a.card_id == BLITZCRANK_IMPASSIVE and a.trigger_params
    ]
    assert triggered
    survived = died = False
    for action in triggered:
        for outcome in abilities.resolve_unit_play_trigger_outcomes(root, action, card):
            if 10 in {u.instance_id for u in outcome.battlefields[0].units}:
                survived = True
            else:
                died = True
    return survived, died


def test_tank_removes_the_opponents_choice_in_the_redirect():
    """This test used to assert the opposite, and was right to until
    [Tank] was implemented.

    A fragile ally (Might 1) stands where Blitzcrank lands. The redirected
    enemy (Might 4) has pool enough to kill either. Without Tank that is a
    real fork — kill the ally, or dump it all on Blitzcrank — and this
    test existed to prove the REAL generation path produces a multi-outcome
    AND-node rather than only the synthetic one in test_combat.py.

    Blitzcrank prints [Tank]: "I must be assigned combat damage first."
    So the fork was never legal Riftbound; it only existed because
    combat.py ignored Tank entirely. With the ordering enforced the enemy
    has exactly one option, and the ally is protected.
    """
    survived, died = _ally_outcomes(make_root(enemy_might=4, ally_might=1), BLITZCRANK_CARD)
    assert survived and not died


def test_without_tank_the_same_redirect_is_a_genuine_fork():
    """The contrast, so the AND-node coverage this file used to provide
    isn't silently lost: strip Tank from the same body and the opponent's
    choice reappears, proving real action generation still produces
    multi-outcome adversarial nodes."""
    no_tank = CardDef(card_id=BLITZCRANK_IMPASSIVE, card_type="Unit", energy_cost=0,
                       power_cost=0, might=5, keywords=frozenset())
    survived, died = _ally_outcomes(make_root(enemy_might=4, ally_might=1), no_tank)
    assert survived and died
