from solver import maneuvers
from solver.engine.abilities import BLITZCRANK_IMPASSIVE, CAITLYN_PATROLLING, YASUO_WINDRIDER


def make_export(root, solution, edges):
    return {"root": root, "solution": solution, "edges": edges}


def move_action(action_id, card_id, keywords=(), to="s1"):
    return {"action": {"id": action_id, "type": "MoveUnit", "card_id": card_id,
                        "keywords": list(keywords)}, "to": [to]}


def combat_action(action_id, card_id, keywords=(), to="s1", action_type="ResolveCombat"):
    return {"action": {"id": action_id, "type": action_type, "card_id": card_id,
                        "keywords": list(keywords)}, "to": [to]}


def chain(*actions):
    """Builds an export whose solution walks `actions` in order, one per
    state, so a multi-step signature can be written inline."""
    solution, edges = {}, {}
    for i, action in enumerate(actions):
        state = f"s{i}"
        action["to"] = [f"s{i + 1}"]
        action["action"]["id"] = f"a{i}"
        solution[state] = f"a{i}"
        edges[state] = [action]
    return make_export(root="s0", solution=solution, edges=edges)


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


def test_a_plain_move_keeps_only_movement_relevant_keywords():
    """A combat keyword on a step that doesn't fight is not a different
    trick. Ganking is, because it decides where the mover may legally go
    (rule 810, Battlefield-to-Battlefield).

    generated-07640 and generated-08685 were the same Blitzcrank line and
    survived dedup as two, purely because one walked a Shield body into
    the cleared lane and the other a bare one."""
    tank = make_export(root="s0", solution={"s0": "a1"},
                        edges={"s0": [move_action("a1", "cardA", keywords=("Tank",))]})
    bare = make_export(root="s0", solution={"s0": "a1"},
                        edges={"s0": [move_action("a1", "cardA")]})
    ganking = make_export(root="s0", solution={"s0": "a1"},
                           edges={"s0": [move_action("a1", "cardB", keywords=("Ganking",))]})
    assert maneuvers.maneuver_signature(tank) == maneuvers.maneuver_signature(bare)
    assert maneuvers.maneuver_signature(tank) == (("MoveUnit", "vanilla:"),)
    assert maneuvers.maneuver_signature(ganking) == (("MoveUnit", "vanilla:Ganking"),)


def test_a_fighting_step_keeps_its_combat_keywords():
    """The same keyword that's inert on a plain move is a real difference
    once the step actually resolves damage."""
    tank = make_export(root="s0", solution={"s0": "a1"},
                        edges={"s0": [combat_action("a1", "cardA", keywords=("Tank",))]})
    bare = make_export(root="s0", solution={"s0": "a1"},
                        edges={"s0": [combat_action("a1", "cardA")]})
    assert maneuvers.maneuver_signature(tank) != maneuvers.maneuver_signature(bare)
    assert maneuvers.maneuver_signature(tank) == (("ResolveCombat", "vanilla:Tank"),)


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
    """Blitzcrank buckets as vanilla when all he does is walk. His Tank
    comes with him into the bucket label on a step that fights, and drops
    out on one that doesn't."""
    walking = make_export(root="s0", solution={"s0": "a1"},
                           edges={"s0": [move_action("a1", BLITZCRANK_IMPASSIVE, keywords=("Tank",))]})
    fighting = make_export(root="s0", solution={"s0": "a1"},
                            edges={"s0": [combat_action("a1", BLITZCRANK_IMPASSIVE, keywords=("Tank",))]})
    assert maneuvers.maneuver_signature(walking) == (("MoveUnit", "vanilla:"),)
    assert maneuvers.maneuver_signature(fighting) == (("ResolveCombat", "vanilla:Tank"),)


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


# --- normalizations that keep equivalent lines tokenizing alike ---


def spell_action(action_id, card_id, to="s1"):
    return {"action": {"id": action_id, "type": "PlaySpell", "card_id": card_id,
                        "keywords": []}, "to": [to]}


def showdown_pair(card_id, keywords=()):
    return [combat_action("x", card_id, keywords, action_type="EnterShowdown"),
            {"action": {"id": "x", "type": "ResolveShowdown", "card_id": "", "keywords": []},
             "to": ["s"]}]


def test_an_unused_showdown_window_collapses_to_the_combat_it_equals():
    """Opening a showdown and immediately resolving it, with nothing
    played in between, is an ordinary combat written across two steps —
    so it has to tokenize as one."""
    split = chain(*showdown_pair("cardA"))
    atomic = chain(combat_action("x", "cardA"))
    assert maneuvers.maneuver_signature(split) == maneuvers.maneuver_signature(atomic)
    assert maneuvers.maneuver_signature(split) == (("ResolveCombat", "vanilla:"),)


def test_a_showdown_that_is_actually_used_is_not_collapsed():
    """A window someone acts inside is a real decision and stays two
    steps — that is the whole difference showdowns add."""
    used = chain(showdown_pair("cardA")[0], spell_action("x", "ogn-173-298"),
                 showdown_pair("cardA")[1])
    assert maneuvers.maneuver_signature(used) == (
        ("EnterShowdown", "vanilla:"), ("PlaySpell", "ogn-173-298"), ("ResolveShowdown", ""))


def test_a_known_trick_with_a_step_spliced_into_it_is_still_a_duplicate():
    """generated-05347 was puzzle 3's signature exactly, with one combat
    inserted to clear the destination first, and containment missed it
    because the run was no longer contiguous."""
    puzzle_3 = (("MoveUnit", YASUO_WINDRIDER), ("PlaySpell", "ogn-173-298"),
                ("MoveUnit", YASUO_WINDRIDER))
    spliced = (("MoveUnit", YASUO_WINDRIDER), ("PlaySpell", "ogn-173-298"),
               ("ResolveCombat", "vanilla:"), ("MoveUnit", YASUO_WINDRIDER))
    assert maneuvers.is_duplicate(spliced, {puzzle_3})


def test_splicing_in_enough_new_work_still_reads_as_a_composite():
    """The coverage gate still protects genuine composites: a known trick
    stops accounting for the bulk of a candidate once enough else is
    happening, and subsequence matching does not change that."""
    puzzle_3 = (("MoveUnit", YASUO_WINDRIDER), ("PlaySpell", "ogn-173-298"),
                ("MoveUnit", YASUO_WINDRIDER))
    composite = (("ResolveCombat", "vanilla:"), ("MoveUnit", YASUO_WINDRIDER),
                 ("PlayUnit", BLITZCRANK_IMPASSIVE), ("PlaySpell", "ogn-173-298"),
                 ("MoveUnit", YASUO_WINDRIDER))
    assert not maneuvers.is_duplicate(composite, {puzzle_3})


def test_subsequence_matching_still_respects_order():
    """Order carries the trick: the same steps performed in a different
    sequence are a different line, not a duplicate."""
    trick = (("MoveUnit", YASUO_WINDRIDER), ("PlaySpell", "ogn-173-298"),
             ("ResolveCombat", "vanilla:"))
    reordered = (("PlaySpell", "ogn-173-298"), ("MoveUnit", YASUO_WINDRIDER),
                 ("ResolveCombat", "vanilla:"))
    assert not maneuvers.is_duplicate(reordered, {trick})
