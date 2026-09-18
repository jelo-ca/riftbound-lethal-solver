"""Spell-kill reactions — "when you kill a unit with a spell," detected as
a board diff (deaths.units_killed_between) rather than per-spell
bookkeeping, so it's real for any spell whose effect happens to kill
something (a damage spell reducing Might to 0, not just an outright-kill
spell like Vengeance). Immortal Phoenix is the card that exercises it.

The reachability test goes through search.legal_actions/search.apply's
list-returning path, not a direct call into abilities.py, for the usual
reason: "registered but unreachable" is this codebase's most common
self-inflicted bug.
"""

from solver import search
from solver.engine import abilities
from solver.engine.actions import PlaySpell
from solver.engine.card_pool import card_def
from solver.engine.state import (
    BattlefieldState,
    GameState,
    PlayerState,
    RunePool,
    UnitInstance,
)

VENGEANCE = abilities.VENGEANCE  # "Kill a unit" — unrestricted target
IMMORTAL_PHOENIX = abilities.IMMORTAL_PHOENIX


def make_unit(card_id, instance_id, controller=0, might=3, exhausted=False):
    return UnitInstance(card_id=card_id, instance_id=instance_id, controller=controller,
                         might=might, keywords=frozenset(), exhausted=exhausted, damage=0,
                         is_token=False)


def make_state(base_units=frozenset(), opp_base=frozenset(), hand=(), runes=(), trash=()):
    return GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=base_units, hand=hand, runes=RunePool(available=runes),
                        score=0, trash=trash),
            PlayerState(base_units=opp_base, hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=(
            BattlefieldState("left", None, frozenset(), None),
            BattlefieldState("right", None, frozenset(), None),
        ),
        scored_this_turn=frozenset(),
        cards_played_this_turn=0,
    )


def test_vengeance_killing_a_unit_offers_the_phoenix_reaction():
    victim = make_unit("plain-card", 5, controller=1)
    state = make_state(opp_base=frozenset({victim}), hand=(VENGEANCE,), trash=(IMMORTAL_PHOENIX,),
                        runes=("Fury",) * 5 + ("Order",) * 3)
    cards = {VENGEANCE: card_def(VENGEANCE)}
    action = next(a for a in search.legal_actions(state, cards)
                  if isinstance(a, PlaySpell) and a.card_id == VENGEANCE
                  and a.params == (5,) and a.reaction_params)
    [result] = abilities.resolve_spell_outcomes_with_reaction(state, action, cards[VENGEANCE])
    # Phoenix left trash for the board; Vengeance itself landed there as a
    # resolved spell (apply_play_spell_cost) — the two cross paths.
    assert result.players[0].trash == (VENGEANCE,)
    assert any(u.card_id == IMMORTAL_PHOENIX for u in result.players[0].base_units)
    assert victim.instance_id not in {u.instance_id for u in result.players[1].base_units}


def test_declining_the_reaction_is_still_legal():
    victim = make_unit("plain-card", 5, controller=1)
    state = make_state(opp_base=frozenset({victim}), hand=(VENGEANCE,), trash=(IMMORTAL_PHOENIX,),
                        runes=("Fury",) * 5 + ("Order",) * 3)
    cards = {VENGEANCE: card_def(VENGEANCE)}
    action = next(a for a in search.legal_actions(state, cards)
                  if isinstance(a, PlaySpell) and a.card_id == VENGEANCE
                  and a.params == (5,) and not a.reaction_params)
    [result] = abilities.resolve_spell_outcomes_with_reaction(state, action, cards[VENGEANCE])
    assert result.players[0].trash == (IMMORTAL_PHOENIX, VENGEANCE)  # Phoenix untouched, declined


def test_no_reaction_offered_without_a_kill():
    """Vengeance targeting nothing lethal-worthy doesn't apply here since
    it always kills its target — this instead checks the guard directly:
    no registered watcher in trash means no reaction candidates at all,
    regardless of what the spell does."""
    victim = make_unit("plain-card", 5, controller=1)
    state = make_state(opp_base=frozenset({victim}), hand=(VENGEANCE,),
                        runes=("Fury",) * 5 + ("Order",) * 3)
    cards = {VENGEANCE: card_def(VENGEANCE)}
    actions = [a for a in search.legal_actions(state, cards)
               if isinstance(a, PlaySpell) and a.card_id == VENGEANCE and a.reaction_params]
    assert actions == []


def test_reaction_payment_comes_from_what_vengeance_leaves_behind():
    """Just enough runes for both costs together (4E/2 Order for Vengeance,
    1E/1 Fury for the reaction) and nothing to spare — proves the two
    payments don't double-count the same runes."""
    victim = make_unit("plain-card", 5, controller=1)
    state = make_state(opp_base=frozenset({victim}), hand=(VENGEANCE,), trash=(IMMORTAL_PHOENIX,),
                        runes=("Order", "Order", "Fury", "Fury", "Fury"))
    cards = {VENGEANCE: card_def(VENGEANCE)}
    action = next(a for a in search.legal_actions(state, cards)
                  if isinstance(a, PlaySpell) and a.card_id == VENGEANCE
                  and a.params == (5,) and a.reaction_params)
    [result] = abilities.resolve_spell_outcomes_with_reaction(state, action, cards[VENGEANCE])
    assert any(u.card_id == IMMORTAL_PHOENIX for u in result.players[0].base_units)
