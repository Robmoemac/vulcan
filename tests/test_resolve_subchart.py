"""Subchart resolution (D9): a subchart is a view over the master, not a fork."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import _doc, _edge, _sock, rules

from vulcan_map.core import compile as compile_mod
from vulcan_map.core.repo import Mind
from vulcan_map.core.resolve import ResolveError, resolve
from vulcan_map.core.workspace import load_workspace


def write_subchart(mind: Mind, body: dict) -> Path:
    path = mind.subcharts_dir / f"{body['chart_id']}.graph.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return path


BASE = {
    "schema_version": "1.0.0",
    "chart_kind": "sub",
    "derives_from": "master",
}


def test_master_edges_between_members_are_inherited(repo: Path, mind: Mind) -> None:
    write_subchart(mind, {
        **BASE, "chart_id": "flow", "title": "Flow",
        "member_nodes": ["propagator.propagate_orbit", "telemetry.write_telemetry"],
    })
    ws = load_workspace(repo)
    graph = resolve(ws.chart("flow"), ws.master, ws.region)

    assert {n.id for n in graph.nodes} == {
        "propagator.propagate_orbit", "telemetry.write_telemetry"
    }
    # The traj -> data edge is inherited; edges touching non-members are not.
    assert [e.id for e in graph.edges] == [
        "e:propagator.propagate_orbit:traj->telemetry.write_telemetry:data"
    ]


def test_unknown_member_is_an_error(repo: Path, mind: Mind) -> None:
    write_subchart(mind, {
        **BASE, "chart_id": "bad", "title": "Bad",
        "member_nodes": ["no.such.node"],
    })
    ws = load_workspace(repo)
    with pytest.raises(ResolveError, match="absent from the master"):
        resolve(ws.chart("bad"), ws.master, ws.region)


def test_subchart_may_not_redefine_a_master_node(repo: Path, mind: Mind) -> None:
    """V2 enforces D9: no restating a master node under the same id."""
    write_subchart(mind, {
        **BASE, "chart_id": "fork", "title": "Fork",
        "member_nodes": [],
        "local_nodes": [{
            "id": "propagator.propagate_orbit", "label": "propagate_orbit",
            "kind": "function", "doc": "nodes/propagator/propagate_orbit.md",
            "source": {"file": "src/propagator.py", "symbol": "propagate_orbit"},
            "origin": "agent",
        }],
    })
    assert "V2" in rules(compile_mod.run(repo, check_only=True).report)


def test_position_override_does_not_leak_into_master(repo: Path, mind: Mind) -> None:
    compile_mod.run(repo, check_only=False)
    write_subchart(mind, {
        **BASE, "chart_id": "moved", "title": "Moved",
        "member_nodes": ["propagator.propagate_orbit"],
        "ui": {"pos_overrides": {"propagator.propagate_orbit": [11.0, 22.0]}},
    })
    ws = load_workspace(repo)
    graph = resolve(ws.chart("moved"), ws.master, ws.region)
    assert graph.nodes[0].pos == (11.0, 22.0)

    master_node = next(
        n for n in ws.master.nodes if n.id == "propagator.propagate_orbit"
    )
    assert master_node.pos != (11.0, 22.0)


def test_local_node_expands_a_master_node(repo: Path, mind: Mind) -> None:
    doc = mind.nodes_dir / "propagator" / "inner_step.md"
    doc.write_text(
        _doc("propagate_orbit", "propagator.inner_step", "src/propagator.py",
             "propagate_orbit", [_sock("prev")], [_sock("next_state")]),
        encoding="utf-8",
    )
    write_subchart(mind, {
        **BASE, "chart_id": "detail", "title": "Detail",
        "member_nodes": ["propagator.propagate_orbit"],
        "local_nodes": [{
            "id": "propagator.inner_step", "label": "inner_step",
            "kind": "function", "doc": "nodes/propagator/inner_step.md",
            "source": {"file": "src/propagator.py", "symbol": "propagate_orbit"},
            "expands": "propagator.propagate_orbit",
            "origin": "agent",
        }],
        "local_edges": [
            _edge("propagator.propagate_orbit", "traj",
                  "propagator.inner_step", "prev", file="src/propagator.py"),
        ],
    })
    compile_mod.run(repo, check_only=False)  # edit -> compile -> check
    report = compile_mod.run(repo, check_only=True).report
    assert report.ok(), [f.format() for f in report.findings]

    ws = load_workspace(repo)
    graph = resolve(ws.chart("detail"), ws.master, ws.region)
    assert {n.id for n in graph.nodes} == {
        "propagator.propagate_orbit", "propagator.inner_step"
    }
