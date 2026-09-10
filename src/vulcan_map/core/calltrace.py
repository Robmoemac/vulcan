"""Derive real call edges between mapped symbols by reading the source.

A map whose only edges run from a module node to each of its members shows
containment, not behaviour — every chart renders as a star and tells you nothing
about how the code actually flows. This finds the edges that are really there:
for each mapped symbol, scan its own declaration span for call sites of other
mapped symbols.

Mechanical and grounded by construction: every edge produced cites the file and
line where the call literally appears, so it satisfies V7 without anyone having
to assert anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .model import Edge, Endpoint, Evidence, Node

#: Socket pair used for derived call edges.
CALLERS_IN = "callers"
CALLEES_OUT = "callees"

#: Lines that mention a symbol without calling it.
_NON_CALL = re.compile(r"^[ \t]*(?:export|using|import|include|#)")


@dataclass(frozen=True, slots=True)
class CallSite:
    caller: str          # node id
    callee: str          # node id
    file: str            # where the call appears (the caller's file)
    line: int            # 1-based


def _span(text: str, node: Node) -> tuple[int, int]:
    """The caller's own line range, defaulting to the whole file."""
    total = text.count("\n") + 1
    if node.source.lines:
        lo, hi = node.source.lines
        return max(1, lo), min(total, max(hi, lo))
    return 1, total


def _call_pattern(symbol: str) -> re.Pattern[str]:
    """`symbol(` — an actual invocation, not a mere mention.

    Requiring the open paren keeps short names like `run` or `main` from
    matching every comment and docstring that happens to contain the word.
    """
    return re.compile(rf"(?<![A-Za-z0-9_.]){re.escape(symbol)}\s*\(")


def find_call_sites(nodes: list[Node], repo_root: Path) -> list[CallSite]:
    """Every call from one mapped symbol to another, observed in source."""
    callable_nodes = [
        n for n in nodes
        if n.source.file and n.source.symbol and not n.is_covering
    ]
    by_symbol: dict[str, list[Node]] = {}
    for n in callable_nodes:
        by_symbol.setdefault(n.source.symbol, []).append(n)

    cache: dict[str, list[str]] = {}
    sites: list[CallSite] = []

    for caller in callable_nodes:
        path = repo_root / caller.source.file
        if not path.is_file():
            continue
        if caller.source.file not in cache:
            try:
                cache[caller.source.file] = path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
            except OSError:
                cache[caller.source.file] = []
        lines = cache[caller.source.file]
        if not lines:
            continue

        lo, hi = _span("\n".join(lines), caller)
        patterns = {
            sym: _call_pattern(sym)
            for sym in by_symbol
            if sym != caller.source.symbol
        }

        for offset, line in enumerate(lines[lo - 1 : hi], start=lo):
            if _NON_CALL.match(line):
                continue
            for sym, pattern in patterns.items():
                if not pattern.search(line):
                    continue
                for callee in by_symbol[sym]:
                    if callee.id == caller.id:
                        continue
                    sites.append(
                        CallSite(caller.id, callee.id, caller.source.file, offset)
                    )
    return sites


def _first_sites(sites: list[CallSite]) -> dict[tuple[str, str], CallSite]:
    """One edge per (caller, callee), citing the first observed call site."""
    out: dict[tuple[str, str], CallSite] = {}
    for s in sites:
        out.setdefault((s.caller, s.callee), s)
    return out


def classify_feedback(pairs: list[tuple[str, str]]) -> set[tuple[str, str]]:
    """Which pairs must be marked `feedback` to keep the graph acyclic.

    Real call graphs contain cycles (D5). A depth-first pass over the edges in a
    deterministic order marks the back-edges it meets; those are rendered dashed
    and exempted from the acyclicity check rather than dropped.
    """
    adjacency: dict[str, list[str]] = {}
    for a, b in pairs:
        adjacency.setdefault(a, []).append(b)
    for a in adjacency:
        adjacency[a].sort()

    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[str, int] = {}
    back: set[tuple[str, str]] = set()

    def visit(node: str) -> None:
        colour[node] = GREY
        for nxt in adjacency.get(node, ()):
            state = colour.get(nxt, WHITE)
            if state == GREY:
                back.add((node, nxt))
            elif state == WHITE:
                visit(nxt)
        colour[node] = BLACK

    for start in sorted({a for a, _ in pairs} | {b for _, b in pairs}):
        if colour.get(start, WHITE) == WHITE:
            visit(start)
    return back


def derive_edges(nodes: list[Node], repo_root: Path) -> list[Edge]:
    """Call edges between mapped symbols, deterministic and evidence-backed."""
    sites = _first_sites(find_call_sites(nodes, repo_root))
    pairs = sorted(sites)
    back = classify_feedback(pairs)
    labels = {n.id: (n.source.symbol or n.label) for n in nodes}

    edges: list[Edge] = []
    for (caller, callee) in pairs:
        site = sites[(caller, callee)]
        edges.append(
            Edge(
                from_=Endpoint(caller, CALLEES_OUT),
                to=Endpoint(callee, CALLERS_IN),
                kind="feedback" if (caller, callee) in back else "call",
                evidence=Evidence(file=site.file, lines=(site.line, site.line)),
                label=labels.get(callee),
                origin="agent",
            )
        )
    return edges
