# Battlefield Effects

`BattlefieldState.effect_id` has existed in the state model since the first design pass but nothing was ever wired to it — every puzzle and every sampled position carried `None`. This doc covers turning it on, prompted by the observation that battlefields (and Legends) are a distinct source of forced-unique lines that no card in hand can produce: they change the rules *of a place*, so a line can be forced by where the fight happens rather than by what's in hand.

Origins has 24 Battlefield cards. This follows the same "add mechanics on demand" policy as `abilities.py` (see `07-scope-and-cut-list.md`) — registered one at a time in `engine/battlefields.py`, only the ones a puzzle actually needs.

## Scope: static effects only

Registered so far, all **static** — they modify a unit's combat math or movement legality purely by virtue of the unit being physically there, with no trigger timing to model:

| Card | `riftbound_id` | Text | Modelled as |
|---|---|---|---|
| Windswept Hillock | `ogn-297-298` | "Units here have [Ganking]." | `GRANTED_KEYWORDS` |
| Trifarian War Camp | `ogn-294-298` | "Units here have +1 Might. (This includes attackers.)" | `MIGHT_BONUS` |
| Vilemaw's Lair | `ogn-295-298` | "Units can't move from here to base." | `NO_MOVE_TO_BASE` |

**Deliberately out of scope for now**: every battlefield whose text is a *trigger* — "when you conquer here…", "when you defend here…", "when you hold here…" (Targon's Peak, Reaver's Row, Fortified Position, Grove of the God-Willow, and most of the rest). Those need a trigger-timing hook that doesn't exist yet; adding one speculatively, before a puzzle needs it, risks encoding wrong timing that no test can meaningfully check.

## Two kinds of conditionality

The Might fix in `09-combat-resolution.md` made this distinction load-bearing:

- **Keyword bonuses** (Assault/Shield) are conditional on a *combat role*. They count only while the unit is actually attacking/defending, so they're passed a `designation` and vanish (`designation=None`) outside combat — a 3-Might Shield unit dies to a 3-damage spell.
- **Battlefield bonuses** are conditional on *position*. A unit standing on Trifarian War Camp is +1 Might in every context, including against direct effect damage, for as long as it's there. It stops the moment the unit leaves.

Both feed the same `combat.effective_might(unit, designation, effect_id)`, and both raise damage dealt *and* the lethal threshold, since Might is one stat.

Positional also means the grant is never a property of the unit itself — `actions.effective_keywords(state, unit, zone)` exists so that nothing reads `unit.keywords` directly where location could matter. A unit at Base gets nothing from a Hillock sitting on the other side of the board.

## Movement restrictions bind every kind of move

Vilemaw's Lair ("units can't move from here to base") is enforced in **both** `is_legal_destination` (a unit's own Standard Move) and `is_legal_ability_move_destination` (spell/ability-granted moves like Ride The Wind and Charm). The text restricts *movement*, not one particular way of moving — so a spell can't route around it. This is the opposite of Ganking's Battlefield-to-Battlefield restriction, which *is* specific to the Standard Move game action and correctly does not bind spells.

## Generation

`generate.py` assigns a registered effect to each sampled battlefield with probability `BATTLEFIELD_EFFECT_CHANCE` (0.3). `canonical_key` already included `effect_id`, so transposition-table dedup was correct for this from the start — two positions differing only by battlefield effect were never going to collide.

## Not yet built: Legends

Legends (36 in Origins) are the other half of the observation that prompted this doc, and a considerably bigger lift: the engine has no Legend zone at all — `PlayerState` tracks only `base_units`/`hand`/`runes`/`score`. Supporting them means new persistent state plus a registry for their abilities, rather than switching on a field the state model already carries. Left for a separate pass.
