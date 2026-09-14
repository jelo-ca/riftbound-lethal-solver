"""Scoring: Conquer/Hold's Final Point restriction and card-effect points.
See design/04-scoring-rules.md. This is the module the whole project's
correctness rests on (per the existing 6-week plan's kill criteria) — every
branch here is cited to a rule number, not a paraphrase.

Scope note: this module does not model a deck, so "draw a card instead"
(rule 476.1, when the Final Point restriction blocks a Conquer) has no
representable effect here beyond "no point granted" — which is the only
consequence that matters for solving. Hold is not modeled here at all: it's
pre-resolved into the puzzle's starting position (design/02-state-model.md)
because it happens during the Beginning Phase, before the puzzle's live
turn begins.
"""

from __future__ import annotations

import dataclasses

from .state import GameState, replace_player

VICTORY_SCORE = 8  # rule 198.1. v0 puzzles don't use battlefield effects
                     # that alter this (design/07-scope-and-cut-list.md).


def held_battlefields(state: GameState) -> frozenset[str]:
    """The battlefields `state.turn_player` currently controls."""
    return frozenset(bf.battlefield_id for bf in state.battlefields
                      if bf.controller == state.turn_player)


def unseeded_holds(state: GameState) -> frozenset[str]:
    """Battlefields the turn player controls that are NOT recorded as
    scored this turn — i.e. the ways `state` violates the Hold invariant.
    Empty for a well-formed position.

    The invariant: mid-turn, every battlefield the turn player controls
    has already scored for them this turn. Either they held it at the
    start of the turn (a Hold point in the Beginning Phase, pre-resolved
    into the starting position — see this module's docstring) or they
    took it during this turn (a Conquer point). There is no third way to
    be standing on a battlefield, and rule 471.1.b caps it at one point
    per battlefield per player per turn, so control implies spent.

    The consequence this exists to prevent: without it, a player could
    walk their last unit off a battlefield they control (rule 468 makes
    it Uncontrolled) and walk another unit back in for a "fresh" Conquer
    — a revolving door minting a point per round trip. Puzzles 7 and 8
    were both built on exactly that and had to be withdrawn.

    Deliberately one-directional. `scored_this_turn` may legitimately
    contain battlefields the turn player does NOT control: one conquered
    earlier this turn and since lost stays scored (rule 471.1.b — puzzle
    4 is built on that), as does one merely held at turn start and
    subsequently taken by the opponent.
    """
    return held_battlefields(state) - state.scored_this_turn


def resolve_conquer(state: GameState, battlefield_id: str) -> GameState:
    """Given a state where `state.turn_player` just established control at
    `battlefield_id` (board mechanics already applied by actions.py — this
    function does not touch unit/battlefield-control fields), resolve the
    scoring consequences and return the updated state.

    rule 471.1.b: a battlefield can only be Scored once per player per
    turn. If it's already in `scored_this_turn`, establishing control again
    is a no-op for points (the reconquer-for-an-extra-point idea from
    08-puzzle-concepts.md's "rejected mechanics" section).
    """
    if battlefield_id in state.scored_this_turn:
        return state

    player_index = state.turn_player
    player = state.players[player_index]
    new_scored_this_turn = state.scored_this_turn | {battlefield_id}

    # rule 474/475: "current Point Total is 1 point from Victory Score or
    # higher" gates the Final Point restriction.
    is_final_point_attempt = player.score >= VICTORY_SCORE - 1

    if not is_final_point_attempt:
        new_player = dataclasses.replace(player, score=player.score + 1)
        state = replace_player(state, player_index, new_player)
        return dataclasses.replace(state, scored_this_turn=new_scored_this_turn)

    # rule 476: only gain the Final Point if every battlefield has been
    # Scored this turn (Conquer OR Hold — Hold entries are already seeded
    # into scored_this_turn as part of the starting position).
    all_battlefield_ids = {bf.battlefield_id for bf in state.battlefields}
    if new_scored_this_turn >= all_battlefield_ids:
        new_player = dataclasses.replace(player, score=player.score + 1)
        state = replace_player(state, player_index, new_player)
        return dataclasses.replace(state, scored_this_turn=new_scored_this_turn)

    # rule 476.1: draw a card instead. No deck modeled — the only
    # solving-relevant consequence is "no point," so just mark the
    # battlefield Scored (rule 471.1.b still applies going forward this
    # turn) without changing score.
    return dataclasses.replace(state, scored_this_turn=new_scored_this_turn)


def resolve_control_change(state: GameState, new_state: GameState, battlefield_id: str) -> GameState:
    """If `battlefield_id`'s controller changed to `state.turn_player`
    between `state` and `new_state`, resolve the scoring consequences via
    resolve_conquer. Shared by every action/effect that can establish
    control (PlayUnit's open-battlefield deploy, MoveUnit, and spell
    effects like Ride The Wind that relocate a unit — see search.py and
    abilities.py), so the same rule 469.1 check happens exactly once
    regardless of which board mechanic produced the control change.
    """
    turn_player = state.turn_player
    old_controller = next(bf.controller for bf in state.battlefields if bf.battlefield_id == battlefield_id)
    if old_controller == turn_player:
        return new_state
    new_bf = next(bf for bf in new_state.battlefields if bf.battlefield_id == battlefield_id)
    if new_bf.controller != turn_player:
        return new_state
    return resolve_conquer(new_state, battlefield_id)


def grant_card_effect_point(state: GameState) -> GameState:
    """rule 473: points gained from sources that are not Conquer (card
    effects) are not subject to the Final Point restriction, and per the
    Scoring definition (rule 469.1/471) they aren't `Scoring` at all — no
    interaction with `scored_this_turn`.
    """
    player_index = state.turn_player
    player = state.players[player_index]
    new_player = dataclasses.replace(player, score=player.score + 1)
    return replace_player(state, player_index, new_player)


def is_winning(state: GameState) -> bool:
    """rule 194.4: a player wins if their points are >= Victory Score and
    greater than any opponent's. v0 has a tapped-out, non-scoring opponent
    within the puzzle's single turn, so the turn player crossing the
    threshold is sufficient as long as the opponent's starting score is
    below it — a puzzle-authoring invariant, not enforced here.
    """
    return state.players[state.turn_player].score >= VICTORY_SCORE
