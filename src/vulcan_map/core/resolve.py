"""Chart resolution: master + subchart -> the flat graph the UI renders.

Resolution is a pure function of the canonical JSON files. That is what makes
the P3 invariant hold: the UI can only ever draw what resolution produced.
"""

from __future__ import annotations

from dataclasses import replace

from .config import Region
from .model import Chart, Edge, Node, ResolvedGraph


class ResolveError(Exception):
    pass


def resolve(
    chart: Chart,
    master: Chart | None,
    region: Region | None = None,
    index: dict[str, Node] | None = None,
) -> ResolvedGraph:
    """Flatten a chart for rendering.

    `index` maps every node id in the map to its node. A subchart may reference
    any of them, not only the master's: a call from a GNC function into a
    dynamics function is real and worth drawing, and restricting membership to
    master nodes would make it unrepresentable.
    """
    if chart.is_master:
        nodes = list(chart.nodes)
        edges = list(chart.edges)
    else:
        if master is None and index is None:
            raise ResolveError(
                f"Subchart {chart.chart_id!r} derives from {chart.derives_from!r}, "
                "which was not loaded."
            )
        nodes, edges = _resolve_sub(chart, master, index)

    if region is not None:
        for n in nodes:
            n.in_region = _node_in_region(n, region)

    nodes.sort(key=lambda n: n.id)
    edges.sort(key=lambda e: e.id)
    return ResolvedGraph(
        chart_id=chart.chart_id,
        chart_kind=chart.chart_kind,
        title=chart.title,
        region=chart.region,
        nodes=nodes,
        edges=edges,
    )


def _resolve_sub(
    chart: Chart, master: Chart | None, index: dict[str, Node] | None
) -> tuple[list[Node], list[Edge]]:
    by_id: dict[str, Node] = dict(index or {})
    if master is not None:
        for n in master.nodes:
            by_id.setdefault(n.id, n)

    members: list[Node] = []
    missing: list[str] = []
    for nid in chart.member_nodes:
        node = by_id.get(nid)
        if node is None:
            missing.append(nid)
            continue
        # Copy so a subchart's position override cannot leak into its owner.
        members.append(replace(node))
    if missing:
        raise ResolveError(
            f"Subchart {chart.chart_id!r} references nodes absent from the master: "
            + ", ".join(sorted(missing))
        )

    nodes = members + [replace(n) for n in chart.local_nodes]
    present = {n.id for n in nodes}

    # Master edges are inherited when both endpoints are members — never copied
    # into the subchart file, so the master stays the single source for them.
    inherited = (
        [e for e in master.edges if e.from_.node in present and e.to.node in present]
        if master is not None
        else []
    )
    edges = inherited + list(chart.local_edges)

    seen: set[str] = set()
    deduped: list[Edge] = []
    for e in edges:
        if e.id in seen:
            continue
        seen.add(e.id)
        deduped.append(e)

    for nid, pos in chart.pos_overrides.items():
        for n in nodes:
            if n.id == nid:
                n.pos = pos
    return nodes, deduped


def _node_in_region(node: Node, region: Region) -> bool:
    """Out-of-region nodes are greyed, not hidden, so the boundary is visible."""
    if node.kind == "external":
        return False
    if node.source.file:
        return region.matches(node.source.file)
    if node.covers:
        # A covering node is in-region if the directory it claims is itself in-region.
        return any(region.matches(_glob_base(c)) for c in node.covers)
    return True


def _glob_base(pattern: str) -> str:
    """The literal directory prefix of a glob: 'src/sim/**/*.jl' -> 'src/sim'."""
    parts: list[str] = []
    for part in pattern.split("/"):
        if any(ch in part for ch in "*?["):
            break
        parts.append(part)
    return "/".join(parts) or pattern
