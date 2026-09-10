"""Cross-cutting workflow charts: named views that span modules.

A question like "show me the RL workflow" does not map onto any one module. It
starts somewhere specific and reaches through dynamics, GNC, simulation and
analysis. Two things have to be true of the answer: it must follow the *real*
call structure rather than a keyword guess, and it must reuse the nodes already
mapped instead of building a shallow parallel model of dynamics inside the RL
view.

The work therefore splits along the line between judgement and computation:

* **Seeds are semantic.** Deciding that "the RL workflow" starts at
  `train_policy!` and `rollout!` is a reading of intent that no traversal can
  derive. An agent picks them, and the choice is written into the chart file
  where a human can audit and correct it.
* **Membership is mechanical.** Given seeds, the reachable set follows from the
  traced call graph. `member_nodes` is *generated* from the seeds on every
  compile, exactly as sockets are lifted and doc blocks are regenerated, so a
  workflow view cannot quietly drift from the code it claims to describe.

Everything reachable that already exists is borrowed by reference. Only genuinely
unmapped symbols are ever created here, and V19 makes duplicating an existing
symbol a hard error.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from .model import Chart, Edge, Node

Direction = Literal["downstream", "upstream", "both"]

DEFAULT_DEPTH = 4
DEFAULT_DIRECTION: Direction = "downstream"

#: Edge kinds that represent real behaviour. Containment fan-out from a module
#: node is excluded: traversing it would pull in a module's entire contents and
#: turn every workflow view into "the whole subsystem".
BEHAVIOURAL_KINDS = frozenset({"call", "dataflow", "mutates", "reads", "feedback"})


@dataclass(frozen=True, slots=True)
class Seed:
    """An entry point a person or agent judged to belong to this workflow."""

    node: str
    why: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any] | str) -> Seed:
        if isinstance(d, str):
            return cls(node=d)
        return cls(node=d["node"], why=d.get("why", ""))

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"node": self.node}
        if self.why:
            out["why"] = self.why
        return out


@dataclass(frozen=True, slots=True)
class Traversal:
    direction: Direction = DEFAULT_DIRECTION
    max_depth: int = DEFAULT_DEPTH

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> Traversal:
        d = d or {}
        return cls(
            direction=d.get("direction", DEFAULT_DIRECTION),
            max_depth=int(d.get("max_depth", DEFAULT_DEPTH)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"direction": self.direction, "max_depth": self.max_depth}


@dataclass(slots=True)
class Closure:
    """The computed reach of a workflow's seeds."""

    members: list[str] = field(default_factory=list)
    unreachable_seeds: list[str] = field(default_factory=list)
    depth_reached: int = 0


def _behavioural_edges(
    charts: Iterable[Chart], covering: set[str]
) -> list[Edge]:
    """Real call/dataflow edges, excluding module containment fan-out."""
    out: list[Edge] = []
    for chart in charts:
        for edge in chart.all_edges():
            if edge.kind not in BEHAVIOURAL_KINDS:
                continue
            if edge.from_.node in covering or edge.to.node in covering:
                continue
            out.append(edge)
    return out


def compute_closure(
    seeds: list[Seed],
    charts: list[Chart],
    nodes: list[Node],
    traversal: Traversal,
) -> Closure:
    """Nodes reachable from `seeds` along real edges, to `max_depth`.

    Deterministic: adjacency is sorted, the frontier is processed in order, and
    the result is returned sorted. The same seeds over the same map always yield
    the same membership.
    """
    by_id = {n.id: n for n in nodes}
    covering = {n.id for n in nodes if n.is_covering}

    forward: dict[str, set[str]] = {}
    backward: dict[str, set[str]] = {}
    for edge in _behavioural_edges(charts, covering):
        forward.setdefault(edge.from_.node, set()).add(edge.to.node)
        backward.setdefault(edge.to.node, set()).add(edge.from_.node)

    if traversal.direction == "downstream":
        adjacency = [forward]
    elif traversal.direction == "upstream":
        adjacency = [backward]
    else:
        adjacency = [forward, backward]

    seen: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque()
    unreachable: list[str] = []

    for seed in seeds:
        if seed.node not in by_id:
            unreachable.append(seed.node)
            continue
        if seed.node not in seen:
            seen[seed.node] = 0
            queue.append((seed.node, 0))

    deepest = 0
    while queue:
        node_id, depth = queue.popleft()
        deepest = max(deepest, depth)
        if depth >= traversal.max_depth:
            continue
        nxt: set[str] = set()
        for table in adjacency:
            nxt |= table.get(node_id, set())
        for other in sorted(nxt):
            if other in seen or other not in by_id:
                continue
            seen[other] = depth + 1
            queue.append((other, depth + 1))

    return Closure(
        members=sorted(seen),
        unreachable_seeds=sorted(unreachable),
        depth_reached=deepest,
    )


def seeds_of(chart: Chart) -> list[Seed]:
    return [Seed.from_dict(s) for s in (chart.seeds or [])]


def regenerate_membership(chart: Chart, charts: list[Chart], nodes: list[Node]) -> tuple[int, list[str]]:
    """Recompute a workflow chart's `member_nodes` from its seeds.

    Returns (changed_count, problems). Local nodes stay local: a workflow may
    introduce a symbol nothing else has mapped, and that node belongs to it.
    """
    if chart.chart_kind != "workflow":
        return 0, []

    seeds = seeds_of(chart)
    if not seeds:
        return 0, [f"workflow {chart.chart_id!r} declares no seeds"]

    closure = compute_closure(seeds, charts, nodes, Traversal.from_dict(chart.traversal))
    local = {n.id for n in chart.local_nodes}
    members = [m for m in closure.members if m not in local]

    problems = [
        f"workflow {chart.chart_id!r} seeds an unknown node {s!r}"
        for s in closure.unreachable_seeds
    ]
    changed = 0 if members == list(chart.member_nodes) else 1
    chart.member_nodes = members
    return changed, problems
