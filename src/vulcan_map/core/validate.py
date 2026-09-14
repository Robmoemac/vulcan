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


def validate(
    ws: Workspace,
    *,
    expected_blocks: dict[Path, dict[str, str]] | None = None,
    resolved: dict[str, Any] | None = None,
) -> Report:
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
    _v12_prose(ws, nodes, report)
    _v13_coverage(ws, nodes, report)
    _v14_isolated(ws, by_id, report)
    if expected_blocks is not None:
        _v15_drift(ws, expected_blocks, report)
    _v16_wikilinks(ws, by_id, report)
    _v17_stale_lines(ws, nodes, report)
    _v18_workflows(ws, by_id, report)
    _v19_no_duplicate_symbols(ws, report)
    if resolved is not None:
        _v20_sheet_size(ws, resolved, report)
    _v21_operational_master(ws, by_id, report)

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

def _v12_prose(ws: Workspace, nodes: list[Node], report: Report) -> None:
    """Anti-vagueness lint, with a word floor proportionate to what a node claims.

    The 120-word floor was calibrated for a module or subsystem doc. Applying it
    unchanged to every leaf function under D11 would force padding on a twelve
    line accessor — which is precisely the vagueness this rule exists to catch.
    Covering nodes keep the full floor; symbol-level nodes get a smaller one.
    """
    banned = [p for p in ws.config.banned_phrases if p]
    kinds = {n.id: n for n in nodes}

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

        node = kinds.get(doc.id or "")
        # Cluster group nodes summarise a file or directory; they are held to
        # the symbol floor, not the module floor (D13).
        covering = node.is_covering if node is not None else True
        floor = ws.config.min_doc_words if covering else ws.config.min_doc_words_symbol

        words = doc.word_count()
        if words < floor:
            scope = "covering" if covering else "symbol"
            report.add(
                Finding(
                    "V12", ERROR,
                    f"node doc has {words} words of prose; minimum for a {scope} "
                    f"node is {floor}",
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

    # V13a — a covering node must claim a bounded subtree that contains its anchor.
    for node in covering:
        base = _covers_base(node)
        if base is None or base in ("", ".", "/"):
            report.add(
                Finding(
                    "V13a", ERROR,
                    f"node {node.id!r} covers the entire tree ({', '.join(node.covers)})",
                    hint="A node may not claim everything; coverage is earned module by module.",
                )
            )
            continue
        src = node.source.file
        if src and not (src == base or src.startswith(base + "/")):
            report.add(
                Finding(
                    "V13a", ERROR,
                    f"node {node.id!r} covers {base!r} but its source file {src!r} "
                    "lies outside it",
                    hint="A covering node must be anchored inside the subtree it claims.",
                )
            )

    # V13c — two covering nodes claiming the same file leaves ownership ambiguous.
    claimed: dict[str, str] = {}
    for node in sorted(covering, key=lambda n: n.id):
        for rel in ws.in_scope_files():
            if not _covers(node, rel):
                continue
            prior = claimed.get(rel)
            if prior is not None:
                report.add(
                    Finding(
                        "V13c", ERROR,
                        f"{rel} is covered by both {prior!r} and {node.id!r}",
                        hint="Each file must have exactly one owning module node.",
                    )
                )
            else:
                claimed[rel] = node.id

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
            # Only real aggregators carry this obligation. A Julia `module Foo`
            # symbol node is module-kinded but covers nothing.
            if not node.is_covering:
                continue
            if node.id not in expanded:
                report.add(
                    Finding(
                        "V13b", ERROR,
                        f"covering node {node.id!r} is never expanded by a subchart",
                        hint="D3: the master is module-level, so function-level completeness "
                             "is a per-subchart obligation. Build a subchart that expands it.",
                    )
                )

    # V13e — per-symbol granularity (D11).
    #
    # V13d forces every file to be described by *something*. That still permits
    # one node standing in for a file with forty functions in it, which is what
    # shipped the first time and made the map unusable: you could not click into
    # anything, and call edges had nothing to resolve against. Every significant
    # symbol must now be a node in its own right.
    #
    # Only languages whose grounder can enumerate declarations deterministically
    # are checked — guessing at symbols would make this rule unfalsifiable.
    if cfg.require_node_per_symbol:
        mapped_by_file: dict[str, set[str]] = {}
        for n in nodes:
            if n.source.file and n.source.symbol and not n.is_covering:
                mapped_by_file.setdefault(n.source.file, set()).add(n.source.symbol)

        gaps: list[tuple[str, list[str]]] = []
        for rel in in_scope:
            abs_path = ws.repo_root / rel
            if not abs_path.is_file():
                continue
            grounder = grounder_for(abs_path, ws.config.symbol_search)
            if not grounder.enumerates:
                continue
            try:
                text = abs_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            significant = {d.symbol for d in grounder.declarations(text)}
            if not significant:
                continue
            missing = sorted(significant - mapped_by_file.get(rel, set()))
            if missing:
                gaps.append((rel, missing))

        if gaps:
            total = sum(len(m) for _f, m in gaps)
            shown = "\n        ".join(
                f"{f} — {len(m)} unmapped: {', '.join(m[:6])}"
                + (" …" if len(m) > 6 else "")
                for f, m in gaps[:15]
            )
            more = f"\n        ... and {len(gaps) - 15} more file(s)" if len(gaps) > 15 else ""
            report.add(
                Finding(
                    "V13e", ERROR,
                    f"{total} significant symbol(s) across {len(gaps)} file(s) have no "
                    f"node of their own:\n        {shown}{more}",
                    hint="D11: a node per significant symbol, not one node standing in "
                         "for a whole file. Run `vulcan scaffold` to generate the missing "
                         "nodes and docs, then write their prose.",
                )
            )

    # V13d — depth, not just accounting.
    #
    # V13 alone is satisfiable by a `covers` glob, and V13b by a single token node
    # per module. Dogfooding on a 205-file repo produced a map where 186 files had
    # no representation at all and both rules still passed — exactly the premature
    # "done" this design exists to prevent. Coverage means every in-scope file is
    # actually described by something, not merely claimed by a glob.
    if cfg.require_function_node_per_file:
        described = {
            n.source.file for n in nodes if n.source.file and not n.is_covering
        }
        undescribed = [rel for rel in in_scope if rel not in described]
        if undescribed:
            shown = "\n        ".join(undescribed[:20])
            more = (
                f"\n        ... and {len(undescribed) - 20} more"
                if len(undescribed) > 20
                else ""
            )
            report.add(
                Finding(
                    "V13d", ERROR,
                    f"{len(undescribed)} in-scope file(s) are claimed by a module `covers` "
                    f"glob but have no function-level node describing them:"
                    f"\n        {shown}{more}",
                    hint="A `covers` glob accounts for a file; it does not describe it. "
                         "Add function/struct nodes in the module's subchart.",
                )
            )


def _covers_base(node: Node) -> str | None:
    """Longest common directory prefix of a node's `covers` globs.

    Derived from the globs rather than from the anchor file's parent directory:
    a module's principal file often sits in a subdirectory (src/dynamics has no
    top-level .jl at all), so inferring the root from the anchor would reject
    perfectly ordinary layouts.
    """
    bases = [_glob_base(p).split("/") for p in node.covers if _glob_base(p)]
    if not bases:
        return None
    common = bases[0]
    for parts in bases[1:]:
        keep = 0
        for a, b in zip(common, parts):
            if a != b:
                break
            keep += 1
        common = common[:keep]
        if not common:
            return None
    return "/".join(common) or None


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


# ---------------------------------------------------------------- V18

def _v18_workflows(ws: Workspace, by_id: dict[str, Node], report: Report) -> None:
    """Workflow charts must be seeded, and their seeds must be real nodes (D12).

    Membership is regenerated from seeds on every compile, so it cannot drift.
    What *can* go wrong is the input: a workflow with no seeds describes nothing,
    and a seed naming a node that does not exist silently shrinks the view.
    """
    for chart in ws.charts:
        if not chart.is_workflow:
            continue
        where = _rel(ws, chart.path)

        if not chart.seeds:
            report.add(
                Finding(
                    "V18", ERROR,
                    f"workflow {chart.chart_id!r} declares no seeds",
                    path=where,
                    hint="A workflow view is defined by its entry points. Add "
                         "`seeds`, each naming a node and why it belongs.",
                )
            )
            continue

        for raw in chart.seeds:
            nid = raw["node"] if isinstance(raw, dict) else raw
            if nid not in by_id:
                report.add(
                    Finding(
                        "V18", ERROR,
                        f"workflow {chart.chart_id!r} seeds unknown node {nid!r}",
                        path=where,
                        hint="Seeds must name nodes that already exist. Map the "
                             "symbol first, then seed the workflow with it.",
                    )
                )

        if not chart.member_nodes and not chart.local_nodes:
            report.add(
                Finding(
                    "V18", ERROR,
                    f"workflow {chart.chart_id!r} resolves to no nodes",
                    path=where,
                    hint="The seeds reach nothing. Check the traversal direction "
                         "and depth, or whether the call edges have been traced.",
                )
            )


# ---------------------------------------------------------------- V19

def _v19_no_duplicate_symbols(ws: Workspace, report: Report) -> None:
    """One symbol, one node — anywhere in the map (D12).

    A workflow view must *borrow* the dynamics nodes it spans, not build a
    shallow second model of dynamics inside itself. Two nodes describing the same
    (file, symbol) means the map disagrees with itself about what that symbol is.
    """
    owner: dict[tuple[str, str], tuple[str, str]] = {}
    for chart in ws.charts:
        for node in chart.all_nodes():
            src = node.source
            if not (src.file and src.symbol) or node.is_covering:
                continue
            key = (src.file, src.symbol)
            prior = owner.get(key)
            if prior is not None:
                report.add(
                    Finding(
                        "V19", ERROR,
                        f"{src.file}:{src.symbol} is defined by two nodes — "
                        f"{prior[0]!r} in {prior[1]!r} and {node.id!r} in "
                        f"{chart.chart_id!r}",
                        path=_rel(ws, chart.path),
                        hint="Reference the existing node via member_nodes instead "
                             "of creating a second one for the same symbol.",
                    )
                )
            else:
                owner[key] = (node.id, chart.chart_id)


# ---------------------------------------------------------------- V20

def _v20_sheet_size(ws: Workspace, resolved: dict[str, Any], report: Report) -> None:
    """Readability gate (D13): no sheet may render more nodes than the limit.

    Compile clusters oversized sheets automatically, so a finding here means
    clustering could not partition the sheet any further — typically one file
    whose symbols share a single name prefix. The fix is a hand-authored split
    or a smaller region, never a bigger limit.
    """
    limit = ws.config.max_nodes_per_sheet
    for chart_id in sorted(resolved):
        graph = resolved[chart_id]
        n = len(graph.nodes)
        if n > limit:
            report.add(
                Finding(
                    "V20", ERROR,
                    f"chart {chart_id!r} renders {n} nodes; the readability limit is {limit}",
                    hint="D13: sheets must be readable at fit-to-window. Split this block "
                         "by hand (a subchart with explicit member_nodes) or lower the "
                         "granularity of what it covers.",
                )
            )


# ---------------------------------------------------------------- V21

#: Master node kinds that are already at the finest granularity and therefore
#: need nothing to open into.
_LEAF_KINDS: frozenset[str] = frozenset({"function", "struct"})

#: Below this many master edges the hub test is meaningless.
_HUB_MIN_EDGES = 8


def _v21_operational_master(ws: Workspace, by_id: dict[str, Node], report: Report) -> None:
    """The master is the operational flow, not the package tree (D14).

    The first SpaceAGORA master passed every other rule and told a reader
    nothing: thirteen `include` arrows into a root module, no inputs, no
    outputs, and a root you could not click. Three properties rule that shape
    out, and each is mechanical:

    * V21a — data visibly enters and leaves: at least one `external` node with
      only outgoing master edges (a source) and one with only incoming (a sink).
    * V21b — every macro block is clickable: a non-leaf master node must `opens`
      an existing chart, or be expanded by one.
    * V21c — no hub: no master node touches more than `master_hub_fraction` of
      the master's edges. A package tree always fails this; a pipeline never
      does.
    """
    if not ws.config.require_operational_master:
        return
    master = ws.master
    if master is None:
        return
    nodes = list(master.nodes)
    edges = list(master.edges)
    if not nodes:
        return

    out_deg: dict[str, int] = {n.id: 0 for n in nodes}
    in_deg: dict[str, int] = {n.id: 0 for n in nodes}
    for e in edges:
        if e.from_.node in out_deg:
            out_deg[e.from_.node] += 1
        if e.to.node in in_deg:
            in_deg[e.to.node] += 1

    sources = [n for n in nodes if n.kind == "external" and out_deg[n.id] > 0 and in_deg[n.id] == 0]
    sinks = [n for n in nodes if n.kind == "external" and in_deg[n.id] > 0 and out_deg[n.id] == 0]
    if not sources or not sinks:
        report.add(
            Finding(
                "V21", ERROR,
                f"master has {len(sources)} external source(s) and {len(sinks)} external sink(s); "
                "it needs at least one of each",
                hint="D14: the master is the operational flow. Add `kind: external` nodes for "
                     "what the program reads (config, kernels, data files) and for every "
                     "artefact it writes (results, checkpoints, reports), and wire them in.",
            )
        )

    chart_ids = {c.chart_id for c in ws.charts}
    expanded = {n.expands for n in ws.all_nodes() if n.expands}
    for n in nodes:
        if n.kind in _LEAF_KINDS or n.kind == "external":
            continue
        if n.opens:
            if n.opens not in chart_ids:
                report.add(
                    Finding(
                        "V21", ERROR,
                        f"master node {n.id!r} opens chart {n.opens!r}, which does not exist",
                        hint="Point `opens` at a real chart id (see `vulcan status` for the list).",
                    )
                )
            continue
        if n.id in expanded:
            continue
        report.add(
            Finding(
                "V21", ERROR,
                f"master block {n.id!r} cannot be clicked through: it neither `opens` a chart "
                "nor is expanded by one",
                hint="D14: every macro block on the master must drill into a sheet. Set "
                     "`opens: <chart_id>` on the node.",
            )
        )

    if len(edges) >= _HUB_MIN_EDGES:
        limit = ws.config.master_hub_fraction
        for n in nodes:
            touched = in_deg[n.id] + out_deg[n.id]
            frac = touched / len(edges)
            if frac > limit:
                report.add(
                    Finding(
                        "V21", ERROR,
                        f"master node {n.id!r} is a hub: it touches {touched} of {len(edges)} "
                        f"edges ({frac:.0%} > {limit:.0%})",
                        hint="D14: a master where everything points at one node is a package "
                             "tree, not a flow. Replace containment edges with the dataflow "
                             "between phases, and move the package structure to its own sheet.",
                    )
                )
