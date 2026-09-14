"""Chart resolution: master + subchart -> the flat graph the UI renders.

Resolution is a pure function of the canonical JSON files. That is what makes
the P3 invariant hold: the UI can only ever draw what resolution produced.
"""

from __future__ import annotations

from dataclasses import replace

from .config import Region
from .model import Chart, Edge, Endpoint, Evidence, Node, ResolvedGraph

#: Socket ids every cluster group node carries (see cluster.py).
_GROUP_IN = "members_in"
_GROUP_OUT = "members_out"


class ResolveError(Exception):
    pass


def resolve(
    chart: Chart,
    master: Chart | None,
    region: Region | None = None,
    index: dict[str, Node] | None = None,
    all_edges: list[Edge] | None = None,
    children: list[Chart] | None = None,
) -> ResolvedGraph:
    """Flatten a chart for rendering.

    `index` maps every node id in the map to its node. A subchart may reference
    any of them, not only the master's: a call from a GNC function into a
    dynamics function is real and worth drawing, and restricting membership to
    master nodes would make it unrepresentable.

    `children` are the cluster-generated charts nested directly under this one
    (D13). Their members are hidden here and replaced by the group node that
    expands into them, with the members' edges lifted onto the group.
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
        nodes, edges = _resolve_sub(chart, master, index, all_edges)

    nodes, edges = _fold_children(nodes, edges, children or [], index or {})

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
    chart: Chart,
    master: Chart | None,
    index: dict[str, Node] | None,
    all_edges: list[Edge] | None = None,
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
        # Copy so a subchart's position override cannot leak into its owner, and
        # drop the inherited position: coordinates from the chart that owns this
        # node mean nothing in this one's layout, and keeping them drops the node
        # on top of whatever the layout engine puts there.
        members.append(replace(node, pos=None))
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
    if (chart.is_workflow or chart.group) and all_edges is not None:
        # A workflow — or a generated nested sheet — borrows the real edges
        # between the nodes it spans; they live in whichever module chart owns
        # them, not in the master.
        inherited = [
            e for e in all_edges
            if e.from_.node in present and e.to.node in present
        ]
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


def _fold_children(
    nodes: list[Node], edges: list[Edge], children: list[Chart], index: dict[str, Node]
) -> tuple[list[Node], list[Edge]]:
    """Replace each child chart's members with its group node; lift their edges.

    Cluster group nodes that belong to a deeper level (owned here but expanded
    by a chart nested further down) are hidden: a block is visible only on the
    one sheet it partitions.
    """
    owner_of: dict[str, str] = {}
    for child in children:
        for nid in child.member_nodes:
            owner_of[nid] = child.group or ""
    visible_groups = {c.group for c in children if c.group}

    kept: list[Node] = []
    present: set[str] = set()
    for n in nodes:
        if n.id in owner_of:
            continue
        if n.kind == "group" and "cluster" in n.tags and n.id not in visible_groups:
            continue
        kept.append(n)
        present.add(n.id)
    for gid in sorted(visible_groups):
        if gid in present:
            continue
        g = index.get(gid)
        if g is None:
            continue
        kept.append(replace(g, pos=None))
        present.add(gid)

    if not owner_of:
        return kept, edges

    lifted: dict[str, Edge] = {}
    counts: dict[str, int] = {}
    out: list[Edge] = []
    for e in edges:
        src = owner_of.get(e.from_.node)
        dst = owner_of.get(e.to.node)
        if src is None and dst is None:
            out.append(e)
            continue
        if src is not None and src == dst:
            continue  # internal to one block: drawn on the nested sheet
        from_ep = Endpoint(src, _GROUP_OUT) if src is not None else e.from_
        to_ep = Endpoint(dst, _GROUP_IN) if dst is not None else e.to
        if from_ep.node not in present or to_ep.node not in present:
            continue
        key = f"{from_ep.node}>{to_ep.node}"
        if key not in lifted:
            lifted[key] = Edge(from_=from_ep, to=to_ep, kind=e.kind, evidence=e.evidence,
                               origin=e.origin)
            counts[key] = 0
        counts[key] += 1
    for key, e in lifted.items():
        e.label = f"{counts[key]} edge" + ("s" if counts[key] != 1 else "")
        out.append(e)
    return kept, out


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
