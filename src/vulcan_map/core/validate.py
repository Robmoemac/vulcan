"""Validator rules V1-V17 (PLAN.md §8).

`vulcan check --strict` exiting 0 is the definition of done (P1), so these rules
are the project's actual completion criterion. They are deliberately mechanical:
every one is decidable from the filesystem, with no judgement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import networkx as nx

from .config import Region
from .frontmatter import CONNECTIONS_BLOCK, ICD_BLOCK, NodeDoc
from .grounding import grounder_for
from .model import Chart, Edge, Node, Socket
from .resolve import _glob_base
from .workspace import Workspace

ERROR = "error"
WARNING = "warning"


@dataclass(slots=True)
class Finding:
    rule: str
    severity: str
    message: str
    path: str | None = None
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "hint": self.hint,
        }

    def format(self) -> str:
        loc = f"{self.path}: " if self.path else ""
        line = f"[{self.rule}] {loc}{self.message}"
        if self.hint:
            line += f"\n        → {self.hint}"
        return line


@dataclass(slots=True)
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, *findings: Finding) -> None:
        self.findings.extend(findings)

    def errors(self, strict: bool = False) -> list[Finding]:
        if strict:
            return list(self.findings)
        return [f for f in self.findings if f.severity == ERROR]

    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == WARNING]

    def ok(self, strict: bool = False) -> bool:
        return not self.errors(strict)

    def to_dict(self, strict: bool = False) -> dict[str, Any]:
        return {
            "ok": self.ok(strict),
            "strict": strict,
            "error_count": len([f for f in self.findings if f.severity == ERROR]),
            "warning_count": len(self.warnings()),
            "findings": [f.to_dict() for f in self.findings],
        }


_ID_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")


def validate(ws: Workspace, *, expected_blocks: dict[Path, dict[str, str]] | None = None) -> Report:
    report = Report()

    for issue in ws.issues:
        report.add(
            Finding(issue.rule, ERROR, issue.message, path=_rel(ws, issue.path))
        )

    nodes = ws.all_nodes()
    by_id = {n.id: n for n in nodes}

    _v2_ids(ws, nodes, report)
    _v3_v4_endpoints(ws, by_id, report)
    _v5_acyclic(ws, by_id, report)
    _v6_grounding(ws, nodes, report)
    _v7_evidence(ws, report)
    _v8_v9_docs(ws, nodes, report)
    _v10_socket_parity(ws, nodes, report)
    _v11_region(ws, nodes, report)
    _v12_prose(ws, report)
    _v13_coverage(ws, nodes, report)
    _v14_isolated(ws, by_id, report)
    if expected_blocks is not None:
        _v15_drift(ws, expected_blocks, report)
    _v16_wikilinks(ws, by_id, report)
    _v17_stale_lines(ws, nodes, report)

    return report


def _rel(ws: Workspace, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(ws.repo_root).as_posix()
    except ValueError:
        return str(path)


def _all_edges(ws: Workspace) -> Iterable[tuple[Chart, Edge]]:
    for chart in ws.charts:
        for edge in chart.all_edges():
            yield chart, edge


# ---------------------------------------------------------------- V2

def _v2_ids(ws: Workspace, nodes: list[Node], report: Report) -> None:
    """Ids must be well-formed and globally unique.

    Uniqueness is checked across *every* node definition, including two in the
    same chart: a duplicate there is worse than a cross-chart one, because the
    second definition silently shadows the first in every id lookup.
    """
    seen: dict[str, str] = {}
    for chart in ws.charts:
        for node in chart.all_nodes():
            if not _ID_RE.match(node.id):
                report.add(
                    Finding(
                        "V2", ERROR,
                        f"node id {node.id!r} does not match ^[a-z0-9_]+(\\.[a-z0-9_]+)*$",
                        path=_rel(ws, chart.path),
                    )
                )
            prior = seen.get(node.id)
            if prior is not None:
                where = (
                    f"twice in {chart.chart_id!r}"
                    if prior == chart.chart_id
                    else f"in both {prior!r} and {chart.chart_id!r}"
                )
                report.add(
                    Finding(
                        "V2", ERROR,
                        f"node id {node.id!r} is defined {where}",
                        path=_rel(ws, chart.path),
                        hint="Subcharts reference master nodes via member_nodes; "
                             "they must not redefine them (D9).",
                    )
                )
            else:
                seen[node.id] = chart.chart_id


# ---------------------------------------------------------------- V3, V4

def _v3_v4_endpoints(ws: Workspace, by_id: dict[str, Node], report: Report) -> None:
    for chart, edge in _all_edges(ws):
        where = _rel(ws, chart.path)
        for role, ep in (("from", edge.from_), ("to", edge.to)):
            node = by_id.get(ep.node)
            if node is None:
                report.add(
                    Finding(
                        "V3", ERROR,
                        f"edge {edge.id} references unknown node {ep.node!r} ({role})",
                        path=where,
                        hint="Every JSON connection must be renderable; create the node or drop the edge.",
                    )
                )
                continue
            has = node.has_output(ep.socket) if role == "from" else node.has_input(ep.socket)
            if not has:
                kind = "output" if role == "from" else "input"
                available = [
                    s.id for s in (node.outputs if role == "from" else node.inputs)
                ]
                report.add(
                    Finding(
                        "V4", ERROR,
                        f"edge {edge.id} references {kind} socket {ep.socket!r} "
                        f"which node {ep.node!r} does not declare",
                        path=where,
                        hint=f"Declared {kind}s: {', '.join(available) or '(none)'} "
                             f"— sockets are authored in the node doc's frontmatter.",
                    )
                )


# ---------------------------------------------------------------- V5

def _v5_acyclic(ws: Workspace, by_id: dict[str, Node], report: Report) -> None:
    g = nx.DiGraph()
    g.add_nodes_from(by_id)
    for _chart, edge in _all_edges(ws):
        if edge.is_feedback:
            continue
        if edge.from_.node in by_id and edge.to.node in by_id:
            g.add_edge(edge.from_.node, edge.to.node, id=edge.id)

    try:
        cycle = nx.find_cycle(g, orientation="original")
    except nx.NetworkXNoCycle:
        return
    path = " -> ".join(u for u, _v, _k in cycle) + f" -> {cycle[-1][1]}"
    report.add(
        Finding(
            "V5", ERROR,
            f"cycle among non-feedback edges: {path}",
            hint='Classify the back-edge as kind: "feedback" (D5) if it is real recursion, '
                 "or restructure the decomposition.",
        )
    )


# ---------------------------------------------------------------- V6

def _v6_grounding(ws: Workspace, nodes: list[Node], report: Report) -> None:
    if not ws.config.require_symbol_match:
        return
    for node in nodes:
        if not node.needs_grounding:
            continue
        src = node.source
        if not src.file or not src.symbol:
            report.add(
                Finding(
                    "V6", ERROR,
                    f"node {node.id!r} ({node.kind}) has no source.file/source.symbol",
                    hint="Every mapped node must name real code. Only group/external nodes are exempt.",
                )
            )
            continue
        abs_path = ws.repo_root / src.file
        if not abs_path.is_file():
            report.add(
                Finding(
                    "V6", ERROR,
                    f"node {node.id!r} cites {src.file!r}, which does not exist",
                    hint="Grounding failure — the file was renamed, or the path was invented.",
                )
            )
            continue
        grounder = grounder_for(abs_path, ws.config.symbol_search)
        if not grounder.check(abs_path, src.symbol):
            report.add(
                Finding(
                    "V6", ERROR,
                    f"node {node.id!r} cites symbol {src.symbol!r}, "
                    f"which does not occur in {src.file}",
                    path=src.file,
                    hint="Open the file and use the real identifier. Invented names fail here by design.",
                )
            )


# ---------------------------------------------------------------- V7

def _v7_evidence(ws: Workspace, report: Report) -> None:
    for chart, edge in _all_edges(ws):
        ev = edge.evidence
        if not ev.file:
            report.add(
                Finding("V7", ERROR, f"edge {edge.id} has no evidence.file",
                        path=_rel(ws, chart.path))
            )
            continue
        if not (ws.repo_root / ev.file).is_file():
            report.add(
                Finding(
                    "V7", ERROR,
                    f"edge {edge.id} cites evidence file {ev.file!r}, which does not exist",
                    path=_rel(ws, chart.path),
                    hint="Every connection must point at real code where it is observable.",
                )
            )


# ---------------------------------------------------------------- V8, V9

def _v8_v9_docs(ws: Workspace, nodes: list[Node], report: Report) -> None:
    doc_ids = {d.id for d in ws.docs if d.id}
    for node in nodes:
        doc_path = ws.mind.root / node.doc
        if not doc_path.is_file():
            report.add(
                Finding("V8", ERROR, f"node {node.id!r} points at missing doc {node.doc!r}")
            )
        elif node.id not in doc_ids:
            report.add(
                Finding(
                    "V8", ERROR,
                    f"node {node.id!r} has doc {node.doc!r} but no doc declares that id",
                )
            )

    node_ids = {n.id for n in nodes}
    for doc in ws.docs:
        if doc.id and doc.id not in node_ids:
            report.add(
                Finding(
                    "V9", ERROR,
                    f"orphan doc: {doc.id!r} is not registered in any chart",
                    path=_rel(ws, doc.path),
                    hint="Add the node to a chart, or delete the doc.",
                )
            )


# ---------------------------------------------------------------- V10

def _sockets_from_meta(meta: dict[str, Any], key: str) -> list[Socket]:
    return [Socket.from_dict(s) for s in meta.get(key, [])]


def _v10_socket_parity(ws: Workspace, nodes: list[Node], report: Report) -> None:
    for node in nodes:
        doc = ws.doc_by_id(node.id)
        if doc is None:
            continue  # V8 already reported
        for key, actual in (("inputs", node.inputs), ("outputs", node.outputs)):
            declared = {s.id for s in _sockets_from_meta(doc.meta, key)}
            present = {s.id for s in actual}
            only_json = present - declared
            if only_json:
                report.add(
                    Finding(
                        "V10", ERROR,
                        f"node {node.id!r} has {key} {sorted(only_json)} in chart JSON "
                        "but not in its doc frontmatter",
                        path=_rel(ws, doc.path),
                        hint="Sockets are authored in frontmatter and lifted into JSON; "
                             "the compiler never deletes a JSON socket because an edge may depend on it.",
                    )
                )


# ---------------------------------------------------------------- V11

def _v11_region(ws: Workspace, nodes: list[Node], report: Report) -> None:
    region = ws.region
    for node in nodes:
        if node.kind == "external":
            continue  # boundary stubs are how excluded code is represented
        if not node.source.file:
            continue
        if not region.matches(node.source.file):
            report.add(
                Finding(
                    "V11", ERROR,
                    f"node {node.id!r} maps {node.source.file!r}, which region "
                    f"{region.name!r} excludes",
                    hint='Represent excluded code as a kind: "external" stub instead of mapping it.',
                )
            )


# ---------------------------------------------------------------- V12

def _v12_prose(ws: Workspace, report: Report) -> None:
    banned = [p for p in ws.config.banned_phrases if p]
    for doc in ws.docs:
        prose = doc.prose()
        lowered = prose.lower()
        for phrase in banned:
            if phrase.lower() in lowered:
                report.add(
                    Finding(
                        "V12", ERROR,
                        f"banned phrase {phrase!r} in node doc prose",
                        path=_rel(ws, doc.path),
                        hint="Name the real function, file, or value instead of describing it vaguely.",
                    )
                )
        words = doc.word_count()
        if words < ws.config.min_doc_words:
            report.add(
                Finding(
                    "V12", ERROR,
                    f"node doc has {words} words of prose; minimum is {ws.config.min_doc_words}",
                    path=_rel(ws, doc.path),
                    hint="Generated tables do not count toward the floor — write the real design/ICD content.",
                )
            )


# ---------------------------------------------------------------- V13, V13a, V13b

def _v13_coverage(ws: Workspace, nodes: list[Node], report: Report) -> None:
    cfg = ws.config
    severity = ERROR if cfg.require_every_in_scope_file_mapped else WARNING

    direct = {n.source.file for n in nodes if n.source.file}
    covering = [n for n in nodes if n.is_covering and n.covers]

    # V13a — a covering node may not claim files outside its own module root.
    for node in covering:
        root = _module_root(node)
        for pattern in node.covers:
            base = _glob_base(pattern)
            if root and not (base == root or base.startswith(root + "/")):
                report.add(
                    Finding(
                        "V13a", ERROR,
                        f"node {node.id!r} covers {pattern!r}, which escapes its module root {root!r}",
                        hint="A node may not claim the whole tree; coverage must be earned module by module.",
                    )
                )

    in_scope = ws.in_scope_files()
    unaccounted: list[str] = []
    for rel in in_scope:
        if rel in direct:
            continue
        if any(_covers(n, rel) for n in covering):
            continue
        unaccounted.append(rel)

    if unaccounted:
        shown = "\n        ".join(unaccounted[:20])
        more = f"\n        ... and {len(unaccounted) - 20} more" if len(unaccounted) > 20 else ""
        report.add(
            Finding(
                "V13", severity,
                f"{len(unaccounted)} in-scope file(s) are not accounted for by any node:"
                f"\n        {shown}{more}",
                hint="Not finished. Run `vulcan worklist --remaining` and keep mapping.",
            )
        )

    # V13b — every module node must be expanded to function granularity somewhere.
    if cfg.require_subchart_per_module:
        expanded = {n.expands for n in nodes if n.expands}
        for node in nodes:
            if node.kind != "module":
                continue
            if node.id not in expanded:
                report.add(
                    Finding(
                        "V13b", ERROR,
                        f"module node {node.id!r} is never expanded by a subchart",
                        hint="D3: the master is module-level, so function-level completeness "
                             "is a per-subchart obligation. Build a subchart that expands it.",
                    )
                )


def _module_root(node: Node) -> str | None:
    if node.source.file:
        return str(Path(node.source.file).parent.as_posix())
    bases = [_glob_base(p) for p in node.covers]
    return min(bases, key=len) if bases else None


def _covers(node: Node, rel: str) -> bool:
    from .config import _match_any

    return _match_any(rel, node.covers)


# ---------------------------------------------------------------- V14

def _v14_isolated(ws: Workspace, by_id: dict[str, Node], report: Report) -> None:
    touched: set[str] = set()
    for _chart, edge in _all_edges(ws):
        touched.add(edge.from_.node)
        touched.add(edge.to.node)
    for nid, node in sorted(by_id.items()):
        if node.kind == "group":
            continue
        if nid not in touched:
            report.add(
                Finding(
                    "V14", WARNING,
                    f"node {nid!r} has no connections",
                    hint="An isolated node usually means a dataflow was not traced.",
                )
            )


# ---------------------------------------------------------------- V15

def _v15_drift(
    ws: Workspace, expected: dict[Path, dict[str, str]], report: Report
) -> None:
    for doc in ws.docs:
        want = expected.get(doc.path)
        if not want:
            continue
        for name in (ICD_BLOCK, CONNECTIONS_BLOCK):
            current = doc.block(name)
            if current is None:
                report.add(
                    Finding(
                        "V15", ERROR,
                        f"node doc is missing the generated '{name}' block",
                        path=_rel(ws, doc.path),
                        hint=f"Restore the <!-- vulcan:{name}:begin --> / :end --> markers.",
                    )
                )
                continue
            if current.strip() != want[name].strip():
                report.add(
                    Finding(
                        "V15", ERROR,
                        f"generated '{name}' block is out of date",
                        path=_rel(ws, doc.path),
                        hint="Run `vulcan compile` to regenerate it; do not hand-edit generated blocks.",
                    )
                )


# ---------------------------------------------------------------- V16

def _v16_wikilinks(ws: Workspace, by_id: dict[str, Node], report: Report) -> None:
    adjacency: dict[str, set[str]] = {nid: set() for nid in by_id}
    for _chart, edge in _all_edges(ws):
        if edge.from_.node in adjacency:
            adjacency[edge.from_.node].add(edge.to.node)
        if edge.to.node in adjacency:
            adjacency[edge.to.node].add(edge.from_.node)

    label_to_id = {n.label: n.id for n in by_id.values()}
    for doc in ws.docs:
        if not doc.id or doc.id not in adjacency:
            continue
        for link in doc.wikilinks():
            target = link if link in by_id else label_to_id.get(link)
            if target is None or target == doc.id:
                continue
            if target not in adjacency[doc.id]:
                report.add(
                    Finding(
                        "V16", WARNING,
                        f"prose links to [[{link}]] but no edge connects "
                        f"{doc.id!r} and {target!r}",
                        path=_rel(ws, doc.path),
                        hint="Usually a missing edge. Prose wikilinks are not edges (A4).",
                    )
                )


# ---------------------------------------------------------------- V17

def _v17_stale_lines(ws: Workspace, nodes: list[Node], report: Report) -> None:
    for node in nodes:
        src = node.source
        if not (src.file and src.symbol and src.lines):
            continue
        abs_path = ws.repo_root / src.file
        if not abs_path.is_file():
            continue  # V6 owns this
        try:
            text = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        line = grounder_for(abs_path, ws.config.symbol_search).symbol_line(text, src.symbol)
        if line is None:
            continue
        lo, hi = src.lines
        if not (lo <= line <= hi):
            report.add(
                Finding(
                    "V17", WARNING,
                    f"node {node.id!r} records lines {lo}-{hi} but {src.symbol!r} "
                    f"now appears at line {line}",
                    path=src.file,
                    hint="The map has drifted from the code. Re-run the augment skill for this area.",
                )
            )
