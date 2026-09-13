from solver import maneuvers
from solver.engine.abilities import BLITZCRANK_IMPASSIVE, CAITLYN_PATROLLING, YASUO_WINDRIDER


def make_export(root, solution, edges):
    return {"root": root, "solution": solution, "edges": edges}


def move_action(action_id, card_id, keywords=(), to="s1"):
    return {"action": {"id": action_id, "type": "MoveUnit", "card_id": card_id,
                        "keywords": list(keywords)}, "to": [to]}


def test_maneuver_signature_walks_the_solution_path():
    result = make_export(
        root="s0",
        solution={"s0": "a1", "s1": "a2"},
        edges={
            "s0": [move_action("a1", "cardA")],
            "s1": [{"action": {"id": "a2", "type": "PlaySpell", "card_id": "cardB", "keywords": []},
                     "to": ["s2"]}],
        },
    )
    # cardA is an unregistered vanilla mover with no keywords -> buckets as "vanilla:";
    # PlaySpell always keeps its raw card_id regardless of registration.
    assert maneuvers.maneuver_signature(result) == (("MoveUnit", "vanilla:"), ("PlaySpell", "cardB"))


def test_maneuver_signature_ignores_lane_and_instance_differences():
    left_variant = make_export(root="s0", solution={"s0": "a1"}, edges={"s0": [move_action("a1", "cardA")]})
    right_variant = make_export(root="t0", solution={"t0": "a9"}, edges={"t0": [move_action("a9", "cardA", to="t1")]})
    assert maneuvers.maneuver_signature(left_variant) == maneuvers.maneuver_signature(right_variant)


def test_maneuver_signature_collapses_different_vanilla_cards_with_the_same_keywords():
    """The actual granularity fix: two DIFFERENT unregistered card_ids
    (e.g. Sneaky Deckhand vs Faithful Manufactor as interchangeable
    filler) with the same keyword set (here: none) must collapse to one
    signature — this is what let a near-duplicate slip past dedup in
    practice before this fix."""
    deckhand = make_export(root="s0", solution={"s0": "a1"}, edges={"s0": [move_action("a1", "ogn-176-298")]})
    manufactor = make_export(root="s0", solution={"s0": "a1"}, edges={"s0": [move_action("a1", "ogn-211-298")]})
    assert maneuvers.maneuver_signature(deckhand) == maneuvers.maneuver_signature(manufactor)
    assert maneuvers.maneuver_signature(deckhand) == (("MoveUnit", "vanilla:"),)


def test_maneuver_signature_keeps_different_keyword_sets_distinct():
    tank = make_export(root="s0", solution={"s0": "a1"}, edges={"s0": [move_action("a1", "cardA", keywords=("Tank",))]})
    ganking = make_export(root="s0", solution={"s0": "a1"},
                           edges={"s0": [move_action("a1", "cardB", keywords=("Ganking",))]})
    assert maneuvers.maneuver_signature(tank) != maneuvers.maneuver_signature(ganking)
    assert maneuvers.maneuver_signature(tank) == (("MoveUnit", "vanilla:Tank"),)


def test_move_step_keeps_raw_card_id_only_for_a_move_relevant_mechanic():
    """Yasuo - Windrider's move-count trigger changes what a move MEANS,
    so a move by him stays keyed to his card_id."""
    result = make_export(root="s0", solution={"s0": "a1"},
                          edges={"s0": [move_action("a1", YASUO_WINDRIDER, keywords=("Ganking",))]})
    assert maneuvers.maneuver_signature(result) == (("MoveUnit", YASUO_WINDRIDER),)


def test_a_mechanic_card_that_merely_moves_buckets_as_vanilla():
    """Caitlyn's ability and Blitzcrank's play-trigger are irrelevant when
    all the card does is walk into a lane — treating them as distinctive
    made one trick read as three in a live batch."""
    caitlyn = make_export(root="s0", solution={"s0": "a1"},
                           edges={"s0": [move_action("a1", CAITLYN_PATROLLING)]})
    plain = make_export(root="s0", solution={"s0": "a1"},
                         edges={"s0": [move_action("a1", "ogn-211-298")]})
    assert maneuvers.maneuver_signature(caitlyn) == maneuvers.maneuver_signature(plain)
    assert maneuvers.maneuver_signature(caitlyn) == (("MoveUnit", "vanilla:"),)


def test_a_mechanic_card_moving_still_keeps_its_keywords():
    """Blitzcrank buckets as vanilla, but Tank is still a real combat
    difference, so it stays in the bucket label."""
    result = make_export(root="s0", solution={"s0": "a1"},
                          edges={"s0": [move_action("a1", BLITZCRANK_IMPASSIVE, keywords=("Tank",))]})
    assert maneuvers.maneuver_signature(result) == (("MoveUnit", "vanilla:Tank"),)


def test_non_move_steps_still_key_on_the_real_card():
    """The bucketing is specific to MOVE steps - actually PLAYING a spell
    or ACTIVATING an ability is entirely about which card it is."""
    result = make_export(
        root="s0", solution={"s0": "a1"},
        edges={"s0": [{"action": {"id": "a1", "type": "ActivateAbility",
                                   "card_id": CAITLYN_PATROLLING, "keywords": []}, "to": ["s1"]}]},
    )
    assert maneuvers.maneuver_signature(result) == (("ActivateAbility", CAITLYN_PATROLLING),)


# --- declined tricks ---


def test_declined_signatures_are_persisted_and_reloaded(tmp_path, monkeypatch):
    monkeypatch.setattr(maneuvers, "DECLINED_PATH", tmp_path / "declined.json")
    assert maneuvers.load_declined() == []

    trick = sig(("ResolveCombat", "vanilla:"), ("PlaySpell", "rtw"), ("ResolveCombat", "vanilla:"))
    assert maneuvers.decline_signature(trick, note="seen every batch, not interesting") is True
    assert maneuvers.load_declined() == [trick]
    # Declining the same trick twice is a no-op rather than a duplicate entry.
    assert maneuvers.decline_signature(trick) is False
    assert maneuvers.load_declined() == [trick]


def test_known_signatures_covers_promoted_and_declined(tmp_path, monkeypatch):
    monkeypatch.setattr(maneuvers, "REGISTRY_PATH", tmp_path / "maneuvers.json")
    monkeypatch.setattr(maneuvers, "DECLINED_PATH", tmp_path / "declined.json")
    promoted = make_export(root="s0", solution={"s0": "a1"}, edges={"s0": [move_action("a1", "cardA")]})
    maneuvers.register_puzzle("puzzle-x", promoted)
    declined = sig(("PlaySpell", "rtw"), ("MoveUnit", "vanilla:"), ("ResolveCombat", "vanilla:"))
    maneuvers.decline_signature(declined)

    known = maneuvers.known_signatures()
    assert declined in known
    assert maneuvers.maneuver_signature(promoted) in known


def test_a_declined_trick_is_treated_as_duplicate(tmp_path, monkeypatch):
    """The point of the declined list: a trick we've already rejected
    stops consuming the attempt budget in later batches."""
    monkeypatch.setattr(maneuvers, "DECLINED_PATH", tmp_path / "declined.json")
    trick = sig(("ResolveCombat", "vanilla:"), ("PlaySpell", "rtw"), ("ResolveCombat", "vanilla:"))
    maneuvers.decline_signature(trick)
    assert maneuvers.is_duplicate(trick, maneuvers.known_signatures())


# --- is_duplicate: exact match plus dominant-containment ---


def sig(*steps):
    return tuple(steps)


YASUO_RUN = sig(("MoveUnit", "yasuo"), ("PlaySpell", "rtw"), ("MoveUnit", "yasuo"))


def test_is_duplicate_on_exact_match():
    assert maneuvers.is_duplicate(YASUO_RUN, [YASUO_RUN])


def test_is_duplicate_when_a_known_trick_plus_trivial_setup():
    """The real case from a live batch: one combat step prepended to
    puzzle 3's Yasuo loop. 3 of 4 steps are the known trick, so it's the
    same puzzle with a throwaway opener, not a new one."""
    candidate = sig(("ResolveCombat", "vanilla:"), *YASUO_RUN)
    assert maneuvers.is_duplicate(candidate, [YASUO_RUN])


def test_is_not_duplicate_when_a_known_trick_is_only_part_of_a_composite():
    """The case worth protecting: a known trick CHAINED with substantial
    other work (e.g. starting further back on points and needing two
    conquers as well as Yasuo's card-effect point) is a genuinely better
    puzzle, not a rerun."""
    candidate = sig(
        ("ResolveCombat", "vanilla:"), ("MoveUnit", "vanilla:"), ("ResolveCombat", "vanilla:Tank"),
        *YASUO_RUN,
    )
    assert not maneuvers.is_duplicate(candidate, [YASUO_RUN])


def test_short_registered_signatures_never_match_by_containment():
    """Puzzle 2 and puzzle 4 are single-step signatures that appear inside
    almost everything - matching those by containment would reject the
    entire search space."""
    one_step = sig(("PlaySpell", "rtw"))
    candidate = sig(("ResolveCombat", "vanilla:"), ("PlaySpell", "rtw"), ("MoveUnit", "vanilla:"))
    assert not maneuvers.is_duplicate(candidate, [one_step])


def test_is_duplicate_ignores_an_unrelated_known_trick():
    candidate = sig(("ResolveCombat", "vanilla:"), ("ActivateAbility", "caitlyn"))
    assert not maneuvers.is_duplicate(candidate, [YASUO_RUN])


def test_empty_signature_is_never_duplicate():
    assert not maneuvers.is_duplicate((), [YASUO_RUN])


def test_registry_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(maneuvers, "REGISTRY_PATH", tmp_path / "maneuvers.json")
    assert maneuvers.load_registry() == {}

    result = make_export(root="s0", solution={"s0": "a1"},
                          edges={"s0": [{"action": {"id": "a1", "type": "ResolveCombat", "card_id": "cardZ",
                                                     "keywords": ["Tank"]}, "to": ["s1"]}]})
    signature = maneuvers.register_puzzle("puzzle-999-test", result)
    assert signature == (("ResolveCombat", "vanilla:Tank"),)

    reloaded = maneuvers.load_registry()
    assert reloaded == {"puzzle-999-test": signature}


def test_registry_overwrites_existing_entry_for_same_puzzle_id(tmp_path, monkeypatch):
    monkeypatch.setattr(maneuvers, "REGISTRY_PATH", tmp_path / "maneuvers.json")
    first = make_export(root="s0", solution={"s0": "a1"}, edges={"s0": [move_action("a1", "cardA")]})
    second = make_export(
        root="s0", solution={"s0": "a1"},
        edges={"s0": [{"action": {"id": "a1", "type": "PlaySpell", "card_id": "cardB", "keywords": []},
                       "to": ["s1"]}]},
    )
    maneuvers.register_puzzle("puzzle-001-x", first)
    maneuvers.register_puzzle("puzzle-001-x", second)
    registry = maneuvers.load_registry()
    assert registry == {"puzzle-001-x": (("PlaySpell", "cardB"),)}
