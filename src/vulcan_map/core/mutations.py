"""Canonical-file mutations used by the UI (PLAN.md §11.3).

Every UI edit goes through here: it writes the canonical chart JSON, and the UI
then recompiles and re-renders. The UI never mutates its own scene directly,
which is what makes an unbacked connection unrepresentable rather than merely
invalid (P3).

Kept out of the `ui` package deliberately so it is testable without Qt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import derive_edge_id, Endpoint
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


def add_edge(
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
    """Add an edge. `evidence_file` is required and must exist on disk.

    Human-drawn edges are held to the same grounding standard as agent-written
    ones: an edge asserts that a connection is observable somewhere in the code,
    and the UI has no business fabricating that claim.
    """
    if not (mind.repo_root / evidence_file).is_file():
        raise MutationError(
            f"Evidence file {evidence_file!r} does not exist. "
            "An edge must cite real code where the connection is observable (V7)."
        )

    path = chart_path(mind, chart_id)
    data = _load(path)
    key = _edge_list_key(data)
    edges = data.setdefault(key, [])

    edge_id = derive_edge_id(Endpoint(from_node, from_socket), Endpoint(to_node, to_socket))
    if any(e["id"] == edge_id for e in edges):
        raise MutationError("That connection already exists.")

    edge: dict[str, Any] = {
        "id": edge_id,
        "from": {"node": from_node, "socket": from_socket},
        "to": {"node": to_node, "socket": to_socket},
        "kind": kind,
        "evidence": {"file": evidence_file},
        "origin": origin,
    }
    if label:
        edge["label"] = label
    edges.append(edge)
    _save(path, data)
    return edge_id


def remove_edge(mind: Mind, chart_id: str, edge_id: str, *, allow_removal: bool = False) -> dict[str, Any]:
    """Remove an edge, returning it so the action can be undone.

    Agent-authored edges are removable from the UI (a person is driving), but
    D6's protection runs the other way: agents may not remove human edits.
    """
    path = chart_path(mind, chart_id)
    data = _load(path)
    key = _edge_list_key(data)
    edges = data.get(key, [])

    match = next((e for e in edges if e["id"] == edge_id), None)
    if match is None:
        raise MutationError(f"Edge {edge_id!r} is not in chart {chart_id!r}.")
    if match.get("origin") == "human" and not allow_removal:
        raise MutationError(
            "This edge was added by hand (origin: human). "
            "Removing it needs an explicit confirmation."
        )
    edges.remove(match)
    _save(path, data)
    return match


def restore_edge(mind: Mind, chart_id: str, edge: dict[str, Any]) -> None:
    path = chart_path(mind, chart_id)
    data = _load(path)
    edges = data.setdefault(_edge_list_key(data), [])
    if not any(e["id"] == edge["id"] for e in edges):
        edges.append(edge)
        _save(path, data)


def set_position(mind: Mind, chart_id: str, node_id: str, pos: tuple[float, float]) -> None:
    """Persist a node position.

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
