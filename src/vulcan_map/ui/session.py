"""UI-side state: the only path from canonical files to rendered graphs.

The window holds a Session; the Session holds no graph of its own beyond what
the compiler produced. Every mutation goes file -> compile -> resolved -> render.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..core import compile as compile_mod
from ..core.model import ResolvedGraph
from ..core.repo import Mind


@dataclass(slots=True)
class ChartInfo:
    chart_id: str
    chart_kind: str
    title: str
    nodes: int
    edges: int


@dataclass(slots=True)
class Session:
    repo_root: Path
    region: str | None = None
    mind: Mind = field(init=False)
    graphs: dict[str, ResolvedGraph] = field(default_factory=dict)
    #: chart id -> {"derives_from", "group"} for nested drill-in (D13).
    chart_meta: dict[str, dict[str, str | None]] = field(default_factory=dict)
    errors: int = 0
    warnings: int = 0
    last_error: str | None = None

    def __post_init__(self) -> None:
        self.mind = Mind(self.repo_root)

    def reload(self) -> None:
        """Recompile and re-read. This is the only way graphs are populated."""
        result = compile_mod.run(self.repo_root, region=self.region, check_only=False)
        self.graphs = dict(result.resolved)
        self.chart_meta = {
            c.chart_id: {"derives_from": c.derives_from, "group": c.group}
            for c in result.workspace.charts
        }
        findings = result.report.findings
        self.errors = len([f for f in findings if f.severity == "error"])
        self.warnings = len([f for f in findings if f.severity == "warning"])
        self.last_error = next(
            (f.format() for f in findings if f.severity == "error"), None
        )

    def expansions(self) -> dict[str, list[str]]:
        """node id -> charts that expand it to finer granularity.

        This is what makes a high-level block clickable: the `expands` field has
        always been in the data, and without this the UI rendered module nodes as
        leaves with no way in.
        """
        out: dict[str, set[str]] = {}
        for graph in self.graphs.values():
            for node in graph.nodes:
                if node.expands:
                    out.setdefault(node.expands, set()).add(graph.chart_id)
        return {k: sorted(v) for k, v in sorted(out.items())}

    def expansion_for(self, node_id: str, from_chart: str | None = None) -> str | None:
        """The single best chart to open for a node, if any.

        A cluster group node (D13) opens a different sheet depending on where it
        was clicked: from a module sheet, the whole block; from a workflow sheet,
        only the workflow's members of it. That per-parent nesting is recorded on
        the generated chart (`derives_from`, `group`), so it wins over the node's
        own `expands`.
        """
        if from_chart is not None:
            for cid, graph in sorted(self.graphs.items()):
                meta = self.chart_meta.get(cid) or {}
                if meta.get("group") == node_id and meta.get("derives_from") == from_chart:
                    return cid
        charts = self.expansions().get(node_id) or []
        return charts[0] if charts else None

    def charts(self) -> list[ChartInfo]:
        return [
            ChartInfo(g.chart_id, g.chart_kind, g.title, len(g.nodes), len(g.edges))
            for g in sorted(
                self.graphs.values(), key=lambda g: (g.chart_kind != "master", g.chart_id)
            )
        ]

    def graph(self, chart_id: str) -> ResolvedGraph | None:
        return self.graphs.get(chart_id)

    def doc_path(self, chart_id: str, node_id: str) -> Path | None:
        graph = self.graph(chart_id)
        if graph is None:
            return None
        node = next((n for n in graph.nodes if n.id == node_id), None)
        if node is None:
            return None
        return self.mind.root / node.doc

    def status_text(self, chart_id: str) -> str:
        graph = self.graph(chart_id)
        n = len(graph.nodes) if graph else 0
        e = len(graph.edges) if graph else 0
        state = "PASS" if self.errors == 0 else f"FAIL ({self.errors} error)"
        warn = f" · {self.warnings} warning" if self.warnings else ""
        region = self.region or "default"
        return f"{n} nodes · {e} edges · region {region} · check: {state}{warn}"
