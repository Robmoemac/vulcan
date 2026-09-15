"""`vulcan export` — a self-contained, view-only HTML copy of the map.

The recipient needs a browser and nothing else: no conda, no PySide, no
network. Every resolved sheet, every node doc (rendered to HTML here, at
export time) and the chart hierarchy are embedded in one file behind a small
viewer that reproduces the app's read path — sidebar, node sheet with sockets
and noodles, doc panel, double-click drill-in, back navigation, search.

View-only is a property of the artefact, not a mode switch: the file carries
no pending-edit queue and no way to write one, so P3 (the UI cannot invent an
edge the JSON lacks) holds trivially. It is a snapshot; it says so in its
header, with the repo commit and the gate verdict at the moment of export.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .. import __version__
from . import compile as compile_mod
from .model import ResolvedGraph
from .repo import git_commit

_PLACEHOLDER = "/*__VULCAN_DATA__*/"
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


@dataclass(slots=True)
class ExportResult:
    path: Path
    charts: int
    nodes: int
    docs: int
    bytes: int


def _render_markdown(text: str) -> str:
    """Body markdown -> HTML. Wikilinks become in-viewer node links."""
    if text.startswith("---"):
        _, _, rest = text.partition("---\n")
        _, _, body = rest.partition("---\n")
        text = body or rest
    text = _WIKILINK_RE.sub(
        lambda m: f'<a href="#" data-node="{m.group(1).strip()}">{(m.group(2) or m.group(1)).strip()}</a>',
        text,
    )
    try:
        from markdown_it import MarkdownIt

        return MarkdownIt("commonmark", {"html": True}).enable("table").render(text)
    except Exception:  # pragma: no cover - markdown-it is a declared dependency
        return f"<pre>{text}</pre>"


def _graph_payload(g: ResolvedGraph) -> dict:
    return {
        "id": g.chart_id,
        "kind": g.chart_kind,
        "title": g.title,
        "nodes": [
            {
                "id": n.id, "label": n.label, "kind": n.kind, "doc": n.doc,
                "in_region": n.in_region, "expands": n.expands,
                "pos": list(n.pos) if n.pos else None,
                "inputs": [{"id": s.id, "type": s.type} for s in n.inputs],
                "outputs": [{"id": s.id, "type": s.type} for s in n.outputs],
                "source": n.source.to_dict(),
                "tags": list(n.tags),
            }
            for n in g.nodes
        ],
        "edges": [
            {
                "id": e.id, "from": e.from_.to_dict(), "to": e.to.to_dict(),
                "kind": e.kind, "label": e.label,
                "evidence": e.evidence.to_dict(),
            }
            for e in g.edges
        ],
    }


def build_payload(repo_root: Path, region: str | None = None) -> dict:
    """Everything the viewer needs, from a fresh check-mode compile.

    Check mode so exporting never mutates the map; the picture is exactly
    what `vulcan check` validates.
    """
    result = compile_mod.run(repo_root, region=region, check_only=True)
    ws = result.workspace
    charts = {cid: _graph_payload(g) for cid, g in sorted(result.resolved.items())}

    hierarchy = {
        c.chart_id: {"derives_from": c.derives_from, "group": c.group, "title": c.title,
                     "kind": c.chart_kind}
        for c in ws.charts
    }
    # Drill-in table: (parent chart, node) -> child chart, mirroring Session.expansion_for.
    drill: dict[str, str] = {}
    for c in ws.charts:
        if c.group and c.derives_from:
            drill[f"{c.derives_from}|{c.group}"] = c.chart_id
    expands: dict[str, list[str]] = {}
    for cid, g in result.resolved.items():
        for n in g.nodes:
            if n.expands:
                expands.setdefault(n.expands, []).append(cid)

    docs: dict[str, str] = {}
    for doc in ws.docs:
        if doc.id:
            docs[doc.id] = _render_markdown(doc.raw)

    errors = [f for f in result.report.findings if f.severity == "error"]
    return {
        "generator": f"vulcan-map/{__version__}",
        "project": ws.config.project,
        "region": ws.region.name,
        "repo_commit": git_commit(repo_root),
        "verdict": "PASS" if not errors else f"FAIL ({len(errors)} errors)",
        "charts": charts,
        "hierarchy": hierarchy,
        "drill": drill,
        "expands": {k: sorted(v) for k, v in expands.items()},
        "docs": docs,
    }


def export_html(repo_root: Path, out: Path, region: str | None = None) -> ExportResult:
    payload = build_payload(repo_root, region)
    template = resources.files("vulcan_map.export").joinpath("viewer.html").read_text(encoding="utf-8")
    if _PLACEHOLDER not in template:
        raise RuntimeError("viewer template is missing its data placeholder")
    # `</script>` inside a JSON string would end the script block early.
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = template.replace(_PLACEHOLDER, "window.VULCAN = " + blob + ";")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return ExportResult(
        path=out,
        charts=len(payload["charts"]),
        nodes=sum(len(c["nodes"]) for c in payload["charts"].values()),
        docs=len(payload["docs"]),
        bytes=out.stat().st_size,
    )
