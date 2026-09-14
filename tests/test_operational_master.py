"""D14: the master chart is the operational flow, not the package tree.

The first SpaceAGORA master passed every rule and told a reader nothing:
thirteen `include` arrows into a root module, no inputs, no outputs, and a root
you could not click. These tests pin that shape as a failure.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import rules, write_master

from vulcan_map.core import compile as compile_mod
from vulcan_map.core.repo import Mind
from vulcan_map.ui.session import Session


def check(repo: Path):
    return compile_mod.run(repo, check_only=True).report


def _drop_node(d, node_id):
    d["nodes"] = [n for n in d["nodes"] if n["id"] != node_id]
    d["edges"] = [e for e in d["edges"] if node_id not in (e["from"]["node"], e["to"]["node"])]


def test_fixture_master_is_operational(repo: Path) -> None:
    assert "V21" not in rules(check(repo))


def test_master_without_an_external_sink_fails(repo: Path, mind: Mind) -> None:
    write_master(mind, lambda d: _drop_node(d, "io.telemetry_file"))
    found = check(repo)
    assert "V21" in rules(found)
    assert "sink" in next(f for f in found.findings if f.rule == "V21").message


def test_master_without_an_external_source_fails(repo: Path, mind: Mind) -> None:
    write_master(mind, lambda d: _drop_node(d, "io.initial_state"))
    assert "V21" in rules(check(repo))


def test_macro_block_must_open_a_chart(repo: Path, mind: Mind) -> None:
    """A group node on the master with nothing behind it is a dead end."""
    def mutate(d):
        d["nodes"].append({
            "id": "flow.solve", "label": "Solve loop", "kind": "group",
            "doc": "nodes/telemetry/run.md", "origin": "agent",
        })
    write_master(mind, mutate)
    found = check(repo)
    msgs = [f.message for f in found.findings if f.rule == "V21"]
    assert any("cannot be clicked through" in m for m in msgs)


def test_opens_must_name_a_real_chart(repo: Path, mind: Mind) -> None:
    def mutate(d):
        d["nodes"].append({
            "id": "flow.solve", "label": "Solve loop", "kind": "group",
            "doc": "nodes/telemetry/run.md", "origin": "agent", "opens": "nowhere",
        })
    write_master(mind, mutate)
    msgs = [f.message for f in check(repo).findings if f.rule == "V21"]
    assert any("does not exist" in m for m in msgs)


def test_leaf_symbol_nodes_need_nothing_to_open(repo: Path) -> None:
    """Function nodes are the finest granularity; V21b does not apply to them."""
    msgs = [f.message for f in check(repo).findings if f.rule == "V21"]
    assert not any("clicked through" in m for m in msgs)


def test_package_tree_master_is_a_hub(repo: Path, mind: Mind) -> None:
    """The exact shape of the first SpaceAGORA master: everything -> root."""
    def mutate(d):
        for i in range(8):
            d["nodes"].append({
                "id": f"module.m{i}", "label": f"m{i}", "kind": "module",
                "doc": "nodes/telemetry/run.md", "origin": "agent",
                "opens": "master",
            })
            d["edges"].append({
                "id": f"e:module.m{i}:x->telemetry.run:state0",
                "from": {"node": f"module.m{i}", "socket": "x"},
                "to": {"node": "telemetry.run", "socket": "state0"},
                "kind": "call", "evidence": {"file": "src/telemetry.py"}, "origin": "agent",
            })
    write_master(mind, mutate)
    msgs = [f.message for f in check(repo).findings if f.rule == "V21"]
    assert any("is a hub" in m and "telemetry.run" in m for m in msgs)


def test_opens_makes_a_block_clickable_in_the_ui(repo: Path, mind: Mind) -> None:
    (mind.subcharts_dir / "detail.graph.json").write_text(json.dumps({
        "schema_version": "1.0.0", "chart_id": "detail", "chart_kind": "sub",
        "derives_from": "master", "title": "Detail",
        "member_nodes": ["telemetry.run"], "local_nodes": [], "local_edges": [],
    }, indent=2), encoding="utf-8")

    def mutate(d):
        d["nodes"].append({
            "id": "flow.solve", "label": "Solve loop", "kind": "group",
            "doc": "nodes/telemetry/run.md", "origin": "agent", "opens": "detail",
        })
    write_master(mind, mutate)
    compile_mod.run(repo, check_only=False)

    session = Session(repo_root=repo)
    session.reload()
    assert session.expansion_for("flow.solve", from_chart="master") == "detail"


def test_rule_can_be_switched_off_per_repo(repo: Path, mind: Mind) -> None:
    cfg = mind.config_path.read_text(encoding="utf-8")
    mind.config_path.write_text(
        cfg + "  require_operational_master: false\n", encoding="utf-8"
    )
    write_master(mind, lambda d: _drop_node(d, "io.telemetry_file"))
    assert "V21" not in rules(check(repo))
