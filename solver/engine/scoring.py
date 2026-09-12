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
