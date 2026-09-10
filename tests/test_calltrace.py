"""Derived call edges: real invocations, read out of the source."""

from __future__ import annotations

from pathlib import Path

from vulcan_map.core.calltrace import (
    CALLEES_OUT, CALLERS_IN, classify_feedback, derive_edges, find_call_sites,
)
from vulcan_map.core.model import Node, Source


def node(nid: str, file: str, symbol: str, lines=(1, 200)) -> Node:
    return Node(
        id=nid, label=symbol, kind="function", doc=f"nodes/{nid}.md",
        source=Source(file=file, symbol=symbol, lines=lines),
    )


def test_finds_a_real_call(tmp_path: Path) -> None:
    (tmp_path / "a.jl").write_text(
        "function outer(x)\n    inner(x)\nend\n", encoding="utf-8"
    )
    (tmp_path / "b.jl").write_text("function inner(x)\n    x\nend\n", encoding="utf-8")
    nodes = [node("m.outer", "a.jl", "outer"), node("m.inner", "b.jl", "inner")]

    sites = find_call_sites(nodes, tmp_path)
    assert [(s.caller, s.callee, s.line) for s in sites] == [("m.outer", "m.inner", 2)]


def test_edge_cites_the_call_site_as_evidence(tmp_path: Path) -> None:
    (tmp_path / "a.jl").write_text(
        "function outer(x)\n\n    inner(x)\nend\n", encoding="utf-8"
    )
    (tmp_path / "b.jl").write_text("function inner(x)\n    x\nend\n", encoding="utf-8")
    edges = derive_edges(
        [node("m.outer", "a.jl", "outer"), node("m.inner", "b.jl", "inner")], tmp_path
    )
    assert len(edges) == 1
    e = edges[0]
    assert e.from_.socket == CALLEES_OUT and e.to.socket == CALLERS_IN
    assert e.evidence.file == "a.jl" and e.evidence.lines == (3, 3)
    assert e.kind == "call"


def test_a_mention_is_not_a_call(tmp_path: Path) -> None:
    """Requiring `symbol(` keeps comments and exports from inventing edges."""
    (tmp_path / "a.jl").write_text(
        "export inner\n# inner is documented here\nfunction outer(x)\n"
        "    # see inner for details\n    x\nend\n",
        encoding="utf-8",
    )
    (tmp_path / "b.jl").write_text("function inner(x)\n    x\nend\n", encoding="utf-8")
    assert find_call_sites(
        [node("m.outer", "a.jl", "outer"), node("m.inner", "b.jl", "inner")], tmp_path
    ) == []


def test_calls_outside_the_declaration_span_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "a.jl").write_text(
        "function outer(x)\n    x\nend\n\nfunction elsewhere()\n    inner(1)\nend\n",
        encoding="utf-8",
    )
    (tmp_path / "b.jl").write_text("function inner(x)\n    x\nend\n", encoding="utf-8")
    nodes = [node("m.outer", "a.jl", "outer", lines=(1, 3)), node("m.inner", "b.jl", "inner")]
    assert find_call_sites(nodes, tmp_path) == []


def test_self_calls_are_not_edges(tmp_path: Path) -> None:
    (tmp_path / "a.jl").write_text(
        "function fact(n)\n    n * fact(n - 1)\nend\n", encoding="utf-8"
    )
    assert derive_edges([node("m.fact", "a.jl", "fact")], tmp_path) == []


def test_cycles_become_feedback_edges_not_dropped(tmp_path: Path) -> None:
    """D5: real recursion is drawn dashed, never silently discarded."""
    (tmp_path / "a.jl").write_text("function ping(x)\n    pong(x)\nend\n", encoding="utf-8")
    (tmp_path / "b.jl").write_text("function pong(x)\n    ping(x)\nend\n", encoding="utf-8")
    edges = derive_edges(
        [node("m.ping", "a.jl", "ping"), node("m.pong", "b.jl", "pong")], tmp_path
    )
    assert len(edges) == 2
    assert sum(1 for e in edges if e.is_feedback) == 1


def test_feedback_classification_is_deterministic() -> None:
    pairs = [("a", "b"), ("b", "c"), ("c", "a")]
    assert classify_feedback(pairs) == classify_feedback(list(reversed(pairs)))


def test_derive_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "a.jl").write_text(
        "function outer(x)\n    inner(x)\n    other(x)\nend\n", encoding="utf-8"
    )
    (tmp_path / "b.jl").write_text(
        "function inner(x)\n    x\nend\nfunction other(x)\n    x\nend\n", encoding="utf-8"
    )
    nodes = [
        node("m.outer", "a.jl", "outer"),
        node("m.inner", "b.jl", "inner"),
        node("m.other", "b.jl", "other"),
    ]
    first = [e.id for e in derive_edges(nodes, tmp_path)]
    assert first == [e.id for e in derive_edges(nodes, tmp_path)]
    assert first == sorted(first)
