"""Compile must be idempotent and must never destroy author prose."""

from __future__ import annotations

import json
from pathlib import Path

from vulcan_map.core import compile as compile_mod
from vulcan_map.core.repo import Mind


def snapshot(mind: Mind) -> dict[str, str]:
    """Every committed file under vulcan_mind/, excluding generated _build/."""
    out: dict[str, str] = {}
    for p in sorted(mind.root.rglob("*")):
        if p.is_file() and mind.build_dir not in p.parents:
            out[mind.rel(p)] = p.read_text(encoding="utf-8")
    return out


def test_compile_is_idempotent(repo: Path, mind: Mind) -> None:
    compile_mod.run(repo, check_only=False)
    first = snapshot(mind)
    compile_mod.run(repo, check_only=False)
    second = snapshot(mind)
    assert first == second, "second compile changed the tree; diffs would churn on every run"


def test_committed_chart_has_no_wallclock_timestamp(repo: Path, mind: Mind) -> None:
    """A timestamp in a committed file would break idempotence by construction."""
    compile_mod.run(repo, check_only=False)
    data = json.loads(mind.master_path.read_text(encoding="utf-8"))
    assert "generated_at" not in data.get("provenance", {})


def test_author_prose_is_byte_preserved(repo: Path, mind: Mind) -> None:
    doc = mind.nodes_dir / "telemetry" / "run.md"
    marker = "A sentence the compiler must never touch, with $\\alpha$ math in it."
    text = doc.read_text(encoding="utf-8").replace("## Purpose", f"## Purpose\n{marker}")
    doc.write_text(text, encoding="utf-8")

    compile_mod.run(repo, check_only=False)
    assert marker in doc.read_text(encoding="utf-8")


def test_generated_blocks_are_populated(repo: Path, mind: Mind) -> None:
    compile_mod.run(repo, check_only=False)
    text = (mind.nodes_dir / "propagator" / "propagate_orbit.md").read_text(encoding="utf-8")
    assert "| Direction | Socket |" in text          # ICD table
    assert "[[telemetry.run|run]]" in text            # wikilink back to upstream
    assert "**Upstream**" in text


def test_sockets_are_lifted_from_frontmatter(repo: Path, mind: Mind) -> None:
    compile_mod.run(repo, check_only=False)
    data = json.loads(mind.master_path.read_text(encoding="utf-8"))
    node = next(n for n in data["nodes"] if n["id"] == "propagator.propagate_orbit")
    assert [s["id"] for s in node["sockets"]["inputs"]] == ["state0", "tspan"]
    assert [s["id"] for s in node["sockets"]["outputs"]] == ["traj"]


def test_layout_is_deterministic_and_topological(repo: Path, mind: Mind) -> None:
    compile_mod.run(repo, check_only=False)
    data = json.loads(mind.master_path.read_text(encoding="utf-8"))
    pos = {n["id"]: n["ui"]["pos"] for n in data["nodes"]}
    assert pos["telemetry.run"][0] < pos["propagator.propagate_orbit"][0]
    assert pos["propagator.propagate_orbit"][0] < pos["telemetry.write_telemetry"][0]


def test_existing_positions_are_never_overwritten(repo: Path, mind: Mind) -> None:
    """D6: human placement is sticky."""
    compile_mod.run(repo, check_only=False)
    data = json.loads(mind.master_path.read_text(encoding="utf-8"))
    for n in data["nodes"]:
        if n["id"] == "telemetry.run":
            n["ui"]["pos"] = [-999.0, -999.0]
            n["origin"] = "human"
    mind.master_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    compile_mod.run(repo, check_only=False)
    after = json.loads(mind.master_path.read_text(encoding="utf-8"))
    moved = next(n for n in after["nodes"] if n["id"] == "telemetry.run")
    assert moved["ui"]["pos"] == [-999.0, -999.0]


def test_check_writes_nothing(repo: Path, mind: Mind) -> None:
    compile_mod.run(repo, check_only=False)
    before = snapshot(mind)
    compile_mod.run(repo, check_only=True)
    assert snapshot(mind) == before


def test_ui_drawn_edge_folds_deterministically(repo: Path, mind: Mind) -> None:
    """Draw in the UI layer, compile, and confirm the same edge lands identically.

    Runs the whole thing twice from a clean start and compares the resulting
    trees byte for byte: the drawn edge must reach canonical JSON through compile
    alone, and by a path that does not vary between runs.
    """
    from vulcan_map.core.mutations import enqueue_add_edge

    def draw_and_compile() -> dict[str, str]:
        enqueue_add_edge(
            mind, "master",
            from_node="telemetry.run", from_socket="path_out",
            to_node="propagator.propagate_orbit", to_socket="state0",
            evidence_file="src/telemetry.py",
            origin="human",
        )
        compile_mod.run(repo, check_only=False)
        return snapshot(mind)

    baseline = snapshot(mind)
    first = draw_and_compile()
    assert first != baseline, "drawing then compiling should change the tree"

    # Reset to the pre-draw state and replay the identical gesture.
    for rel, text in baseline.items():
        (mind.root / rel).write_text(text, encoding="utf-8", newline="\n")
    for rel in set(first) - set(baseline):
        (mind.root / rel).unlink()

    second = draw_and_compile()
    assert second == first, "the same drawn edge must produce the same tree"

    edge_id = "e:telemetry.run:path_out->propagator.propagate_orbit:state0"
    edges = json.loads(mind.master_path.read_text(encoding="utf-8"))["edges"]
    matching = [e for e in edges if e["id"] == edge_id]
    assert len(matching) == 1
    assert matching[0]["origin"] == "human"
    assert matching[0]["evidence"] == {"file": "src/telemetry.py"}


def test_compile_after_ui_draw_is_still_idempotent(repo: Path, mind: Mind) -> None:
    from vulcan_map.core.mutations import enqueue_add_edge

    enqueue_add_edge(
        mind, "master",
        from_node="telemetry.run", from_socket="path_out",
        to_node="propagator.propagate_orbit", to_socket="state0",
        evidence_file="src/telemetry.py",
    )
    compile_mod.run(repo, check_only=False)
    once = snapshot(mind)
    compile_mod.run(repo, check_only=False)
    assert snapshot(mind) == once


def test_pending_queue_is_not_part_of_the_compiled_tree(repo: Path, mind: Mind) -> None:
    """The queue is transient input; after compile it should not linger."""
    from vulcan_map.core.mutations import enqueue_add_edge

    enqueue_add_edge(
        mind, "master",
        from_node="telemetry.run", from_socket="path_out",
        to_node="propagator.propagate_orbit", to_socket="state0",
        evidence_file="src/telemetry.py",
    )
    assert mind.pending_path.exists()
    compile_mod.run(repo, check_only=False)
    assert not mind.pending_path.exists()


def test_resolved_graph_is_emitted_for_ui(repo: Path, mind: Mind) -> None:
    compile_mod.run(repo, check_only=False)
    resolved = json.loads(mind.resolved_path("master").read_text(encoding="utf-8"))
    assert len(resolved["nodes"]) == 3
    assert len(resolved["edges"]) == 4
    assert mind.index_path.exists()


def test_stale_resolved_graphs_are_pruned(repo: Path, mind: Mind) -> None:
    """A deleted subchart must not leave a live-looking artefact in _build/."""
    compile_mod.run(repo, check_only=False)
    ghost = mind.build_dir / "ghost.resolved.json"
    ghost.write_text('{"chart_id": "ghost"}', encoding="utf-8")

    compile_mod.run(repo, check_only=False)
    assert not ghost.exists()
    assert mind.resolved_path("master").exists()


def test_subchart_with_no_members_survives_a_round_trip(repo: Path, mind: Mind) -> None:
    """_prune drops empty lists, but the schema requires member_nodes.

    Without the exception, compile writes a subchart it can no longer read.
    """
    sub = {
        "schema_version": "1.0.0", "chart_id": "empty", "chart_kind": "sub",
        "derives_from": "master", "title": "Empty", "member_nodes": [],
    }
    (mind.subcharts_dir / "empty.graph.json").write_text(
        json.dumps(sub, indent=2), encoding="utf-8"
    )
    compile_mod.run(repo, check_only=False)

    written = json.loads((mind.subcharts_dir / "empty.graph.json").read_text(encoding="utf-8"))
    assert "member_nodes" in written

    from vulcan_map.core.workspace import load_workspace

    assert load_workspace(repo).chart("empty") is not None, "chart failed to reload"
