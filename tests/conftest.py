"""Fixture repo builder.

Tests construct a real repo on disk rather than mocking the filesystem, because
the rules under test (grounding, coverage, drift) are *about* the filesystem.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vulcan_map.core.repo import Mind  # noqa: E402

PROPAGATOR = '''\
def propagate_orbit(state0, tspan):
    traj = [state0]
    for _ in range(int(tspan[1] - tspan[0])):
        traj.append(traj[-1])
    return traj
'''

TELEMETRY = '''\
from .propagator import propagate_orbit


def write_telemetry(data, path):
    with open(path, "w") as fh:
        fh.write(str(data))
    return path


def run(state0, tspan, path):
    traj = propagate_orbit(state0, tspan)
    return write_telemetry(traj, path)
'''

CONFIG = """\
version: 1
project: demo
languages: [python]
default_region: all
regions:
  all:
    description: "Everything."
    include: ["src/**"]
    exclude: []
    granularity: function
grounding:
  require_symbol_match: true
  symbol_search: auto
lint:
  banned_phrases: ["a helper function", "various", "TODO"]
  min_doc_words: 20
coverage:
  require_every_in_scope_file_mapped: true
  require_subchart_per_module: true
"""

BODY = """

# {label}

## Purpose
This unit exists so that the fixture exercises the validator rules end to end
with prose long enough to clear the configured minimum word count for a node
document without tripping the banned phrase lint in any way whatsoever here.

## Interface (ICD)
<!-- vulcan:icd:begin -->
<!-- vulcan:icd:end -->

## Connections
<!-- vulcan:connections:begin -->
<!-- vulcan:connections:end -->

## Provenance
Mapped from `{file}`.
"""


def _doc(label: str, node_id: str, file: str, symbol: str, inputs, outputs, kind="function") -> str:
    fm = {
        "id": node_id,
        "label": label,
        "kind": kind,
        "inputs": inputs,
        "outputs": outputs,
        "origin": "agent",
    }
    if kind not in ("external", "group"):
        fm["source"] = {"file": file, "symbol": symbol}
    import yaml

    return "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n" + BODY.format(label=label, file=file)


def _sock(sid: str) -> dict:
    return {"id": sid, "type": "object", "description": "A socket used by the fixture."}


def _edge(fn, fs, tn, ts, kind="dataflow", file="src/telemetry.py"):
    return {
        "id": f"e:{fn}:{fs}->{tn}:{ts}",
        "from": {"node": fn, "socket": fs},
        "to": {"node": tn, "socket": ts},
        "kind": kind,
        "evidence": {"file": file},
        "origin": "agent",
    }


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A small, fully-mapped repo whose `check --strict` passes."""
    root = tmp_path / "demo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "propagator.py").write_text(PROPAGATOR, encoding="utf-8")
    (root / "src" / "telemetry.py").write_text(TELEMETRY, encoding="utf-8")

    mind = Mind(root)
    for d in (mind.graph_dir, mind.subcharts_dir, mind.nodes_dir, mind.build_dir):
        d.mkdir(parents=True, exist_ok=True)
    mind.config_path.write_text(CONFIG, encoding="utf-8")

    docs = {
        "propagator/propagate_orbit.md": _doc(
            "propagate_orbit", "propagator.propagate_orbit",
            "src/propagator.py", "propagate_orbit",
            [_sock("state0"), _sock("tspan")], [_sock("traj")],
        ),
        "telemetry/write_telemetry.md": _doc(
            "write_telemetry", "telemetry.write_telemetry",
            "src/telemetry.py", "write_telemetry",
            [_sock("data"), _sock("path")], [_sock("written_path")],
        ),
        "telemetry/run.md": _doc(
            "run", "telemetry.run", "src/telemetry.py", "run",
            [_sock("state0"), _sock("tspan"), _sock("path")],
            [_sock("state0_out"), _sock("tspan_out"), _sock("path_out")],
        ),
        # D14: the master is an operational flow, so the fixture shows where
        # data enters (an initial state) and where it leaves (a telemetry file).
        "io/initial_state.md": _doc(
            "initial_state", "io.initial_state", "", "",
            [], [_sock("state0")], kind="external",
        ),
        "io/telemetry_file.md": _doc(
            "telemetry_file", "io.telemetry_file", "", "",
            [_sock("written")], [], kind="external",
        ),
    }
    for rel, text in docs.items():
        p = mind.nodes_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    master = {
        "schema_version": "1.0.0",
        "chart_id": "master",
        "chart_kind": "master",
        "title": "demo master",
        "region": "all",
        "nodes": [
            {
                "id": "propagator.propagate_orbit", "label": "propagate_orbit",
                "kind": "function", "doc": "nodes/propagator/propagate_orbit.md",
                "source": {"file": "src/propagator.py", "symbol": "propagate_orbit"},
                "origin": "agent",
            },
            {
                "id": "telemetry.write_telemetry", "label": "write_telemetry",
                "kind": "function", "doc": "nodes/telemetry/write_telemetry.md",
                "source": {"file": "src/telemetry.py", "symbol": "write_telemetry"},
                "origin": "agent",
            },
            {
                "id": "telemetry.run", "label": "run",
                "kind": "function", "doc": "nodes/telemetry/run.md",
                "source": {"file": "src/telemetry.py", "symbol": "run"},
                "origin": "agent",
            },
            {
                "id": "io.initial_state", "label": "initial_state",
                "kind": "external", "doc": "nodes/io/initial_state.md",
                "origin": "agent",
            },
            {
                "id": "io.telemetry_file", "label": "telemetry_file",
                "kind": "external", "doc": "nodes/io/telemetry_file.md",
                "origin": "agent",
            },
        ],
        "edges": [
            _edge("io.initial_state", "state0", "telemetry.run", "state0"),
            _edge("telemetry.run", "state0_out", "propagator.propagate_orbit", "state0"),
            _edge("telemetry.run", "tspan_out", "propagator.propagate_orbit", "tspan"),
            _edge("propagator.propagate_orbit", "traj", "telemetry.write_telemetry", "data"),
            _edge("telemetry.run", "path_out", "telemetry.write_telemetry", "path"),
            _edge("telemetry.write_telemetry", "written_path", "io.telemetry_file", "written"),
        ],
    }
    mind.master_path.write_text(json.dumps(master, indent=2), encoding="utf-8")

    # Compile once so the baseline is a *compiled* map: generated blocks are
    # populated and sockets are lifted. Without this every test would also trip
    # V15 (drift), since an uncompiled map genuinely has stale empty blocks.
    from vulcan_map.core import compile as compile_mod

    compile_mod.run(root, check_only=False)
    return root


@pytest.fixture
def mind(repo: Path) -> Mind:
    return Mind(repo)


def write_master(mind: Mind, mutate) -> None:
    data = json.loads(mind.master_path.read_text(encoding="utf-8"))
    mutate(data)
    mind.master_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def rules(report) -> set[str]:
    return {f.rule for f in report.findings}
