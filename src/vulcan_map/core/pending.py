"""Pending UI edits, folded into canonical JSON by the compile step.

Drawing a noodle does not write a chart file. It appends an intent to this
queue; `vulcan compile` is the single authority that folds the queue into
canonical JSON, exactly as it is the single authority for lifted sockets and
regenerated blocks (PLAN.md §7.2 step 4a, §11.3).

The queue is authored input, so it lives beside the charts rather than under
_build/, and it carries nothing non-deterministic — no timestamps, no ordering
by wall clock. Folding the same queue onto the same charts always produces the
same result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .model import Chart, Edge, Endpoint, Evidence, derive_edge_id

QUEUE_VERSION = 1

EditOp = Literal["add_edge", "remove_edge"]


class PendingError(Exception):
    pass


@dataclass(slots=True)
class Edit:
    op: EditOp
    chart_id: str
    from_node: str
    from_socket: str
    to_node: str
    to_socket: str
    kind: str = "dataflow"
    label: str | None = None
    evidence_file: str | None = None
    origin: str = "human"

    @property
    def edge_id(self) -> str:
        return derive_edge_id(
            Endpoint(self.from_node, self.from_socket),
            Endpoint(self.to_node, self.to_socket),
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Edit:
        return cls(
            op=d["op"],
            chart_id=d["chart_id"],
            from_node=d["from"]["node"],
            from_socket=d["from"]["socket"],
            to_node=d["to"]["node"],
            to_socket=d["to"]["socket"],
            kind=d.get("kind", "dataflow"),
            label=d.get("label"),
            evidence_file=(d.get("evidence") or {}).get("file"),
            origin=d.get("origin", "human"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "op": self.op,
            "chart_id": self.chart_id,
            "from": {"node": self.from_node, "socket": self.from_socket},
            "to": {"node": self.to_node, "socket": self.to_socket},
            "kind": self.kind,
            "origin": self.origin,
        }
        if self.label:
            out["label"] = self.label
        if self.evidence_file:
            out["evidence"] = {"file": self.evidence_file}
        return out

    def to_edge(self) -> Edge:
        if not self.evidence_file:
            raise PendingError(f"Edit {self.edge_id} carries no evidence file.")
        return Edge(
            from_=Endpoint(self.from_node, self.from_socket),
            to=Endpoint(self.to_node, self.to_socket),
            kind=self.kind,  # type: ignore[arg-type]
            evidence=Evidence(file=self.evidence_file),
            label=self.label,
            origin=self.origin,  # type: ignore[arg-type]
        )


@dataclass(slots=True)
class Queue:
    edits: list[Edit] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.edits)

    def to_dict(self) -> dict[str, Any]:
        return {"version": QUEUE_VERSION, "edits": [e.to_dict() for e in self.edits]}


def load(path: Path) -> Queue:
    if not path.exists():
        return Queue()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PendingError(f"{path}: unreadable pending queue: {exc}") from exc
    if raw.get("version") != QUEUE_VERSION:
        raise PendingError(
            f"{path}: pending queue version {raw.get('version')!r} is not supported."
        )
    return Queue(edits=[Edit.from_dict(e) for e in raw.get("edits", [])])


def save(path: Path, queue: Queue) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(queue.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def append(path: Path, edit: Edit) -> None:
    queue = load(path)
    queue.edits.append(edit)
    save(path, queue)


def clear(path: Path) -> None:
    """Drop the queue once its edits are in canonical JSON."""
    path.unlink(missing_ok=True)


def fold(charts: list[Chart], queue: Queue) -> tuple[int, list[str]]:
    """Apply queued edits to in-memory charts.

    Returns (applied, problems). Deterministic: edits apply in queue order, edge
    identity is derived from endpoints, and re-adding an edge that already exists
    is a no-op rather than a duplicate. Folding is therefore idempotent — the
    same queue folded twice yields the same charts.
    """
    by_id = {c.chart_id: c for c in charts}
    master = next((c for c in charts if c.is_master), None)
    applied = 0
    problems: list[str] = []

    for edit in queue.edits:
        chart = by_id.get(edit.chart_id) or master
        if chart is None:
            problems.append(f"pending edit targets unknown chart {edit.chart_id!r}")
            continue

        edges = chart.edges if chart.is_master else chart.local_edges

        if edit.op == "add_edge":
            if any(e.id == edit.edge_id for e in edges):
                continue  # already folded in a previous compile
            try:
                edges.append(edit.to_edge())
            except PendingError as exc:
                problems.append(str(exc))
                continue
            applied += 1

        elif edit.op == "remove_edge":
            match = next((e for e in edges if e.id == edit.edge_id), None)
            if match is None:
                continue  # already removed
            edges.remove(match)
            applied += 1

        else:
            problems.append(f"unknown pending op {edit.op!r}")

    return applied, problems
