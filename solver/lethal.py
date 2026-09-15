"""The MVP entry point: given a board of Origins cards, is there lethal?

Three outcomes, deliberately kept distinct:

    lethal        — a winning line exists; `strategy` holds it
    no_lethal     — searched to `max_depth` and there is none
    unanswerable  — the board contains cards the engine doesn't model,
                    so neither of the above can be claimed honestly

That third one is the whole point. `solve()` on its own cannot tell
"there is no lethal" apart from "there is no lethal *among the rules I
happen to implement*", and with 298 cards in Origins and a couple of
dozen modelled, the second is overwhelmingly the common case. Collapsing
them produces confident wrong answers that are indistinguishable from
right ones — see engine/coverage.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .engine import coverage
from .engine.cards import CardDef
from .engine.state import GameState
from .search import Strategy, solve

Outcome = Literal["lethal", "no_lethal", "unanswerable"]


@dataclass(frozen=True)
class LethalAnswer:
    outcome: Outcome
    strategy: Optional[Strategy] = None
    # One human-readable reason per unmodelled card, naming the card and
    # quoting its printed text. Only populated when unanswerable.
    blocking: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        """Truthy only for an actual lethal — so `if find_lethal(...)`
        can never be accidentally satisfied by an unanswerable board."""
        return self.outcome == "lethal"


def find_lethal(state: GameState, cards: dict[str, CardDef], max_depth: int = 6,
                 ignore_unmodelled: bool = False) -> LethalAnswer:
    """Answer the lethal question for `state`, refusing rather than
    guessing when the board contains cards the engine can't model.

    `ignore_unmodelled=True` forces a search anyway, for the cases where
    the caller genuinely knows the unmodelled text can't matter — the
    hand-authored puzzles, whose positions were built against the engine's
    own subset. It is deliberately opt-in and named for what it costs.
    """
    if not ignore_unmodelled:
        blocking = coverage.blocking_cards(state)
        if blocking:
            return LethalAnswer(outcome="unanswerable", blocking=tuple(blocking))

    strategy = solve(state, cards, max_depth=max_depth)
    if strategy is None:
        return LethalAnswer(outcome="no_lethal")
    return LethalAnswer(outcome="lethal", strategy=strategy)
