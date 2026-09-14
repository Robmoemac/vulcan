"""The compile pipeline (PLAN.md §7.2).

Deterministic, idempotent, offline. `compile` writes; `check` runs the identical
pipeline with every write suppressed, plus drift detection (V15).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import SCHEMA_VERSION, __version__
from . import cluster as cluster_mod
from . import handoff as handoff_mod
from . import pending as pending_mod
from . import workflow as workflow_mod
from .frontmatter import CONNECTIONS_BLOCK, ICD_BLOCK, NodeDoc, render
from .layout import assign_positions
from .model import Chart, Edge, Node, ResolvedGraph, Socket
from .repo import Mind, git_commit
from .resolve import resolve
from .validate import Report, validate
from .workspace import Workspace, load_workspace
from .worklist import build_worklist


@dataclass(slots=True)
class CompileResult:
    workspace: Workspace
    report: Report
    resolved: dict[str, ResolvedGraph] = field(default_factory=dict)
    written: list[Path] = field(default_factory=list)
    sockets_lifted: int = 0
    positions_assigned: int = 0
    pending_applied: int = 0
    clusters_added: int = 0
    check_only: bool = False

    @property
    def ok(self) -> bool:
        return self.report.ok()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _dump_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


# ---------------------------------------------------------------- step 4: lift sockets

def lift_sockets(ws: Workspace) -> int:
    """Project frontmatter-declared sockets into chart JSON (md -> json).

    Never deletes a socket present only in JSON: an edge may reference it, and
    silently removing it would turn a reportable V10 into a confusing V4.
    """
    lifted = 0
    for chart in ws.charts:
        for node in chart.all_nodes():
            doc = ws.doc_by_id(node.id)
            if doc is None:
                continue
            for key, attr in (("inputs", "inputs"), ("outputs", "outputs")):
                declared = [Socket.from_dict(s) for s in doc.meta.get(key, [])]
                current = list(getattr(node, attr))
                merged = _merge_sockets(current, declared)
                if [s.to_dict() for s in merged] != [s.to_dict() for s in current]:
                    setattr(node, attr, tuple(merged))
                    lifted += 1
    return lifted


def _merge_sockets(current: list[Socket], declared: list[Socket]) -> list[Socket]:
    """Frontmatter wins on content and ordering; JSON-only sockets are retained."""
    declared_ids = {s.id for s in declared}
    retained = [s for s in current if s.id not in declared_ids]
    return declared + retained


# ---------------------------------------------------------------- step 9: generated blocks

def generate_icd_block(node: Node) -> str:
    lines = ["| Direction | Socket | Type | Units | Required | Description |",
             "|---|---|---|---|---|---|"]
    rows = [("in", s) for s in node.inputs] + [("out", s) for s in node.outputs]
    if not rows:
        lines.append("| — | — | — | — | — | *No sockets declared.* |")
    for direction, s in rows:
        req = "yes" if s.required else ("no" if s.required is not None else "—")
        lines.append(
            f"| {direction} | `{s.id}` | {_cell(s.type)} | {_cell(s.units)} | {req} | {_cell(s.description)} |"
        )
    return "\n".join(lines)


def _cell(value: str | None) -> str:
    return value.replace("|", r"\|") if value else "—"


def generate_connections_block(
    node: Node, edges: list[Edge], by_id: dict[str, Node]
) -> str:
    upstream: list[str] = []
    downstream: list[str] = []
    for e in sorted(edges, key=lambda e: e.id):
        if e.to.node == node.id and e.from_.node in by_id:
            other = by_id[e.from_.node]
            upstream.append(
                f"- [[{other.id}|{other.label}]] · `{e.from_.socket}` → `{e.to.socket}`"
                f" · {e.kind}{_evidence_suffix(e)}"
            )
        elif e.from_.node == node.id and e.to.node in by_id:
            other = by_id[e.to.node]
            downstream.append(
                f"- `{e.from_.socket}` → [[{other.id}|{other.label}]] · `{e.to.socket}`"
                f" · {e.kind}{_evidence_suffix(e)}"
            )

    out = ["**Upstream**", ""]
    out += upstream or ["- *none*"]
    out += ["", "**Downstream**", ""]
    out += downstream or ["- *none*"]
    return "\n".join(out)


def _evidence_suffix(edge: Edge) -> str:
    ev = edge.evidence
    if ev.lines:
        return f" · `{ev.file}:{ev.lines[0]}-{ev.lines[1]}`"
    return f" · `{ev.file}`"


def expected_blocks(ws: Workspace, all_edges: list[Edge]) -> dict[Path, dict[str, str]]:
    by_id = {n.id: n for n in ws.all_nodes()}
    out: dict[Path, dict[str, str]] = {}
    for doc in ws.docs:
        node = by_id.get(doc.id or "")
        if node is None:
            continue
        out[doc.path] = {
            ICD_BLOCK: generate_icd_block(node),
            CONNECTIONS_BLOCK: generate_connections_block(node, all_edges, by_id),
        }
    return out


def _apply_blocks(doc: NodeDoc, blocks: dict[str, str]) -> str:
    body = doc.body
    tmp = NodeDoc(path=doc.path, meta=doc.meta, body=body, raw=doc.raw)
    for name, content in blocks.items():
        tmp.body = tmp.with_block(name, content)
    return render(doc.meta, tmp.body)


# ---------------------------------------------------------------- driver

def run(
    repo_root: Path,
    *,
    region: str | None = None,
    check_only: bool = False,
    strict: bool = False,
) -> CompileResult:
    ws = load_workspace(repo_root, region)
    mind = ws.mind
    result_written_early: list[Path] = []

    # Step 4a — fold queued UI edits into the in-memory charts before anything
    # else reads them. Done in check mode too, so `check` validates exactly what
    # `compile` would persist; only the writing and clearing are suppressed.
    from .workspace import LoadIssue

    queue = pending_mod.load(mind.pending_path)
    applied, problems = pending_mod.fold(ws.charts, queue)
    for problem in problems:
        ws.issues.append(LoadIssue(path=mind.pending_path, message=problem, rule="V3"))

    lifted = lift_sockets(ws)

    # Step 4c — workflow membership is generated from seeds, never authored.
    # A view that spans modules must follow the real call graph, so it cannot
    # be allowed to drift from it (D12).
    all_nodes_now = ws.all_nodes()
    for chart in ws.charts:
        if not chart.is_workflow:
            continue
        _changed, problems = workflow_mod.regenerate_membership(
            chart, ws.charts, all_nodes_now
        )
        for problem in problems:
            ws.issues.append(
                LoadIssue(path=chart.path or mind.root, message=problem, rule='V18')
            )

    # Step 4d — readability by nesting (D13). Oversized sheets are partitioned
    # into group nodes with generated nested charts. Done in memory in check
    # mode too, so `check` sees the clustered picture `compile` would write.
    clusters = cluster_mod.apply(ws)
    if not check_only:
        # Group-node doc skeletons (D13), written now so the ICD/Connections
        # blocks below are generated into them in this same run. Like scaffold,
        # a skeleton never clears the prose floor: the gate keeps failing until
        # someone writes the block's purpose.
        from .frontmatter import parse as parse_doc

        for path, text in clusters.docs_to_scaffold.items():
            if not path.exists():
                _atomic_write(path, text)
                result_written_early.append(path)
            ws.docs.append(parse_doc(path))

    master = ws.master
    # Every node in the map, so a subchart can reference one owned by another
    # chart (a cross-module call is a real edge worth drawing).
    index = {n.id: n for chart in ws.charts for n in chart.all_nodes()}
    every_edge = [e for c in ws.charts for e in c.all_edges()]
    children_of: dict[str, list[Chart]] = {}
    for c in ws.charts:
        if c.group and c.derives_from:
            children_of.setdefault(c.derives_from, []).append(c)
    resolved: dict[str, ResolvedGraph] = {}
    for chart in ws.charts:
        try:
            resolved[chart.chart_id] = resolve(
                chart, master, ws.region, index, every_edge,
                children=children_of.get(chart.chart_id),
            )
        except Exception as exc:
            ws.issues.append(LoadIssue(path=chart.path or mind.root, message=str(exc), rule="V3"))

    # Lay out the resolved graph — every node the chart shows, including members
    # borrowed from another chart, which have no meaningful position of their own
    # here. Owned nodes keep theirs on the node; borrowed ones are persisted as
    # pos_overrides so they are stable without touching the owning chart.
    assigned = 0
    for chart in ws.charts:
        graph = resolved.get(chart.chart_id)
        if graph is None:
            continue
        if chart.chart_id in clusters.reflow:
            # The sheet's contents changed (blocks appeared or moved), so every
            # stored position on it was laid out for a different sheet. Drop them
            # and let the layout engine place the new picture from scratch.
            chart.pos_overrides.clear()
            for node in graph.nodes:
                node.pos = None
            for node in (chart.nodes if chart.is_master else chart.local_nodes):
                node.pos = None
        for node in graph.nodes:
            if node.pos is None and not chart.is_master:
                node.pos = chart.pos_overrides.get(node.id)
        assigned += assign_positions(graph.nodes, graph.edges)

        owned = {n.id: n for n in (chart.nodes if chart.is_master else chart.local_nodes)}
        for node in graph.nodes:
            if node.pos is None:
                continue
            if node.id in owned:
                owned[node.id].pos = node.pos
            elif not chart.is_master:
                chart.pos_overrides[node.id] = node.pos

    all_edges = [e for c in ws.charts for e in c.all_edges()]
    # Lifted block-to-block edges exist only on resolved sheets (D13). A group
    # node's Connections block would otherwise always read "none", which is
    # exactly the wrong thing to tell a reader about a macro block.
    seen = {e.id for e in all_edges}
    for graph in resolved.values():
        for e in graph.edges:
            if e.id not in seen and (e.from_.node.startswith("grp.") or e.to.node.startswith("grp.")):
                seen.add(e.id)
                all_edges.append(e)
    blocks = expected_blocks(ws, all_edges)

    report = validate(ws, expected_blocks=blocks if check_only else None, resolved=resolved)

    result = CompileResult(
        workspace=ws,
        report=report,
        resolved=resolved,
        sockets_lifted=lifted,
        positions_assigned=assigned,
        pending_applied=applied,
        clusters_added=len(clusters.charts_added) + len(clusters.groups_added),
        check_only=check_only,
    )
    if check_only:
        return result

    result.written.extend(result_written_early)
    _write_all(ws, mind, resolved, blocks, report, strict, result)

    for chart in clusters.charts_removed:
        if chart.path and chart.path.exists():
            chart.path.unlink()

    # Cleared only after the charts are safely on disk. Validation errors do not
    # block clearing: the edit now lives in canonical JSON, where the findings
    # point at it — replaying the queue would duplicate the intent, not fix it.
    if len(queue):
        pending_mod.clear(mind.pending_path)
    return result


def _write_all(
    ws: Workspace,
    mind: Mind,
    resolved: dict[str, ResolvedGraph],
    blocks: dict[Path, dict[str, str]],
    report: Report,
    strict: bool,
    result: CompileResult,
) -> None:
    commit = git_commit(ws.repo_root)
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    for chart in ws.charts:
        if chart.path is None:
            continue
        if chart.is_master:
            # Only values that are stable for a given (repo state, tool version)
            # go in the committed file. A wall-clock stamp here would make every
            # compile a diff, defeating idempotence; it lives in _build/index.json
            # instead. None must never reach the file either — the schema types
            # these as strings, so a null would fail V1 on our own output.
            updated = {
                **{k: v for k, v in chart.provenance.items() if k != "generated_at"},
                "repo_commit": commit,
                "generator": f"vulcan-map/{__version__}",
            }
            chart.provenance = {k: v for k, v in updated.items() if v is not None}
        chart.schema_version = SCHEMA_VERSION
        _atomic_write(chart.path, _dump_json(chart.to_dict()))
        result.written.append(chart.path)

    for doc in ws.docs:
        want = blocks.get(doc.path)
        if not want:
            continue
        new_text = _apply_blocks(doc, want)
        if new_text != doc.raw:
            _atomic_write(doc.path, new_text)
            result.written.append(doc.path)

    mind.build_dir.mkdir(parents=True, exist_ok=True)

    # Drop resolved graphs for charts that no longer exist, otherwise a deleted
    # or renamed subchart leaves a stale artefact behind that still looks live.
    current = {mind.resolved_path(cid) for cid in resolved}
    for stale in mind.build_dir.glob("*.resolved.json"):
        if stale not in current:
            stale.unlink()

    for chart_id, graph in resolved.items():
        path = mind.resolved_path(chart_id)
        _atomic_write(path, _dump_json(graph.to_dict()))
        result.written.append(path)

    index = {
        "generated_at": stamp,
        "project": ws.config.project,
        "region": ws.region.name,
        "repo_commit": commit,
        "charts": [
            {
                "chart_id": g.chart_id,
                "chart_kind": g.chart_kind,
                "title": g.title,
                "nodes": len(g.nodes),
                "edges": len(g.edges),
                "resolved": mind.rel(mind.resolved_path(g.chart_id)),
            }
            for g in sorted(resolved.values(), key=lambda g: (g.chart_kind != "master", g.chart_id))
        ],
    }
    _atomic_write(mind.index_path, _dump_json(index))
    result.written.append(mind.index_path)

    worklist = build_worklist(ws)
    _atomic_write(mind.worklist_path, _dump_json(worklist))
    result.written.append(mind.worklist_path)

    _atomic_write(mind.report_path, _dump_json(report.to_dict(strict)))
    result.written.append(mind.report_path)

    gitignore = mind.build_dir / ".gitignore"
    if not gitignore.exists():
        _atomic_write(gitignore, "*\n")

    # Written last, from the state that actually reached disk. This is what an
    # incoming agent reads instead of trusting a predecessor's completion claim.
    status = handoff_mod.collect(ws, report, commit)
    result.written.extend(handoff_mod.write(mind, status))
