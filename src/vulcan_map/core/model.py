"""Data model for charts, nodes, edges and sockets.

Field ownership follows PLAN.md §7.1: markdown owns what a thing *is*, JSON owns
how things *connect and lay out*.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Literal

NodeKind = Literal["function", "file", "module", "struct", "external", "group"]
EdgeKind = Literal["dataflow", "call", "mutates", "reads", "feedback"]
Origin = Literal["agent", "human"]

#: Edge kinds exempt from the acyclicity check (PLAN.md D5).
ACYCLIC_EXEMPT: frozenset[str] = frozenset({"feedback"})

#: Node kinds that must declare `covers` so V13 can account for files (PLAN.md D3).
COVERING_KINDS: frozenset[str] = frozenset({"module", "group"})

#: Node kinds exempt from source grounding (V6).
UNGROUNDED_KINDS: frozenset[str] = frozenset({"group", "external"})


def _prune(d: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is None or an empty container.

    Keeps emitted JSON stable and free of noise fields, which matters because
    compile output is committed and diffed.
    """
    out: dict[str, Any] = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, (list, dict)) and not v:
            continue
        out[k] = v
    return out


@dataclass(frozen=True, slots=True)
class Socket:
    id: str
    type: str | None = None
    units: str | None = None
    required: bool | None = None
    description: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Socket:
        return cls(
            id=d["id"],
            type=d.get("type"),
            units=d.get("units"),
            required=d.get("required"),
            description=d.get("description"),
        )

    def to_dict(self) -> dict[str, Any]:
        return _prune(
            {
                "id": self.id,
                "type": self.type,
                "units": self.units,
                "required": self.required,
                "description": self.description,
            }
        )


@dataclass(frozen=True, slots=True)
class Source:
    file: str | None = None
    symbol: str | None = None
    lines: tuple[int, int] | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> Source:
        if not d:
            return cls()
        lines = d.get("lines")
        return cls(
            file=d.get("file"),
            symbol=d.get("symbol"),
            lines=(int(lines[0]), int(lines[1])) if lines else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return _prune(
            {
                "file": self.file,
                "symbol": self.symbol,
                "lines": list(self.lines) if self.lines else None,
            }
        )


@dataclass(slots=True)
class Node:
    id: str
    label: str
    kind: NodeKind
    doc: str
    origin: Origin = "agent"
    source: Source = field(default_factory=Source)
    inputs: tuple[Socket, ...] = ()
    outputs: tuple[Socket, ...] = ()
    covers: tuple[str, ...] = ()
    expands: str | None = None
    tags: tuple[str, ...] = ()
    pos: tuple[float, float] | None = None
    color: str | None = None
    collapsed: bool = False

    # Set during resolve() so the UI can grey out-of-region nodes (PLAN.md §5.3).
    in_region: bool = True

    @property
    def needs_grounding(self) -> bool:
        return self.kind not in UNGROUNDED_KINDS

    @property
    def is_covering(self) -> bool:
        """Whether this node stands in for a set of files rather than a symbol.

        Keyed off actually declaring `covers`, not off `kind` alone: a Julia
        `module Foo` declaration is a symbol like any other and gets a node of
        its own under D11. Treating every module-kinded node as an aggregator
        made those symbol nodes inherit the aggregator's obligations — V13b
        demanded a subchart expanding each of them, which is meaningless.
        """
        return self.kind in COVERING_KINDS and bool(self.covers)

    def socket(self, socket_id: str) -> Socket | None:
        for s in (*self.inputs, *self.outputs):
            if s.id == socket_id:
                return s
        return None

    def has_output(self, socket_id: str) -> bool:
        return any(s.id == socket_id for s in self.outputs)

    def has_input(self, socket_id: str) -> bool:
        return any(s.id == socket_id for s in self.inputs)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Node:
        sockets = d.get("sockets") or {}
        ui = d.get("ui") or {}
        pos = ui.get("pos")
        return cls(
            id=d["id"],
            label=d["label"],
            kind=d["kind"],
            doc=d["doc"],
            origin=d.get("origin", "agent"),
            source=Source.from_dict(d.get("source")),
            inputs=tuple(Socket.from_dict(s) for s in sockets.get("inputs", [])),
            outputs=tuple(Socket.from_dict(s) for s in sockets.get("outputs", [])),
            covers=tuple(d.get("covers", ())),
            expands=d.get("expands"),
            tags=tuple(d.get("tags", ())),
            pos=(float(pos[0]), float(pos[1])) if pos else None,
            color=ui.get("color"),
            collapsed=bool(ui.get("collapsed", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        sockets = _prune(
            {
                "inputs": [s.to_dict() for s in self.inputs],
                "outputs": [s.to_dict() for s in self.outputs],
            }
        )
        ui = _prune(
            {
                "pos": list(self.pos) if self.pos else None,
                "color": self.color,
                "collapsed": self.collapsed or None,
            }
        )
        return _prune(
            {
                "id": self.id,
                "label": self.label,
                "kind": self.kind,
                "doc": self.doc,
                "source": self.source.to_dict(),
                "sockets": sockets,
                "covers": list(self.covers),
                "expands": self.expands,
                "ui": ui,
                "tags": list(self.tags),
                "origin": self.origin,
            }
        )


@dataclass(frozen=True, slots=True)
class Endpoint:
    node: str
    socket: str

    def to_dict(self) -> dict[str, str]:
        return {"node": self.node, "socket": self.socket}


@dataclass(frozen=True, slots=True)
class Evidence:
    file: str
    lines: tuple[int, int] | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Evidence:
        lines = d.get("lines")
        return cls(file=d["file"], lines=(int(lines[0]), int(lines[1])) if lines else None)

    def to_dict(self) -> dict[str, Any]:
        return _prune({"file": self.file, "lines": list(self.lines) if self.lines else None})


@dataclass(slots=True)
class Edge:
    from_: Endpoint
    to: Endpoint
    kind: EdgeKind
    evidence: Evidence
    label: str | None = None
    origin: Origin = "agent"
    id: str = ""

    def __post_init__(self) -> None:
        # IDs are derived, never authored — keeps compile idempotent and diffs
        # stable regardless of what an agent wrote (PLAN.md §6.2).
        self.id = derive_edge_id(self.from_, self.to)

    @property
    def is_feedback(self) -> bool:
        return self.kind in ACYCLIC_EXEMPT

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Edge:
        return cls(
            from_=Endpoint(**d["from"]),
            to=Endpoint(**d["to"]),
            kind=d["kind"],
            evidence=Evidence.from_dict(d["evidence"]),
            label=d.get("label"),
            origin=d.get("origin", "agent"),
        )

    def to_dict(self) -> dict[str, Any]:
        return _prune(
            {
                "id": self.id,
                "from": self.from_.to_dict(),
                "to": self.to.to_dict(),
                "kind": self.kind,
                "label": self.label,
                "evidence": self.evidence.to_dict(),
                "origin": self.origin,
            }
        )


def derive_edge_id(from_: Endpoint, to: Endpoint) -> str:
    return f"e:{from_.node}:{from_.socket}->{to.node}:{to.socket}"


@dataclass(slots=True)
class Chart:
    chart_id: str
    chart_kind: Literal["master", "sub", "workflow"]
    title: str
    schema_version: str = "1.0.0"
    region: str | None = None
    derives_from: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    # Subchart-only (PLAN.md §6.3 / D9).
    member_nodes: list[str] = field(default_factory=list)
    local_nodes: list[Node] = field(default_factory=list)
    local_edges: list[Edge] = field(default_factory=list)
    pos_overrides: dict[str, tuple[float, float]] = field(default_factory=dict)

    # Workflow-only (PLAN.md D12). Seeds are the semantic input a person or
    # agent chose; member_nodes is generated from them on every compile.
    seeds: list[Any] = field(default_factory=list)
    traversal: dict[str, Any] = field(default_factory=dict)

    #: Filesystem path this chart was loaded from; None for resolved charts.
    path: Any = None

    @property
    def is_master(self) -> bool:
        return self.chart_kind == "master"

    @property
    def is_workflow(self) -> bool:
        return self.chart_kind == "workflow"

    def node_by_id(self, node_id: str) -> Node | None:
        for n in self.all_nodes():
            if n.id == node_id:
                return n
        return None

    def all_nodes(self) -> Iterable[Node]:
        yield from self.nodes
        yield from self.local_nodes

    def all_edges(self) -> Iterable[Edge]:
        yield from self.edges
        yield from self.local_edges

    @classmethod
    def from_dict(cls, d: dict[str, Any], path: Any = None) -> Chart:
        ui = d.get("ui") or {}
        overrides = {
            k: (float(v[0]), float(v[1])) for k, v in (ui.get("pos_overrides") or {}).items()
        }
        return cls(
            chart_id=d["chart_id"],
            chart_kind=d["chart_kind"],
            title=d["title"],
            schema_version=d.get("schema_version", "1.0.0"),
            region=d.get("region"),
            derives_from=d.get("derives_from"),
            provenance=d.get("provenance", {}),
            nodes=[Node.from_dict(n) for n in d.get("nodes", [])],
            edges=[Edge.from_dict(e) for e in d.get("edges", [])],
            member_nodes=list(d.get("member_nodes", [])),
            local_nodes=[Node.from_dict(n) for n in d.get("local_nodes", [])],
            local_edges=[Edge.from_dict(e) for e in d.get("local_edges", [])],
            pos_overrides=overrides,
            seeds=list(d.get("seeds", [])),
            traversal=dict(d.get("traversal", {})),
            path=path,
        )

    def to_dict(self) -> dict[str, Any]:
        base: dict[str, Any] = {
            "schema_version": self.schema_version,
            "chart_id": self.chart_id,
            "chart_kind": self.chart_kind,
            "title": self.title,
            "region": self.region,
            "provenance": self.provenance,
        }
        if self.is_master:
            base["nodes"] = [n.to_dict() for n in self.nodes]
            base["edges"] = [e.to_dict() for e in self.edges]
            return _prune(base)

        base["derives_from"] = self.derives_from
        if self.is_workflow:
            base["seeds"] = list(self.seeds)
            base["traversal"] = dict(self.traversal)
        base["local_nodes"] = [n.to_dict() for n in self.local_nodes]
        base["local_edges"] = [e.to_dict() for e in self.local_edges]
        if self.pos_overrides:
            base["ui"] = {"pos_overrides": {k: list(v) for k, v in self.pos_overrides.items()}}
        out = _prune(base)
        # The schema requires member_nodes on a subchart, and _prune drops empty
        # lists — so a subchart with no members must still emit the key, or the
        # file compile just wrote fails to load on the next run.
        out["member_nodes"] = list(self.member_nodes)
        return out

    def copy_with(self, **kw: Any) -> Chart:
        return replace(self, **kw)


@dataclass(slots=True)
class ResolvedGraph:
    """A chart flattened for rendering. The UI renders only this (PLAN.md P3)."""

    chart_id: str
    chart_kind: str
    title: str
    region: str | None
    nodes: list[Node]
    edges: list[Edge]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "chart_id": self.chart_id,
            "chart_kind": self.chart_kind,
            "title": self.title,
            "region": self.region,
            "nodes": [
                {**n.to_dict(), "in_region": n.in_region} for n in self.nodes
            ],
            "edges": [e.to_dict() for e in self.edges],
        }
