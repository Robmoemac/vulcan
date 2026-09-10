"""Loaded state for one compile/check run.

Loading is separated from compiling so that `vulcan check` can run every rule
without writing anything (PLAN.md §7.2).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config, Region, load_config
from .frontmatter import NodeDoc, parse as parse_doc
from .model import Chart, Node
from .repo import Mind
from .resolve import ResolveError, resolve
from .schemas import validate_against


@dataclass(slots=True)
class LoadIssue:
    """A failure that prevented something from loading at all (always fatal)."""

    path: Path
    message: str
    rule: str = "V1"


@dataclass(slots=True)
class Workspace:
    repo_root: Path
    mind: Mind
    config: Config
    region: Region
    charts: list[Chart] = field(default_factory=list)
    docs: list[NodeDoc] = field(default_factory=list)
    issues: list[LoadIssue] = field(default_factory=list)

    @property
    def master(self) -> Chart | None:
        return next((c for c in self.charts if c.is_master), None)

    @property
    def subcharts(self) -> list[Chart]:
        return [c for c in self.charts if not c.is_master]

    def chart(self, chart_id: str) -> Chart | None:
        return next((c for c in self.charts if c.chart_id == chart_id), None)

    def all_nodes(self) -> list[Node]:
        seen: dict[str, Node] = {}
        for chart in self.charts:
            for node in chart.all_nodes():
                seen.setdefault(node.id, node)
        return [seen[k] for k in sorted(seen)]

    def doc_by_id(self, node_id: str) -> NodeDoc | None:
        return next((d for d in self.docs if d.id == node_id), None)

    def chart_of(self, node_id: str) -> Chart | None:
        for chart in self.charts:
            if any(n.id == node_id for n in chart.all_nodes()):
                return chart
        return None

    def resolved(self) -> dict[str, object]:
        out: dict[str, object] = {}
        master = self.master
        index = {n.id: n for c in self.charts for n in c.all_nodes()}
        for chart in self.charts:
            try:
                out[chart.chart_id] = resolve(chart, master, self.region, index)
            except ResolveError as exc:
                self.issues.append(LoadIssue(path=chart.path or self.mind.root, message=str(exc), rule="V3"))
        return out

    def in_scope_files(self) -> list[str]:
        return self.config.in_scope_files(self.repo_root, self.region)


def load_workspace(repo_root: Path, region_name: str | None = None) -> Workspace:
    mind = Mind(repo_root)
    config = load_config(mind.config_path)
    region = config.region(region_name)

    ws = Workspace(repo_root=repo_root, mind=mind, config=config, region=region)

    for path in mind.chart_paths():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            ws.issues.append(LoadIssue(path=path, message=f"unreadable chart JSON: {exc}"))
            continue
        errors = validate_against("graph.schema.json", raw)
        if errors:
            for e in errors:
                ws.issues.append(LoadIssue(path=path, message=e))
            continue
        ws.charts.append(Chart.from_dict(raw, path=path))

    for path in mind.node_doc_paths():
        try:
            doc = parse_doc(path)
        except Exception as exc:  # frontmatter errors carry their own path context
            ws.issues.append(LoadIssue(path=path, message=str(exc)))
            continue
        errors = validate_against("node-frontmatter.schema.json", doc.meta)
        if errors:
            for e in errors:
                ws.issues.append(LoadIssue(path=path, message=f"frontmatter {e}"))
            continue
        ws.docs.append(doc)

    return ws
