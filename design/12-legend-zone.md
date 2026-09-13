# The Legend Zone

The other half of "battlefields and Legends are a source of forced lines no card in hand can produce" (see `11-battlefield-effects.md`). Battlefields were cheap — the state model already carried `effect_id`. Legends needed genuinely new state, which is why they were split into their own pass.

## State

A Legend is a persistent card in its own zone: never at a battlefield, never a combat participant, so it has no `instance_id`, no Might, and no damage. `state.LegendState` therefore models only what a single-turn puzzle can actually reach:

```python
@dataclass(frozen=True)
class LegendState:
    card_id: str
    exhausted: bool = False
```

`PlayerState.legend` is `Optional[LegendState]`, defaulting to `None` — so every puzzle authored before Legends existed, and every sampled position that doesn't draw one, is unchanged and needs no migration.

**`canonical_key` includes `(card_id, exhausted)`.** This is load-bearing, not bookkeeping: every registered Legend ability pays an Exhaust cost, so "Legend already used this turn" and "Legend still available" are genuinely different positions. Omitting it would let the transposition table collapse them and silently prune real lines.

## Activation reuses `ActivateAbility`

Rather than a parallel action type, a Legend ability is an `ActivateAbility` with:

- `source_id = LEGEND_SOURCE_ID` (0) — a sentinel, safe because `next_instance_id` starts at 1 and can never hand out 0.
- `ability_id` = the Legend's card_id, keyed into `LEGEND_ABILITIES`.
- `rune_payment` = a real payment. This is the first genuine use of that field: Caitlyn's ability is Exhaust-only and pays `None`, whereas Legend abilities commonly cost Energy on top of Exhaust.

Dispatch checks `legends.is_legend_ability(ability_id)` first and routes to `legends.py`; everything else falls through to `abilities.ABILITY_EFFECTS` as before. Cost payment (Exhaust + runes) is shared in `resolve_legend_ability_outcomes`, so each registered card only writes its own targeting rules and effect.

Effects return `list[GameState]` from the start, matching the shape spells and unit-play triggers converged on — a Legend ability that moves an *enemy* unit would cause combat and branch, and this way that needs no signature change when it arrives.

## Registered

| Card | `riftbound_id` | Text |
|---|---|---|
| Yasuo - Unforgiven | `ogn-259-298` | 2 Energy, Exhaust: Move a friendly unit to or from its base. |

Yasuo - Unforgiven is deliberately *narrower* than Ride The Wind: "to or from its base" means one end of the move must be Base, so battlefield-to-battlefield is illegal even though a spell-granted move normally wouldn't be restricted. This is exactly the case `is_legal_ability_move_destination`'s docstring anticipated — a card that's actually restricted enforces the narrower rule itself rather than loosening the shared helper.

Good next candidates, in rising order of new machinery needed:

- **Viktor - Herald of the Arcane** (`ogn-265-298`): "1 Energy, Exhaust: Play a 1-Might Recruit unit token." `UnitInstance.is_token` already exists, so this mostly needs token construction.
- **Miss Fortune - Bounty Hunter** (`ogn-267-298`): "Exhaust: Give a unit Ganking this turn." Needs temporary ("this turn") modifier tracking, which nothing models yet.
- **Lee Sin - Blind Monk** (`ogn-257-298`): buff mechanic — needs buff state.
- **Ahri / Jinx**: triggered on attack / Beginning Phase — need trigger-timing hooks, same blocker as most Battlefield cards.

## Open question: does an effect-granted move exhaust the unit?

Yasuo - Unforgiven's text has no "and ready it" clause, unlike Ride The Wind. Currently implemented as **preserving** the unit's existing exhaustion state, on the reading that an effect-granted move isn't a Standard Move and so doesn't carry rule 145.1's exhaust cost — which is also what makes Ride The Wind's explicit "ready it" meaningful.

If that reading is wrong, **Blitzcrank's redirect is wrong too** — it hardcodes `exhausted_after=True` on the unit it moves. Flagged, not yet changed, pending confirmation.
