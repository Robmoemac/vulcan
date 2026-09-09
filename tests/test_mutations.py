"""UI mutations write canonical JSON and are held to the same grounding bar."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vulcan_map.core import compile as compile_mod
from vulcan_map.core.mutations import (
    MutationError, add_edge, owning_chart, remove_edge, restore_edge, set_position,
)
from vulcan_map.core.repo import Mind


def master(mind: Mind) -> dict:
    return json.loads(mind.master_path.read_text(encoding="utf-8"))


def test_add_edge_requires_real_evidence(repo: Path, mind: Mind) -> None:
    """A hand-drawn edge may not fabricate its evidence."""
    with pytest.raises(MutationError, match="does not exist"):
        add_edge(
            mind, "master",
            from_node="telemetry.run", from_socket="result",
            to_node="telemetry.write_telemetry", to_socket="data",
            evidence_file="src/invented.py",
        )
    assert len(master(mind)["edges"]) == 4  # unchanged


def test_add_edge_writes_canonical_and_survives_compile(repo: Path, mind: Mind) -> None:
    add_edge(
        mind, "master",
        from_node="telemetry.write_telemetry", from_socket="written_path",
        to_node="telemetry.write_telemetry", to_socket="path",
        evidence_file="src/telemetry.py",
    )
    # Self-edge above is nonsense on purpose; what matters is it landed in JSON.
    edges = master(mind)["edges"]
    assert len(edges) == 5
    assert edges[-1]["origin"] == "human"

    result = compile_mod.run(repo, check_only=True)
    assert any(f.rule == "V5" for f in result.report.findings)  # cycle detected


def test_add_edge_rejects_duplicate(repo: Path, mind: Mind) -> None:
    with pytest.raises(MutationError, match="already exists"):
        add_edge(
            mind, "master",
            from_node="propagator.propagate_orbit", from_socket="traj",
            to_node="telemetry.write_telemetry", to_socket="data",
            evidence_file="src/telemetry.py",
        )


def test_human_edge_is_protected_from_casual_removal(repo: Path, mind: Mind) -> None:
    """D6: human edits are sticky."""
    edge_id = add_edge(
        mind, "master",
        from_node="telemetry.run", from_socket="result",
        to_node="telemetry.write_telemetry", to_socket="data",
        evidence_file="src/telemetry.py",
    )
    with pytest.raises(MutationError, match="added by hand"):
        remove_edge(mind, "master", edge_id)

    removed = remove_edge(mind, "master", edge_id, allow_removal=True)
    assert removed["id"] == edge_id
    assert len(master(mind)["edges"]) == 4


def test_remove_then_restore_round_trips(repo: Path, mind: Mind) -> None:
    target = master(mind)["edges"][0]["id"]
    removed = remove_edge(mind, "master", target)
    assert all(e["id"] != target for e in master(mind)["edges"])

    restore_edge(mind, "master", removed)
    assert any(e["id"] == target for e in master(mind)["edges"])


def test_set_position_persists(repo: Path, mind: Mind) -> None:
    set_position(mind, "master", "telemetry.run", (321.0, 123.0))
    node = next(n for n in master(mind)["nodes"] if n["id"] == "telemetry.run")
    assert node["ui"]["pos"] == [321.0, 123.0]


def test_subchart_position_does_not_touch_master(repo: Path, mind: Mind) -> None:
    compile_mod.run(repo, check_only=False)
    sub = {
        "schema_version": "1.0.0", "chart_id": "view", "chart_kind": "sub",
        "derives_from": "master", "title": "View",
        "member_nodes": ["telemetry.run"],
    }
    (mind.subcharts_dir / "view.graph.json").write_text(json.dumps(sub, indent=2), encoding="utf-8")

    before = next(n for n in master(mind)["nodes"] if n["id"] == "telemetry.run")["ui"]["pos"]
    set_position(mind, "view", "telemetry.run", (999.0, 999.0))

    after = next(n for n in master(mind)["nodes"] if n["id"] == "telemetry.run")["ui"]["pos"]
    assert after == before

    data = json.loads((mind.subcharts_dir / "view.graph.json").read_text(encoding="utf-8"))
    assert data["ui"]["pos_overrides"]["telemetry.run"] == [999.0, 999.0]


def test_owning_chart_resolves_inherited_edges_to_master(repo: Path, mind: Mind) -> None:
    sub = {
        "schema_version": "1.0.0", "chart_id": "view", "chart_kind": "sub",
        "derives_from": "master", "title": "View",
        "member_nodes": ["propagator.propagate_orbit", "telemetry.write_telemetry"],
    }
    (mind.subcharts_dir / "view.graph.json").write_text(json.dumps(sub, indent=2), encoding="utf-8")
    inherited = "e:propagator.propagate_orbit:traj->telemetry.write_telemetry:data"
    assert owning_chart(mind, "view", inherited) == "master"
