"""D13: readability by nesting.

A sheet that renders hundreds of nodes is a wall, not a map. Compile must
partition oversized sheets into group nodes with nested sheets, the parent
must render the blocks with edges lifted, and V20 must fail any sheet that
still exceeds the limit. Group nodes carry a doc like any other node.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from conftest import CONFIG, rules

from vulcan_map.core import compile as compile_mod
from vulcan_map.core.cluster import group_id, plan_clusters
from vulcan_map.core.model import Node, Source
from vulcan_map.core.repo import Mind

LIMIT = 6

DOC = """---
id: {nid}
label: {sym}
kind: function
source:
  file: {file}
  symbol: {sym}
inputs:
- id: callers
  type: call
outputs:
- id: callees
  type: call
expands: module.big
tags: [big]
origin: agent
---

# {sym}

## Purpose
Fixture symbol with enough prose to clear the configured minimum word count
for a node document and exercise the clustering step end to end without
tripping any banned phrase in the lint configuration at all.

## Interface (ICD)
<!-- vulcan:icd:begin -->
<!-- vulcan:icd:end -->

## Connections
<!-- vulcan:connections:begin -->
<!-- vulcan:connections:end -->
"""

MODULE_DOC = """---
id: module.big
label: big
kind: module
covers: ["src/big/**"]
origin: agent
---

# big

## Purpose
The fixture module that owns every generated symbol so the coverage rules are
satisfied while the clustering step is exercised on a sheet far larger than
the configured readability limit for this test repository here.

## Interface (ICD)
<!-- vulcan:icd:begin -->
<!-- vulcan:icd:end -->

## Connections
<!-- vulcan:connections:begin -->
<!-- vulcan:connections:end -->
"""


def _sym(file: str, sym: str) -> dict:
    stem = Path(file).stem
    return {
        "id": f"big.{stem}_{sym}", "label": sym, "kind": "function",
        "doc": f"nodes/big/{stem}_{sym}.md",
        "source": {"file": file, "symbol": sym},
        "sockets": {"inputs": [{"id": "callers", "type": "call"}],
                    "outputs": [{"id": "callees", "type": "call"}]},
        "expands": "module.big", "tags": ["big"], "origin": "agent",
    }


def _edge(a: str, b: str, file: str) -> dict:
    return {
        "id": f"e:{a}:callees->{b}:callers",
        "from": {"node": a, "socket": "callees"}, "to": {"node": b, "socket": "callers"},
        "kind": "call", "evidence": {"file": file}, "origin": "agent",
    }


def _big_repo(tmp_path: Path, layout: dict[str, list[str]], edges: list[tuple[str, str]]) -> Path:
    """A repo with one module whose subchart has one symbol node per (file, sym)."""
    root = tmp_path / "big"
    mind = Mind(root)
    for d in (mind.graph_dir, mind.subcharts_dir, mind.nodes_dir / "big", mind.build_dir):
        d.mkdir(parents=True, exist_ok=True)
    cfg = CONFIG.replace("min_doc_words: 20", "min_doc_words: 20\n  min_doc_words_symbol: 20")
    cfg = cfg.replace("require_subchart_per_module: true",
                      f"require_subchart_per_module: true\n  max_nodes_per_sheet: {LIMIT}")
    mind.config_path.write_text(cfg, encoding="utf-8")

    nodes, docs = [], {}
    for file, syms in layout.items():
        src = root / file
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("".join(f"def {s}():\n    return 1\n\n\n" for s in syms), encoding="utf-8")
        for s in syms:
            n = _sym(file, s)
            nodes.append(n)
            docs[n["doc"]] = DOC.format(nid=n["id"], sym=s, file=file)
    for rel, text in docs.items():
        (mind.root / rel).write_text(text, encoding="utf-8")
    (mind.nodes_dir / "big.md").write_text(MODULE_DOC, encoding="utf-8")

    by_stem = {Path(f).stem: f for f in layout}
    local_edges = [
        _edge(a, b, by_stem[a.split(".", 1)[1].rsplit("_", 1)[0]]) for a, b in edges
    ]
    master = {
        "schema_version": "1.0.0", "chart_id": "master", "chart_kind": "master",
        "title": "big master", "region": "all",
        "nodes": [{"id": "module.big", "label": "big", "kind": "module", "doc": "nodes/big.md",
                   "covers": ["src/big/**"], "origin": "agent"}],
        "edges": [],
    }
    mind.master_path.write_text(json.dumps(master, indent=2), encoding="utf-8")
    sub = {
        "schema_version": "1.0.0", "chart_id": "big", "chart_kind": "sub",
        "title": "big — internals", "derives_from": "master",
        "member_nodes": ["module.big"], "local_nodes": nodes, "local_edges": local_edges,
    }
    (mind.subcharts_dir / "big.graph.json").write_text(json.dumps(sub, indent=2), encoding="utf-8")
    return root


LAYOUT = {
    "src/big/alpha/one.py": ["a1", "a2", "a3", "a4"],
    "src/big/alpha/two.py": ["b1", "b2", "b3"],
    "src/big/beta/three.py": ["c1", "c2", "c3", "c4", "c5"],
    "src/big/beta/four.py": ["d1", "d2", "d3"],
    "src/big/tiny.py": ["t1"],
}
EDGES = [("big.one_a1", "big.three_c1"), ("big.one_a2", "big.three_c2"),
         ("big.two_b1", "big.four_d1"), ("big.one_a1", "big.one_a2")]


# --- planning ------------------------------------------------------------------

def _nodes(layout: dict[str, list[str]]) -> list[Node]:
    return [Node(id=f"x.{Path(f).stem}_{s}", label=s, kind="function", doc="d",
                 source=Source(file=f, symbol=s)) for f, syms in layout.items() for s in syms]


def test_small_sheets_are_left_alone() -> None:
    assert plan_clusters(_nodes({"src/a.py": ["f", "g"]}), threshold=6, min_group=3) is None


def test_clusters_by_directory_then_file() -> None:
    plans = plan_clusters(_nodes(LAYOUT), threshold=6, min_group=3)
    assert plans is not None
    keys = [p.key for p in plans]
    # alpha/ and beta/ are directory blocks; tiny.py alone is below min_group
    # and stays its own block because there is nothing to merge it with.
    assert "src/big/alpha" in keys and "src/big/beta" in keys
    assert sum(len(p.members) for p in plans) == 16


def test_single_file_splits_by_name_prefix() -> None:
    layout = {"src/f.py": [f"_init_{i}" for i in range(5)] + [f"_rhs_{i}" for i in range(5)]}
    plans = plan_clusters(_nodes(layout), threshold=6, min_group=3)
    assert plans is not None and {p.key for p in plans} == {"src/f.py#_init", "src/f.py#_rhs"}


def test_file_and_directory_with_same_stem_get_distinct_ids() -> None:
    """Julia convention: `x.jl` beside `x/`. Collapsing them lost a whole block."""
    assert group_id("src/a/x.jl") != group_id("src/a/x")


# --- compile behaviour -----------------------------------------------------------

def test_oversized_sheet_is_nested_and_rendered_readable(tmp_path: Path) -> None:
    root = _big_repo(tmp_path, LAYOUT, EDGES)
    res = compile_mod.run(root, check_only=False)
    big = res.resolved["big"]
    assert len(big.nodes) <= LIMIT
    groups = [n for n in big.nodes if n.kind == "group"]
    assert {g.label for g in groups} >= {"big/alpha/", "big/beta/"}
    # members are hidden behind their block
    assert not any(n.id == "big.one_a1" for n in big.nodes)
    # nested sheets exist on disk and are themselves readable
    nested = sorted(p.name for p in Mind(root).subcharts_dir.glob("big-*.graph.json"))
    assert nested, "nested charts must be written"
    for cid, graph in res.resolved.items():
        assert len(graph.nodes) <= LIMIT, cid
    assert "V20" not in rules(res.report)


def test_edges_between_blocks_are_lifted_and_counted(tmp_path: Path) -> None:
    root = _big_repo(tmp_path, LAYOUT, EDGES)
    res = compile_mod.run(root, check_only=False)
    big = res.resolved["big"]
    lifted = [e for e in big.edges if e.from_.node.startswith("grp.") and e.to.node.startswith("grp.")]
    assert len(lifted) == 1  # alpha -> beta, three underlying calls collapsed
    assert lifted[0].label == "3 edges"
    # the intra-block call a1 -> a2 lives on the nested sheet, not the parent
    assert not any(e.from_.node == "big.one_a1" for e in big.edges)


def test_group_nodes_need_a_doc_and_the_gate_fails_until_written(tmp_path: Path) -> None:
    root = _big_repo(tmp_path, LAYOUT, EDGES)
    res = compile_mod.run(root, check_only=False)
    v12 = [f for f in res.report.findings if f.rule == "V12"]
    assert v12, "scaffolded group docs must not clear the prose floor"
    docs = sorted(p.name for p in (Mind(root).nodes_dir / "big").glob("src_big_*.md"))
    assert docs, "a doc skeleton is written per group node"
    text = (Mind(root).nodes_dir / "big" / docs[0]).read_text(encoding="utf-8")
    assert "kind: group" in text and "<!-- vulcan:icd:begin -->" in text


def test_compile_is_idempotent_after_clustering(tmp_path: Path) -> None:
    root = _big_repo(tmp_path, LAYOUT, EDGES)
    compile_mod.run(root, check_only=False)
    mind = Mind(root)
    snap = {p: p.read_bytes() for p in mind.subcharts_dir.glob("*.json")}
    snap.update({p: p.read_bytes() for p in mind.nodes_dir.rglob("*.md")})
    compile_mod.run(root, check_only=False)
    for p, before in snap.items():
        assert p.read_bytes() == before, p


def test_check_sees_the_same_picture_without_writing(tmp_path: Path) -> None:
    root = _big_repo(tmp_path, LAYOUT, EDGES)
    res = compile_mod.run(root, check_only=True)
    assert len(res.resolved["big"].nodes) <= LIMIT
    assert not list(Mind(root).subcharts_dir.glob("big-*.graph.json"))
    # ...but it names what compile would have to create
    assert "V8" in rules(res.report)


def test_v20_fires_when_nothing_can_be_split(tmp_path: Path) -> None:
    """One file, one name prefix: clustering has no handle, so the gate must say so."""
    layout = {"src/big/flat.py": [f"same_{i}" for i in range(LIMIT + 2)]}
    root = _big_repo(tmp_path, layout, [])
    res = compile_mod.run(root, check_only=True)
    assert "V20" in rules(res.report)


def test_group_docs_are_held_to_the_symbol_floor(tmp_path: Path) -> None:
    root = _big_repo(tmp_path, LAYOUT, EDGES)
    compile_mod.run(root, check_only=False)
    mind = Mind(root)
    for p in (mind.nodes_dir / "big").glob("src_big_*.md"):
        head, _, body = p.read_text(encoding="utf-8").partition("## Purpose")
        purpose = ("\nThis block groups the fixture symbols of one directory so the sheet reads "
                   "left to right as a handful of macro blocks instead of a wall of leaves.\n")
        p.write_text(head + "## Purpose" + purpose + body, encoding="utf-8")
    res = compile_mod.run(root, check_only=False)
    assert "V12" not in rules(res.report)
    assert "V8" not in rules(res.report) and "V20" not in rules(res.report)


def test_drill_in_is_resolved_per_parent_chart(tmp_path: Path) -> None:
    root = _big_repo(tmp_path, LAYOUT, EDGES)
    compile_mod.run(root, check_only=False)
    from vulcan_map.ui.session import Session

    s = Session(repo_root=root)
    s.reload()
    alpha = group_id("src/big/alpha")
    target = s.expansion_for(alpha, "big")
    assert target is not None and s.chart_meta[target]["group"] == alpha
    assert s.chart_meta[target]["derives_from"] == "big"
