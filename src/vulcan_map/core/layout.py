"""Deterministic layered DAG layout (PLAN.md §7.2 step 7).

Determinism is a hard requirement, not a nicety: positions are written into
committed JSON, so a layout that varied run-to-run would produce spurious diffs
on every compile. Every tie is broken by node id.
"""

from __future__ import annotations

from collections import defaultdict

from .model import Edge, Node

X_SPACING = 320.0
Y_SPACING = 150.0
X_ORIGIN = 80.0
Y_ORIGIN = 80.0

_BARYCENTRE_PASSES = 4


def _layers(nodes: list[Node], edges: list[Edge]) -> dict[str, int]:
    """Longest-path layering over non-feedback edges."""
    ids = {n.id for n in nodes}
    flow = [e for e in edges if not e.is_feedback and e.from_.node in ids and e.to.node in ids]

    preds: dict[str, set[str]] = defaultdict(set)
    succs: dict[str, set[str]] = defaultdict(set)
    for e in flow:
        preds[e.to.node].add(e.from_.node)
        succs[e.from_.node].add(e.to.node)

    indegree = {n.id: len(preds[n.id]) for n in nodes}
    layer = {n.id: 0 for n in nodes}

    # Kahn's algorithm, popping in sorted order for determinism.
    ready = sorted(nid for nid, d in indegree.items() if d == 0)
    seen = 0
    while ready:
        nid = ready.pop(0)
        seen += 1
        for succ in sorted(succs[nid]):
            layer[succ] = max(layer[succ], layer[nid] + 1)
            indegree[succ] -= 1
            if indegree[succ] == 0:
                ready.append(succ)
                ready.sort()

    if seen != len(nodes):
        # A cycle survived (validation reports it as V5); fall back to a stable
        # layering so the UI can still draw something rather than failing.
        for nid in sorted(layer):
            if indegree.get(nid, 0) > 0:
                layer[nid] = max(layer.values(), default=0) + 1
    return layer


def _order_within_layers(
    layer: dict[str, int], edges: list[Edge]
) -> dict[int, list[str]]:
    buckets: dict[int, list[str]] = defaultdict(list)
    for nid, lv in layer.items():
        buckets[lv].append(nid)
    for lv in buckets:
        buckets[lv].sort()

    preds: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if not e.is_feedback:
            preds[e.to.node].append(e.from_.node)

    for _ in range(_BARYCENTRE_PASSES):
        for lv in sorted(buckets):
            if lv == 0:
                continue
            prev_index = {nid: i for i, nid in enumerate(buckets[lv - 1])}

            def key(nid: str) -> tuple[float, str]:
                ranks = [prev_index[p] for p in preds[nid] if p in prev_index]
                bary = sum(ranks) / len(ranks) if ranks else float(len(prev_index))
                return (bary, nid)  # id breaks ties → deterministic

            buckets[lv].sort(key=key)
    return buckets


def assign_positions(nodes: list[Node], edges: list[Edge]) -> int:
    """Give every node lacking `pos` a position. Returns how many were assigned.

    Existing positions are never overwritten — D6 makes human placement sticky.
    """
    missing = [n for n in nodes if n.pos is None]
    if not missing:
        return 0

    layer = _layers(nodes, edges)
    buckets = _order_within_layers(layer, edges)
    taken = {n.pos for n in nodes if n.pos is not None}

    by_id = {n.id: n for n in nodes}
    assigned = 0
    for lv in sorted(buckets):
        for row, nid in enumerate(buckets[lv]):
            node = by_id[nid]
            if node.pos is not None:
                continue
            x = X_ORIGIN + lv * X_SPACING
            y = Y_ORIGIN + row * Y_SPACING
            while (x, y) in taken:
                y += Y_SPACING
            node.pos = (x, y)
            taken.add((x, y))
            assigned += 1
    return assigned
