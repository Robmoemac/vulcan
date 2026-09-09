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


def test_resolved_graph_is_emitted_for_ui(repo: Path, mind: Mind) -> None:
    compile_mod.run(repo, check_only=False)
    resolved = json.loads(mind.resolved_path("master").read_text(encoding="utf-8"))
    assert len(resolved["nodes"]) == 3
    assert len(resolved["edges"]) == 4
    assert mind.index_path.exists()
