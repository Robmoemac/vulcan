"""Cross-cutting workflow views (D12).

Seeds are semantic and authored; membership is mechanical and generated. These
tests pin both halves, and pin that a workflow borrows existing nodes rather
than building a second, shallower model of the same code.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import rules

from vulcan_map.core import compile as compile_mod, workflow as workflow_mod
from vulcan_map.core.repo import Mind
from vulcan_map.core.workspace import load_workspace

BASE = {
    "schema_version": "1.0.0",
    "chart_kind": "workflow",
    "derives_from": "master",
    "traversal": {"direction": "downstream", "max_depth": 4},
}


def write_flow(mind: Mind, body: dict) -> Path:
    path = mind.subcharts_dir / f"{body['chart_id']}.graph.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return path


def check(repo: Path):
    return compile_mod.run(repo, check_only=True).report


def flow(mind: Mind, chart_id: str) -> dict:
    return json.loads((mind.subcharts_dir / f"{chart_id}.graph.json").read_text(encoding="utf-8"))


# --- closure is mechanical and deterministic -----------------------------------

def test_membership_is_generated_from_seeds(repo: Path, mind: Mind) -> None:
    write_flow(mind, {
        **BASE, "chart_id": "flow", "title": "Flow",
        "seeds": [{"node": "telemetry.run", "why": "entry point"}],
        "member_nodes": [],
    })
    compile_mod.run(repo, check_only=False)

    members = flow(mind, "flow")["member_nodes"]
    # run -> propagate_orbit -> write_telemetry -> the output file, all reached
    assert set(members) == {
        "telemetry.run", "propagator.propagate_orbit", "telemetry.write_telemetry",
        "io.telemetry_file",
    }


def test_authored_membership_is_overwritten_by_the_computed_closure(
    repo: Path, mind: Mind
) -> None:
    """A hand-typed member list must not be able to make a view lie."""
    write_flow(mind, {
        **BASE, "chart_id": "flow", "title": "Flow",
        "seeds": [{"node": "telemetry.run"}],
        "member_nodes": ["propagator.propagate_orbit"],  # deliberately wrong
    })
    compile_mod.run(repo, check_only=False)
    assert "telemetry.run" in flow(mind, "flow")["member_nodes"]


def test_membership_tracks_the_code_without_being_re_authored(
    repo: Path, mind: Mind
) -> None:
    """Map something new the workflow touches; the view picks it up on recompile."""
    write_flow(mind, {
        **BASE, "chart_id": "flow", "title": "Flow",
        "seeds": [{"node": "telemetry.run"}], "member_nodes": [],
    })
    compile_mod.run(repo, check_only=False)
    before = set(flow(mind, "flow")["member_nodes"])

    data = json.loads(mind.master_path.read_text(encoding="utf-8"))
    data["edges"].append({
        "id": "e:telemetry.write_telemetry:written_path->telemetry.run:path",
        "from": {"node": "telemetry.write_telemetry", "socket": "written_path"},
        "to": {"node": "telemetry.run", "socket": "path"},
        "kind": "feedback",
        "evidence": {"file": "src/telemetry.py"}, "origin": "agent",
    })
    mind.master_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    compile_mod.run(repo, check_only=False)

    assert set(flow(mind, "flow")["member_nodes"]) >= before


def test_closure_is_deterministic(repo: Path) -> None:
    ws = load_workspace(repo)
    seeds = [workflow_mod.Seed("telemetry.run")]
    t = workflow_mod.Traversal(direction="both", max_depth=3)
    a = workflow_mod.compute_closure(seeds, ws.charts, ws.all_nodes(), t)
    b = workflow_mod.compute_closure(seeds, ws.charts, ws.all_nodes(), t)
    assert a.members == b.members


def test_depth_bounds_the_reach(repo: Path) -> None:
    ws = load_workspace(repo)
    seeds = [workflow_mod.Seed("telemetry.run")]
    shallow = workflow_mod.compute_closure(
        seeds, ws.charts, ws.all_nodes(),
        workflow_mod.Traversal(direction="downstream", max_depth=1),
    )
    deep = workflow_mod.compute_closure(
        seeds, ws.charts, ws.all_nodes(),
        workflow_mod.Traversal(direction="downstream", max_depth=4),
    )
    assert set(shallow.members) <= set(deep.members)


def test_direction_changes_what_is_reached(repo: Path) -> None:
    ws = load_workspace(repo)
    t = lambda d: workflow_mod.Traversal(direction=d, max_depth=4)  # noqa: E731
    down = workflow_mod.compute_closure(
        [workflow_mod.Seed("telemetry.write_telemetry")], ws.charts, ws.all_nodes(), t("downstream")
    )
    up = workflow_mod.compute_closure(
        [workflow_mod.Seed("telemetry.write_telemetry")], ws.charts, ws.all_nodes(), t("upstream")
    )
    assert "io.initial_state" in up.members and "io.initial_state" not in down.members
    assert "io.telemetry_file" in down.members and "io.telemetry_file" not in up.members


def test_containment_edges_are_not_traversed(repo: Path, mind: Mind) -> None:
    """Following module fan-out would make every workflow "the whole subsystem"."""
    data = json.loads(mind.master_path.read_text(encoding="utf-8"))
    for n in data["nodes"]:
        if n["id"] == "propagator.propagate_orbit":
            n["kind"] = "module"
            n["covers"] = ["src/propagator.py"]
    mind.master_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    doc = mind.nodes_dir / "propagator" / "propagate_orbit.md"
    doc.write_text(doc.read_text(encoding="utf-8").replace("kind: function", "kind: module"),
                   encoding="utf-8")

    ws = load_workspace(repo)
    closure = workflow_mod.compute_closure(
        [workflow_mod.Seed("telemetry.run")], ws.charts, ws.all_nodes(),
        workflow_mod.Traversal(direction="downstream", max_depth=4),
    )
    assert "propagator.propagate_orbit" not in closure.members


# --- V18: the seeds must be real ------------------------------------------------

def test_workflow_without_seeds_fails(repo: Path, mind: Mind) -> None:
    write_flow(mind, {
        **BASE, "chart_id": "empty", "title": "Empty",
        "seeds": [], "member_nodes": [],
    })
    assert "V18" in rules(check(repo))


def test_workflow_with_unknown_seed_fails(repo: Path, mind: Mind) -> None:
    write_flow(mind, {
        **BASE, "chart_id": "ghost", "title": "Ghost",
        "seeds": [{"node": "no.such.node"}], "member_nodes": [],
    })
    found = rules(check(repo))
    assert "V18" in found


# --- V19: borrow, never duplicate -----------------------------------------------

def test_a_workflow_may_not_duplicate_an_existing_symbol(repo: Path, mind: Mind) -> None:
    """The whole point of reuse: no second, shallower model of the same code."""
    doc = mind.nodes_dir / "propagator" / "copy.md"
    doc.write_text(
        (mind.nodes_dir / "propagator" / "propagate_orbit.md").read_text(encoding="utf-8")
        .replace("id: propagator.propagate_orbit", "id: flow.copy_of_propagate"),
        encoding="utf-8",
    )
    write_flow(mind, {
        **BASE, "chart_id": "dupe", "title": "Dupe",
        "seeds": [{"node": "telemetry.run"}],
        "member_nodes": [],
        "local_nodes": [{
            "id": "flow.copy_of_propagate", "label": "propagate_orbit",
            "kind": "function", "doc": "nodes/propagator/copy.md",
            "source": {"file": "src/propagator.py", "symbol": "propagate_orbit"},
            "origin": "agent",
        }],
    })
    found = check(repo)
    assert "V19" in rules(found)
    message = next(f for f in found.findings if f.rule == "V19").message
    assert "src/propagator.py:propagate_orbit" in message


def test_borrowing_the_same_node_in_two_charts_is_fine(repo: Path, mind: Mind) -> None:
    """Membership is a reference; only *definitions* must be unique."""
    for name in ("one", "two"):
        write_flow(mind, {
            **BASE, "chart_id": name, "title": name,
            "seeds": [{"node": "telemetry.run"}], "member_nodes": [],
        })
    compile_mod.run(repo, check_only=False)
    assert "V19" not in rules(check(repo))

    shared = set(flow(mind, "one")["member_nodes"]) & set(flow(mind, "two")["member_nodes"])
    assert shared, "both views borrow the same nodes"
