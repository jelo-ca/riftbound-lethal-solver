"""The one place a card's printed characteristics are written down.

Previously each author_puzzle_*.py hand-rolled its own CardDef for the
cards it used, and generate.py kept a separate CARD_POOL. Those copies
drifted the moment a field was added: `speed` was set on generate.py's
Ride The Wind and not on the four author scripts', so showdowns silently
never opened in any hand-authored puzzle — the cards looked Slow there.

Everything that needs a CardDef imports it from here instead.
"""

from __future__ import annotations

from .abilities import (
    BLITZCRANK_IMPASSIVE,
    CAITLYN_PATROLLING,
    CHARM,
    FAITHFUL_MANUFACTOR,
    PRIMAL_STRENGTH,
    RECRUIT_TOKEN,
    RECRUIT_TOKEN_CARD,
    RIDE_THE_WIND,
    VANGUARD_CAPTAIN,
    VENGEANCE,
    YASUO_WINDRIDER,
    ZAUNITE_BOUNCER,
)
from .cards import CardDef
from .deaths import KOGMAW_CAUSTIC, MACHINE_EVANGEL
from .traits import TARIC_PROTECTOR

LEGION_REARGUARD = "ogn-010-298"
SNEAKY_DECKHAND = "ogn-176-298"
DARING_PORO = "ogn-210-298"
STALWART_PORO = "ogn-052-298"
POUTY_PORO = "ogn-013-298"

CARD_POOL: dict[str, CardDef] = {
    # Recorded as a vanilla body until now; it actually prints [Accelerate]
    # (1 Energy + a Fury rune to enter ready). No Power cost of its own, so
    # the Fury requirement lives in accelerate_domain rather than power_domain.
    LEGION_REARGUARD: CardDef(card_id=LEGION_REARGUARD, card_type="Unit", energy_cost=2,
                               power_cost=0, might=2, keywords=frozenset({"Accelerate"}),
                               accelerate_domain="Fury"),
    FAITHFUL_MANUFACTOR: CardDef(card_id=FAITHFUL_MANUFACTOR, card_type="Unit", energy_cost=3,
                                  power_cost=0, might=2, keywords=frozenset()),
    VANGUARD_CAPTAIN: CardDef(card_id=VANGUARD_CAPTAIN, card_type="Unit", energy_cost=3,
                               power_cost=1, power_domain="Order", might=3,
                               keywords=frozenset({"Legion"})),
    SNEAKY_DECKHAND: CardDef(card_id=SNEAKY_DECKHAND, card_type="Unit", energy_cost=3,
                              power_cost=0, might=2, keywords=frozenset(),
                              can_play_to_open_battlefield=True),
    CAITLYN_PATROLLING: CardDef(card_id=CAITLYN_PATROLLING, card_type="Unit", energy_cost=3,
                                 power_cost=1, power_domain="Calm", might=3, keywords=frozenset()),
    BLITZCRANK_IMPASSIVE: CardDef(card_id=BLITZCRANK_IMPASSIVE, card_type="Unit", energy_cost=5,
                                   power_cost=1, power_domain="Calm", might=5,
                                   keywords=frozenset({"Tank"})),
    YASUO_WINDRIDER: CardDef(card_id=YASUO_WINDRIDER, card_type="Unit", energy_cost=5,
                              power_cost=1, power_domain="Chaos", might=4,
                              keywords=frozenset({"Ganking"})),
    DARING_PORO: CardDef(card_id=DARING_PORO, card_type="Unit", energy_cost=2,
                          power_cost=0, might=2, keywords=frozenset({"Assault"})),
    STALWART_PORO: CardDef(card_id=STALWART_PORO, card_type="Unit", energy_cost=2,
                            power_cost=0, might=2, keywords=frozenset({"Shield"})),
    # The only clean [Deflect] card in the set — same 2 Energy / 2 Might
    # one-keyword shape as the other two Poros. The rest carry extra
    # unimplemented text (attack and conquer triggers, a sacrifice cost,
    # "play me to an occupied enemy battlefield").
    POUTY_PORO: CardDef(card_id=POUTY_PORO, card_type="Unit", energy_cost=2,
                         power_cost=0, might=2, keywords=frozenset({"Deflect"})),
    # A 1-Might body that wipes its own battlefield for 4 when it dies —
    # the [Deathknell] worth having, since dying is cheap for it and
    # Vengeance can target your own units.
    KOGMAW_CAUSTIC: CardDef(card_id=KOGMAW_CAUSTIC, card_type="Unit", energy_cost=3,
                             power_cost=1, power_domain="Chaos", might=1,
                             keywords=frozenset({"Deathknell"})),
    MACHINE_EVANGEL: CardDef(card_id=MACHINE_EVANGEL, card_type="Unit", energy_cost=5,
                              power_cost=1, power_domain="Order", might=4,
                              keywords=frozenset({"Deathknell"})),
    ZAUNITE_BOUNCER: CardDef(card_id=ZAUNITE_BOUNCER, card_type="Unit", energy_cost=4,
                              power_cost=2, power_domain="Chaos", might=2, keywords=frozenset()),
    TARIC_PROTECTOR: CardDef(card_id=TARIC_PROTECTOR, card_type="Unit", energy_cost=4,
                              power_cost=1, power_domain="Calm", might=4,
                              keywords=frozenset({"Shield", "Tank"})),
    RECRUIT_TOKEN: RECRUIT_TOKEN_CARD,
    RIDE_THE_WIND: CardDef(card_id=RIDE_THE_WIND, card_type="Spell", energy_cost=2,
                            power_cost=1, power_domain="Chaos", keywords=frozenset(),
                            speed="Action"),
    VENGEANCE: CardDef(card_id=VENGEANCE, card_type="Spell", energy_cost=4,
                        power_cost=2, power_domain="Order", keywords=frozenset()),
    CHARM: CardDef(card_id=CHARM, card_type="Spell", energy_cost=1,
                    power_cost=1, power_domain="Calm", keywords=frozenset()),
    PRIMAL_STRENGTH: CardDef(card_id=PRIMAL_STRENGTH, card_type="Spell", energy_cost=4,
                              power_cost=1, power_domain="Body", keywords=frozenset(),
                              speed="Action"),
}


def cards_for(*card_ids: str) -> dict[str, CardDef]:
    """The `cards` mapping a puzzle needs, for the cards it actually
    uses — what author scripts pass to export_puzzle."""
    return {card_id: CARD_POOL[card_id] for card_id in card_ids}
