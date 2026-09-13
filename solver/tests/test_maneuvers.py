from solver import maneuvers


def make_export(root, solution, edges):
    return {"root": root, "solution": solution, "edges": edges}


def test_maneuver_signature_walks_the_solution_path():
    result = make_export(
        root="s0",
        solution={"s0": "a1", "s1": "a2"},
        edges={
            "s0": [{"action": {"id": "a1", "type": "MoveUnit", "card_id": "cardA"}, "to": ["s1"]}],
            "s1": [{"action": {"id": "a2", "type": "PlaySpell", "card_id": "cardB"}, "to": ["s2"]}],
        },
    )
    assert maneuvers.maneuver_signature(result) == (("MoveUnit", "cardA"), ("PlaySpell", "cardB"))


def test_maneuver_signature_ignores_lane_and_instance_differences():
    # Same trick, different card_id spelling would differ, but identical
    # card_ids on different lanes/instance_ids must collapse to one
    # signature - the whole point of stripping those out.
    left_variant = make_export(
        root="s0", solution={"s0": "a1"},
        edges={"s0": [{"action": {"id": "a1", "type": "MoveUnit", "card_id": "cardA"}, "to": ["s1"]}]},
    )
    right_variant = make_export(
        root="t0", solution={"t0": "a9"},
        edges={"t0": [{"action": {"id": "a9", "type": "MoveUnit", "card_id": "cardA"}, "to": ["t1"]}]},
    )
    assert maneuvers.maneuver_signature(left_variant) == maneuvers.maneuver_signature(right_variant)


def test_registry_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(maneuvers, "REGISTRY_PATH", tmp_path / "maneuvers.json")
    assert maneuvers.load_registry() == {}

    result = make_export(
        root="s0", solution={"s0": "a1"},
        edges={"s0": [{"action": {"id": "a1", "type": "ResolveCombat", "card_id": "cardZ"}, "to": ["s1"]}]},
    )
    signature = maneuvers.register_puzzle("puzzle-999-test", result)
    assert signature == (("ResolveCombat", "cardZ"),)

    reloaded = maneuvers.load_registry()
    assert reloaded == {"puzzle-999-test": signature}


def test_registry_overwrites_existing_entry_for_same_puzzle_id(tmp_path, monkeypatch):
    monkeypatch.setattr(maneuvers, "REGISTRY_PATH", tmp_path / "maneuvers.json")
    first = make_export(
        root="s0", solution={"s0": "a1"},
        edges={"s0": [{"action": {"id": "a1", "type": "MoveUnit", "card_id": "cardA"}, "to": ["s1"]}]},
    )
    second = make_export(
        root="s0", solution={"s0": "a1"},
        edges={"s0": [{"action": {"id": "a1", "type": "PlaySpell", "card_id": "cardB"}, "to": ["s1"]}]},
    )
    maneuvers.register_puzzle("puzzle-001-x", first)
    maneuvers.register_puzzle("puzzle-001-x", second)
    registry = maneuvers.load_registry()
    assert registry == {"puzzle-001-x": (("PlaySpell", "cardB"),)}
