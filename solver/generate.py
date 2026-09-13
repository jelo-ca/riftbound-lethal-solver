"""Puzzle generation pipeline: sample -> solve -> filter. See
design/10-generation-pipeline.md.

Samples random single-turn positions from the verified card pool (plain
vanilla stat-sticks, two Assault/Shield keyword vanillas, Sneaky
Deckhand, and the cards with registered mechanics — everything else is
unregistered and simply can't be sampled), keeps only positions that are
solvable, long enough (>=4 actions), have EXACTLY one correct line, and
use every rune, then exports survivors through the same export.py used
for the hand-authored puzzles.

Run with: python -m solver.generate --count 5
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import random
from pathlib import Path
from typing import Optional

from .engine.abilities import (
    BLITZCRANK_IMPASSIVE,
    CAITLYN_PATROLLING,
    CHARM,
    RIDE_THE_WIND,
    VENGEANCE,
    YASUO_WINDRIDER,
)
from .engine.battlefields import REGISTERED as BATTLEFIELD_EFFECTS
from .engine.cards import CardDef
from .engine.state import BattlefieldState, GameState, PlayerState, RunePool, UnitInstance, canonical_key
from .export import export_puzzle, resolve_action_outcomes
from .maneuvers import Signature, is_duplicate, load_registry, maneuver_signature
from .search import Strategy, count_winning_strategies, solve

OUTPUT_DIR = Path(__file__).parent.parent / "puzzles" / "generated"

# --- Verified card pool (design/10-generation-pipeline.md) -----------------

LEGION_REARGUARD = "ogn-010-298"
FAITHFUL_MANUFACTOR = "ogn-211-298"
VANGUARD_CAPTAIN = "ogn-218-298"
SNEAKY_DECKHAND = "ogn-176-298"
DARING_PORO = "ogn-210-298"
STALWART_PORO = "ogn-052-298"

CARD_POOL: dict[str, CardDef] = {
    LEGION_REARGUARD: CardDef(card_id=LEGION_REARGUARD, card_type="Unit", energy_cost=2,
                               power_cost=0, might=2, keywords=frozenset()),
    FAITHFUL_MANUFACTOR: CardDef(card_id=FAITHFUL_MANUFACTOR, card_type="Unit", energy_cost=2,
                                  power_cost=0, might=2, keywords=frozenset()),
    VANGUARD_CAPTAIN: CardDef(card_id=VANGUARD_CAPTAIN, card_type="Unit", energy_cost=2,
                               power_cost=1, power_domain="Order", might=3, keywords=frozenset()),
    SNEAKY_DECKHAND: CardDef(card_id=SNEAKY_DECKHAND, card_type="Unit", energy_cost=3,
                              power_cost=0, might=2, keywords=frozenset(),
                              can_play_to_open_battlefield=True),
    CAITLYN_PATROLLING: CardDef(card_id=CAITLYN_PATROLLING, card_type="Unit", energy_cost=3,
                                 power_cost=0, might=3, keywords=frozenset()),
    BLITZCRANK_IMPASSIVE: CardDef(card_id=BLITZCRANK_IMPASSIVE, card_type="Unit", energy_cost=5,
                                   power_cost=0, might=5, keywords=frozenset({"Tank"})),
    YASUO_WINDRIDER: CardDef(card_id=YASUO_WINDRIDER, card_type="Unit", energy_cost=2,
                              power_cost=0, might=2, keywords=frozenset({"Ganking"})),
    RIDE_THE_WIND: CardDef(card_id=RIDE_THE_WIND, card_type="Spell", energy_cost=2,
                            power_cost=1, power_domain="Chaos", keywords=frozenset()),
    DARING_PORO: CardDef(card_id=DARING_PORO, card_type="Unit", energy_cost=2,
                          power_cost=0, might=2, keywords=frozenset({"Assault"})),
    STALWART_PORO: CardDef(card_id=STALWART_PORO, card_type="Unit", energy_cost=2,
                            power_cost=0, might=2, keywords=frozenset({"Shield"})),
    VENGEANCE: CardDef(card_id=VENGEANCE, card_type="Spell", energy_cost=4,
                        power_cost=2, power_domain="Order", keywords=frozenset()),
    CHARM: CardDef(card_id=CHARM, card_type="Spell", energy_cost=1,
                    power_cost=1, power_domain="Calm", keywords=frozenset()),
}

# Units that can be sampled onto the board (pre-placed) or into hand.
OUR_UNIT_POOL = [LEGION_REARGUARD, FAITHFUL_MANUFACTOR, VANGUARD_CAPTAIN,
                  SNEAKY_DECKHAND, CAITLYN_PATROLLING, BLITZCRANK_IMPASSIVE, YASUO_WINDRIDER,
                  DARING_PORO, STALWART_PORO]
# Cards played out of hand (design/10-generation-pipeline.md's card pool
# table) - the mechanic UNITS above are sampled pre-placed on the board
# instead, since nothing here samples units into hand yet (a real gap:
# Blitzcrank's redirect trigger, and any future on-play trigger like
# Zaunite Bouncer, can currently only fire in a HAND-authored puzzle,
# never a generated one, until that's added).
HAND_SPELL_POOL = [RIDE_THE_WIND, VENGEANCE, CHARM]

# Battlefield effects worth sampling (engine/battlefields.py's registered
# static ones) and how often a given battlefield carries one.
BATTLEFIELD_EFFECT_POOL = sorted(BATTLEFIELD_EFFECTS)
BATTLEFIELD_EFFECT_CHANCE = 0.3

STARTING_SCORE = 6  # design decision: forces a two-point turn, see doc
MIN_STRATEGY_SIZE = 4
MAX_SOLVE_DEPTH = 6
REQUIRED_SOLUTION_COUNT = 1  # tightened from a 1-3 range: exactly one correct line, no alternates
MAX_EXPORT_BYTES = 2 * 1024 * 1024
CARD_COPY_CAP = 3  # standard format: max 3 copies of the same card in a deck


def _sample_with_cap(rng: random.Random, pool: list[str], n: int, counts: dict[str, int]) -> list[str]:
    """Draws `n` card ids from `pool`, never letting any single card_id's
    running count in `counts` exceed CARD_COPY_CAP — `counts` is shared
    across both the board and hand draws for one position, since the cap
    is per-deck, not per-zone. Draws fewer than `n` if the pool is
    exhausted under the cap (never happens in practice at these sample
    sizes against a 7-card pool, but safe either way)."""
    result = []
    for _ in range(n):
        available = [c for c in pool if counts.get(c, 0) < CARD_COPY_CAP]
        if not available:
            break
        card_id = rng.choice(available)
        counts[card_id] = counts.get(card_id, 0) + 1
        result.append(card_id)
    return result


def _sample_hand_and_runes(rng: random.Random, card_counts: dict[str, int]) -> tuple[tuple[str, ...], RunePool]:
    num_hand = rng.randint(0, 2)
    hand = tuple(_sample_with_cap(rng, HAND_SPELL_POOL, num_hand, card_counts))

    total_energy = 0
    power_needs: dict[str, int] = {}
    for card_id in hand:
        card = CARD_POOL[card_id]
        total_energy += card.energy_cost
        if card.power_cost:
            power_needs[card.power_domain] = power_needs.get(card.power_domain, 0) + card.power_cost

    runes: list[str] = []
    for domain, count in power_needs.items():
        runes += [domain] * count
    runes += ["Fury"] * total_energy  # energy is domain-agnostic, any filler works
    return hand, RunePool(available=tuple(runes))


def sample_position(rng: random.Random) -> tuple[GameState, dict[str, CardDef]]:
    """One random single-turn position from the verified card pool. See
    design/10-generation-pipeline.md's "Sampling" section for the ranges
    used here and why."""
    battlefield_ids = ["left", "right"]
    scored_this_turn = frozenset({rng.choice(battlefield_ids)}) if rng.random() < 0.5 else frozenset()

    next_id = [1]

    def new_id() -> int:
        value = next_id[0]
        next_id[0] += 1
        return value

    card_counts: dict[str, int] = {}
    num_our_units = rng.randint(2, 4)
    remaining_our = _sample_with_cap(rng, OUR_UNIT_POOL, num_our_units, card_counts)
    used_card_ids = set(remaining_our)

    battlefields = []
    for bf_id in battlefield_ids:
        roll = rng.random()
        # A battlefield carries one of the registered static effects some of
        # the time (engine/battlefields.py) - these change combat math or
        # movement legality for whoever stands there, so they're a real
        # source of forced lines that no card in hand could produce.
        effect_id = rng.choice(BATTLEFIELD_EFFECT_POOL) if rng.random() < BATTLEFIELD_EFFECT_CHANCE else None
        if remaining_our and roll < 0.4:
            card_id = remaining_our.pop(0)
            card = CARD_POOL[card_id]
            # Never exhausted: Awaken readies every unit at turn start (rule
            # 315.4/431), and this position IS turn start - there's no
            # legitimate in-turn event that could have exhausted a unit
            # sitting at Base or a battlefield before the puzzle's own
            # first action. Only a freshly-PLAYED unit starts exhausted
            # (rule 143.4.a), which apply_play_unit already models.
            unit = UnitInstance(card_id=card_id, instance_id=new_id(), controller=0,
                                 might=card.might, keywords=card.keywords,
                                 exhausted=False, damage=0, is_token=False)
            battlefields.append(BattlefieldState(bf_id, 0, frozenset({unit}), effect_id))
        elif roll < 0.65:
            unit = UnitInstance(card_id="generic-opponent", instance_id=new_id(), controller=1,
                                 might=rng.randint(1, 5), keywords=frozenset(),
                                 exhausted=False, damage=0, is_token=False)
            battlefields.append(BattlefieldState(bf_id, 1, frozenset({unit}), effect_id))
        else:
            battlefields.append(BattlefieldState(bf_id, None, frozenset(), effect_id))

    our_base_units = []
    for card_id in remaining_our:
        card = CARD_POOL[card_id]
        our_base_units.append(UnitInstance(card_id=card_id, instance_id=new_id(), controller=0,
                                            might=card.might, keywords=card.keywords,
                                            exhausted=False, damage=0, is_token=False))

    hand, runes = _sample_hand_and_runes(rng, card_counts)
    used_card_ids |= set(hand)

    root = GameState(
        turn_player=0,
        players=(
            PlayerState(base_units=frozenset(our_base_units), hand=hand, runes=runes,
                        score=STARTING_SCORE),
            PlayerState(base_units=frozenset(), hand=(), runes=RunePool(available=()), score=0),
        ),
        battlefields=tuple(battlefields),
        scored_this_turn=scored_this_turn,
        cards_played_this_turn=0,
    )
    cards = {card_id: CARD_POOL[card_id] for card_id in used_card_ids}
    return root, cards


def _runes_left_over(root: GameState, cards: dict[str, CardDef], strategy: Strategy) -> bool:
    """True if the winning line leaves any of OUR runes unspent at the
    terminal (win) state — tightens puzzles to use every resource they're
    given, not just the ones the line happens to need. Walks the
    strategy's spine via the first enumerated outcome at each step (same
    approach as maneuvers.maneuver_signature): rune spending only comes
    from OUR OWN actions, never the opponent's combat-assignment choice,
    so which branch gets followed doesn't affect the answer."""
    state = root
    visited: set[tuple] = set()
    while True:
        key = canonical_key(state)
        if key in visited:
            break
        visited.add(key)
        action = strategy.get(key)
        if action is None:
            break
        state = resolve_action_outcomes(state, action, cards)[0]
    return len(state.players[root.turn_player].runes.available) > 0


def evaluate_filters(root: GameState, cards: dict[str, CardDef], puzzle_id: str) -> Optional[dict]:
    """Every filter EXCEPT maneuver dedup — the position-only ones, which
    depend on nothing but this candidate and so can run in a worker
    process. Dedup is deliberately excluded: it depends on what else has
    already been accepted, so it has to be reconciled in one place, in a
    deterministic order (see generate())."""
    strategy = solve(root, cards, max_depth=MAX_SOLVE_DEPTH)
    if strategy is None:
        return None
    if len(strategy) < MIN_STRATEGY_SIZE:
        return None

    solution_count = count_winning_strategies(root, cards, max_depth=MAX_SOLVE_DEPTH)
    if solution_count != REQUIRED_SOLUTION_COUNT:
        return None

    if _runes_left_over(root, cards, strategy):
        return None

    result = export_puzzle(puzzle_id, root, cards, max_solver_depth=MAX_SOLVE_DEPTH)
    export_bytes = len(json.dumps(result).encode("utf-8"))
    if export_bytes > MAX_EXPORT_BYTES:
        return None

    result["_generation_meta"] = {
        "solution_length": len(strategy),
        "solution_count": solution_count,
        "export_bytes": export_bytes,
        "maneuver_signature": list(maneuver_signature(result)),
    }
    return result


def evaluate_candidate(root: GameState, cards: dict[str, CardDef], puzzle_id: str,
                        seen_signatures: set[Signature]) -> Optional[dict]:
    """Full filter chain including maneuver dedup against
    `seen_signatures` (already-promoted puzzles plus everything accepted
    earlier in this run), which is updated in place on acceptance."""
    result = evaluate_filters(root, cards, puzzle_id)
    if result is None:
        return None
    signature = maneuver_signature(result)
    if is_duplicate(signature, seen_signatures):
        return None
    seen_signatures.add(signature)
    return result


def sample_for_attempt(seed: Optional[int], attempt_index: int) -> tuple[GameState, dict[str, CardDef]]:
    """The position for a given attempt number, derived from its own RNG
    rather than one stream advanced across attempts — so attempt N is the
    same position no matter how the work was divided up, which is what
    lets attempts run in parallel while staying seed-reproducible.

    Seeded with a string rather than a tuple (unsupported) — and unlike
    the frozenset-ordering bug this project already hit, str seeding is
    NOT affected by hash randomization: random.seed() runs str input
    through sha512 rather than hash(), so it's stable across processes."""
    return sample_position(random.Random(f"{seed}:{attempt_index}"))


def _evaluate_attempt(args: tuple[Optional[int], int]) -> tuple[int, Optional[dict]]:
    """Worker entry point — module-level and taking only picklable args,
    since Windows spawns fresh processes rather than forking."""
    seed, attempt_index = args
    root, cards = sample_for_attempt(seed, attempt_index)
    return attempt_index, evaluate_filters(root, cards, f"generated-{attempt_index:05d}")


def generate(count: int, seed: Optional[int] = None, attempt_multiplier: int = 200,
              workers: Optional[int] = None) -> tuple[list[dict], int]:
    """Samples candidates until `count` survive the filters or the attempt
    budget (`count * attempt_multiplier`) runs out. Returns (survivors,
    attempts_made).

    Attempts are independent, so they're spread across `workers`
    processes (default: every core). Dedup still happens here in the
    parent, in attempt order, so results don't depend on which worker
    happened to finish first — the same seed gives the same survivors
    whatever the worker count. `workers=1` runs everything in-process,
    which is what the tests use to stay fast and debuggable.
    """
    max_attempts = count * attempt_multiplier
    seen_signatures: set[Signature] = set(load_registry().values())
    survivors: list[dict] = []
    if workers is None:
        workers = os.cpu_count() or 1

    if workers <= 1:
        for attempt in range(1, max_attempts + 1):
            root, cards = sample_for_attempt(seed, attempt)
            result = evaluate_candidate(root, cards, f"generated-{attempt:05d}", seen_signatures)
            if result is not None:
                survivors.append(result)
                if len(survivors) >= count:
                    return survivors, attempt
        return survivors, max_attempts

    # Work in chunks so a `count` that's reached early doesn't keep the
    # whole budget running, while still handing each worker enough
    # attempts at a time to amortise IPC.
    chunk = max(workers * 32, 64)
    attempted = 0
    with multiprocessing.Pool(processes=workers) as pool:
        while attempted < max_attempts and len(survivors) < count:
            batch = range(attempted + 1, min(attempted + chunk, max_attempts) + 1)
            results = pool.map(_evaluate_attempt, [(seed, i) for i in batch])
            for attempt_index, result in sorted(results, key=lambda r: r[0]):
                attempted = max(attempted, attempt_index)
                if result is None:
                    continue
                signature = maneuver_signature(result)
                if is_duplicate(signature, seen_signatures):
                    continue
                seen_signatures.add(signature)
                survivors.append(result)
                if len(survivors) >= count:
                    return survivors, attempt_index
            attempted = batch[-1]
    return survivors, attempted


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate lethal-puzzle candidates.")
    parser.add_argument("--count", type=int, default=5, help="number of survivors to produce")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed, for reproducible runs")
    parser.add_argument("--attempt-multiplier", type=int, default=200,
                         help="attempt budget per survivor wanted (max_attempts = count * this)")
    parser.add_argument("--workers", type=int, default=None,
                         help="parallel worker processes (default: every core; 1 = in-process)")
    args = parser.parse_args()

    survivors, attempts = generate(args.count, seed=args.seed,
                                    attempt_multiplier=args.attempt_multiplier,
                                    workers=args.workers)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for result in survivors:
        path = OUTPUT_DIR / f"{result['puzzle_id']}.json"
        path.write_text(json.dumps(result, indent=2))

    print(f"Attempts: {attempts}, survivors: {len(survivors)} "
          f"(hit rate: {len(survivors) / attempts:.1%})" if attempts else "No attempts made.")
    for result in survivors:
        meta = result["_generation_meta"]
        print(f"  {result['puzzle_id']}: {meta['solution_length']} states, "
              f"{meta['solution_count']} distinct winning line(s), {meta['export_bytes']} bytes")


if __name__ == "__main__":
    main()
