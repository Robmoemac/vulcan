"""UI edits are queued intents; compile is the only writer of chart files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vulcan_map.core import compile as compile_mod, pending
from vulcan_map.core.mutations import (
    MutationError, enqueue_add_edge, enqueue_remove_edge, owning_chart,
    pending_count, set_position,
)
from vulcan_map.core.repo import Mind


def master(mind: Mind) -> dict:
    return json.loads(mind.master_path.read_text(encoding="utf-8"))


def edge_ids(mind: Mind) -> list[str]:
    return [e["id"] for e in master(mind)["edges"]]


def test_add_edge_requires_real_evidence(repo: Path, mind: Mind) -> None:
    """A hand-drawn edge may not fabricate its evidence."""
    with pytest.raises(MutationError, match="does not exist"):
        enqueue_add_edge(
            mind, "master",
            from_node="telemetry.run", from_socket="result",
            to_node="telemetry.write_telemetry", to_socket="data",
            evidence_file="src/invented.py",
        )
    assert pending_count(mind) == 0
    assert len(master(mind)["edges"]) == 6


def test_blank_evidence_is_refused(repo: Path, mind: Mind) -> None:
    with pytest.raises(MutationError, match="must cite a file"):
        enqueue_add_edge(
            mind, "master",
            from_node="telemetry.run", from_socket="path_out",
            to_node="propagator.propagate_orbit", to_socket="state0",
            evidence_file="   ",
        )


def test_drawing_queues_but_does_not_write(repo: Path, mind: Mind) -> None:
    """The core of the change: drawing must not touch a chart file."""
    before = mind.master_path.read_text(encoding="utf-8")

    enqueue_add_edge(
        mind, "master",
        from_node="telemetry.run", from_socket="path_out",
        to_node="propagator.propagate_orbit", to_socket="state0",
        evidence_file="src/telemetry.py",
    )

    assert mind.master_path.read_text(encoding="utf-8") == before
    assert mind.pending_path.exists()
    assert pending_count(mind) == 1


def test_compile_folds_the_queue_and_clears_it(repo: Path, mind: Mind) -> None:
    edge_id = enqueue_add_edge(
        mind, "master",
        from_node="telemetry.run", from_socket="path_out",
        to_node="propagator.propagate_orbit", to_socket="state0",
        evidence_file="src/telemetry.py",
    )
    result = compile_mod.run(repo, check_only=False)

    assert result.pending_applied == 1
    assert edge_id in edge_ids(mind)
    assert not mind.pending_path.exists()

    folded = next(e for e in master(mind)["edges"] if e["id"] == edge_id)
    assert folded["origin"] == "human"
    assert folded["evidence"]["file"] == "src/telemetry.py"


def test_check_sees_pending_without_consuming_it(repo: Path, mind: Mind) -> None:
    """`check` must validate what `compile` would write, but write nothing."""
    enqueue_add_edge(
        mind, "master",
        from_node="telemetry.write_telemetry", from_socket="written_path",
        to_node="telemetry.run", to_socket="path",
        evidence_file="src/telemetry.py",
    )
    before = mind.master_path.read_text(encoding="utf-8")

    report = compile_mod.run(repo, check_only=True).report
    assert any(f.rule == "V5" for f in report.findings)  # the queued edge closes a cycle

    assert mind.master_path.read_text(encoding="utf-8") == before
    assert pending_count(mind) == 1


def test_add_edge_rejects_duplicate_of_existing(repo: Path, mind: Mind) -> None:
    with pytest.raises(MutationError, match="already exists"):
        enqueue_add_edge(
            mind, "master",
            from_node="propagator.propagate_orbit", from_socket="traj",
            to_node="telemetry.write_telemetry", to_socket="data",
            evidence_file="src/telemetry.py",
        )


def test_add_edge_rejects_duplicate_already_queued(repo: Path, mind: Mind) -> None:
    kw = dict(
        from_node="telemetry.run", from_socket="path_out",
        to_node="propagator.propagate_orbit", to_socket="state0",
        evidence_file="src/telemetry.py",
    )
    enqueue_add_edge(mind, "master", **kw)
    with pytest.raises(MutationError, match="already queued"):
        enqueue_add_edge(mind, "master", **kw)


def test_human_edge_is_protected_from_casual_removal(repo: Path, mind: Mind) -> None:
    """D6: human edits are sticky."""
    edge_id = enqueue_add_edge(
        mind, "master",
        from_node="telemetry.run", from_socket="path_out",
        to_node="propagator.propagate_orbit", to_socket="state0",
        evidence_file="src/telemetry.py",
    )
    compile_mod.run(repo, check_only=False)
    assert edge_id in edge_ids(mind)

    with pytest.raises(MutationError, match="added by hand"):
        enqueue_remove_edge(mind, "master", edge_id)

    enqueue_remove_edge(mind, "master", edge_id, allow_removal=True)
    compile_mod.run(repo, check_only=False)
    assert edge_id not in edge_ids(mind)


def test_removal_is_also_queued_not_written(repo: Path, mind: Mind) -> None:
    target = edge_ids(mind)[0]
    before = mind.master_path.read_text(encoding="utf-8")

    enqueue_remove_edge(mind, "master", target)
    assert mind.master_path.read_text(encoding="utf-8") == before

    compile_mod.run(repo, check_only=False)
    assert target not in edge_ids(mind)


def test_folding_an_already_applied_edit_is_a_no_op(repo: Path, mind: Mind) -> None:
    """Replaying a queue must not duplicate edges — fold is idempotent."""
    edit = pending.Edit(
        op="add_edge", chart_id="master",
        from_node="telemetry.run", from_socket="path_out",
        to_node="propagator.propagate_orbit", to_socket="state0",
        evidence_file="src/telemetry.py",
    )
    pending.append(mind.pending_path, edit)
    compile_mod.run(repo, check_only=False)
    first = edge_ids(mind)

    pending.append(mind.pending_path, edit)  # same intent again
    compile_mod.run(repo, check_only=False)
    assert edge_ids(mind) == first


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
