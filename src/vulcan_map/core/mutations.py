"""UI edit intents (PLAN.md §11.3).

Topology edits made in the UI are *enqueued*, not written. `vulcan compile` folds
the queue into canonical JSON, so there is exactly one writer of chart files and
one deterministic path from intent to persisted graph.

These functions read canonical JSON to validate an intent before queuing it —
reading is unrestricted; only writing is reserved for compile.

Node positions are the deliberate exception: they are presentation state that the
compiler preserves rather than derives, and a drag would otherwise enqueue
hundreds of intents. See PLAN.md §11.3.

Kept out of the `ui` package so it is testable without Qt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import pending
from .model import derive_edge_id, Endpoint
from .pending import Edit
from .repo import Mind


class MutationError(Exception):
    pass


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")


def chart_path(mind: Mind, chart_id: str) -> Path:
    path = mind.master_path if chart_id == "master" else mind.subcharts_dir / f"{chart_id}.graph.json"
    if not path.exists():
        raise MutationError(f"No chart file for {chart_id!r} at {path}")
    return path


def _edge_list_key(data: dict[str, Any]) -> str:
    return "edges" if data.get("chart_kind") == "master" else "local_edges"


def _node_list_keys(data: dict[str, Any]) -> tuple[str, ...]:
    return ("nodes",) if data.get("chart_kind") == "master" else ("local_nodes",)


def _existing_edge_ids(mind: Mind, chart_id: str) -> set[str]:
    ids: set[str] = set()
    for path in (mind.master_path, mind.subcharts_dir / f"{chart_id}.graph.json"):
        if not path.exists():
            continue
        data = _load(path)
        for key in ("edges", "local_edges"):
            ids.update(e["id"] for e in data.get(key, []))
    return ids


def _queued_edge_ids(mind: Mind) -> set[str]:
    return {e.edge_id for e in pending.load(mind.pending_path).edits if e.op == "add_edge"}


def enqueue_add_edge(
    mind: Mind,
    chart_id: str,
    *,
    from_node: str,
    from_socket: str,
    to_node: str,
    to_socket: str,
    evidence_file: str,
    kind: str = "dataflow",
    label: str | None = None,
    origin: str = "human",
) -> str:
    """Queue a new edge. Returns its derived id.

    `evidence_file` is required and must exist on disk. Human-drawn edges are held
    to the same grounding standard as agent-written ones: an edge asserts that a
    connection is observable somewhere in the code, and neither the UI nor the
    compiler has any business fabricating that claim. Checking here as well as at
    validation time (V7) gives the person drawing immediate feedback rather than
    an error that surfaces only after the next compile.
    """
    if not evidence_file.strip():
        raise MutationError(
            "An edge must cite a file where the connection is observable (V7)."
        )
    if not (mind.repo_root / evidence_file).is_file():
        raise MutationError(
            f"Evidence file {evidence_file!r} does not exist. "
            "An edge must cite real code where the connection is observable (V7)."
        )

    chart_path(mind, chart_id)  # fail early if the chart is missing

    edge_id = derive_edge_id(Endpoint(from_node, from_socket), Endpoint(to_node, to_socket))
    if edge_id in _existing_edge_ids(mind, chart_id):
        raise MutationError("That connection already exists.")
    if edge_id in _queued_edge_ids(mind):
        raise MutationError("That connection is already queued for the next compile.")

    pending.append(
        mind.pending_path,
        Edit(
            op="add_edge",
            chart_id=chart_id,
            from_node=from_node,
            from_socket=from_socket,
            to_node=to_node,
            to_socket=to_socket,
            kind=kind,
            label=label,
            evidence_file=evidence_file,
            origin=origin,
        ),
    )
    return edge_id


def enqueue_remove_edge(
    mind: Mind, chart_id: str, edge_id: str, *, allow_removal: bool = False
) -> dict[str, Any]:
    """Queue an edge removal, returning the edge as it currently stands.

    Agent-authored edges are removable from the UI (a person is driving); D6's
    protection runs the other way, stopping agents from removing human edits.
    """
    path = chart_path(mind, chart_id)
    data = _load(path)
    edges = data.get(_edge_list_key(data), [])

    match = next((e for e in edges if e["id"] == edge_id), None)
    if match is None:
        raise MutationError(f"Edge {edge_id!r} is not in chart {chart_id!r}.")
    if match.get("origin") == "human" and not allow_removal:
        raise MutationError(
            "This edge was added by hand (origin: human). "
            "Removing it needs an explicit confirmation."
        )

    pending.append(
        mind.pending_path,
        Edit(
            op="remove_edge",
            chart_id=chart_id,
            from_node=match["from"]["node"],
            from_socket=match["from"]["socket"],
            to_node=match["to"]["node"],
            to_socket=match["to"]["socket"],
            kind=match.get("kind", "dataflow"),
            origin=match.get("origin", "agent"),
        ),
    )
    return match


def set_position(mind: Mind, chart_id: str, node_id: str, pos: tuple[float, float]) -> None:
    """Persist a node position directly.

    Positions bypass the queue by design: they are presentation state the compiler
    preserves rather than derives, they carry no semantics to validate, and a
    single drag would otherwise enqueue an intent per mouse move.

    For a subchart the position is stored as a `pos_overrides` entry rather than
    on the node, so moving a node in a subchart cannot move it in the master.
    """
    path = chart_path(mind, chart_id)
    data = _load(path)

    for key in _node_list_keys(data):
        for node in data.get(key, []):
            if node["id"] == node_id:
                node.setdefault("ui", {})["pos"] = [float(pos[0]), float(pos[1])]
                _save(path, data)
                return

    if data.get("chart_kind") == "sub":
        overrides = data.setdefault("ui", {}).setdefault("pos_overrides", {})
        overrides[node_id] = [float(pos[0]), float(pos[1])]
        _save(path, data)
        return

    raise MutationError(f"Node {node_id!r} is not in chart {chart_id!r}.")


def owning_chart(mind: Mind, chart_id: str, edge_id: str) -> str:
    """Which chart file actually holds an edge — master edges are inherited by
    subcharts, so deleting one from a subchart view must edit the master."""
    sub_path = mind.subcharts_dir / f"{chart_id}.graph.json"
    if chart_id != "master" and sub_path.exists():
        data = _load(sub_path)
        if any(e["id"] == edge_id for e in data.get("local_edges", [])):
            return chart_id
    return "master"


def pending_count(mind: Mind) -> int:
    return len(pending.load(mind.pending_path))
