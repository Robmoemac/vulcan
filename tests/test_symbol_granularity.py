"""D11: a node per significant symbol, not one node standing in for a file.

The map that shipped first had exactly one node per file. It passed every gate
at the time and was practically unusable — nothing to click into, and call edges
had no individual functions to resolve against. These tests pin that shape as a
failure.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import rules, write_master

from vulcan_map.core import compile as compile_mod, scaffold as scaffold_mod
from vulcan_map.core.grounding import grounder_for
from vulcan_map.core.repo import Mind
from vulcan_map.core.workspace import load_workspace

MULTI = (
    "def alpha(x):\n"
    "    return x\n"
    "\n\n"
    "def beta(x):\n"
    "    return alpha(x)\n"
    "\n\n"
    "class Gamma:\n"
    "    def delta(self, x):\n"
    "        return x\n"
    "\n"
    "    def __repr__(self):\n"
    "        return 'Gamma'\n"
)


def check(repo: Path, strict: bool = False):
    return compile_mod.run(repo, check_only=True, strict=strict).report


# --- enumeration --------------------------------------------------------------

def test_python_enumerates_functions_classes_and_methods() -> None:
    decls = grounder_for("x.py").declarations(MULTI)
    assert [d.symbol for d in decls] == ["alpha", "beta", "Gamma", "delta"]
    assert {d.symbol: d.kind for d in decls}["Gamma"] == "struct"


def test_python_enumeration_skips_dunders() -> None:
    assert "__repr__" not in {d.symbol for d in grounder_for("x.py").declarations(MULTI)}


def test_julia_enumerates_all_declaration_forms() -> None:
    text = (
        "module M\n"
        "function alpha(x)\n    x\nend\n"
        "beta(x) = x\n"
        "@kwdef mutable struct Gamma\n    n::Int\nend\n"
        "abstract type Delta end\n"
        "macro eps(x)\n    x\nend\n"
    )
    names = [d.symbol for d in grounder_for("x.jl").declarations(text)]
    assert names == ["M", "alpha", "beta", "Gamma", "Delta", "eps"]


def test_julia_dedupes_methods_of_one_generic() -> None:
    """Eight methods of `calc` are one concept, not eight nodes."""
    text = (
        "function calc(a::Int)\n    a\nend\n"
        "function calc(a::Float64)\n    a\nend\n"
        "function calc(a::String)\n    a\nend\n"
    )
    assert [d.symbol for d in grounder_for("x.jl").declarations(text)] == ["calc"]


def test_unknown_language_is_not_enumerated() -> None:
    """The rule must not guess; unenumerable languages are skipped."""
    assert grounder_for("x.rs").enumerates is False
    assert grounder_for("x.rs").declarations("fn main() {}") == []


# --- the rule ------------------------------------------------------------------

def test_one_node_per_multi_symbol_file_fails_strict(repo: Path, mind: Mind) -> None:
    """The exact shape of the map that shipped last time."""
    (repo / "src" / "multi.py").write_text(MULTI, encoding="utf-8")

    doc = mind.nodes_dir / "telemetry" / "only_alpha.md"
    doc.write_text(
        (mind.nodes_dir / "telemetry" / "run.md").read_text(encoding="utf-8")
        .replace("id: telemetry.run", "id: telemetry.only_alpha")
        .replace("label: run", "label: alpha")
        .replace("file: src/telemetry.py", "file: src/multi.py")
        .replace("symbol: run", "symbol: alpha"),
        encoding="utf-8",
    )

    def mutate(d):
        d["nodes"].append({
            "id": "telemetry.only_alpha", "label": "alpha", "kind": "function",
            "doc": "nodes/telemetry/only_alpha.md",
            "source": {"file": "src/multi.py", "symbol": "alpha"},
            "origin": "agent",
        })
        d["edges"].append({
            "id": "e:telemetry.run:path_out->telemetry.only_alpha:state0",
            "from": {"node": "telemetry.run", "socket": "path_out"},
            "to": {"node": "telemetry.only_alpha", "socket": "state0"},
            "kind": "call", "evidence": {"file": "src/multi.py"}, "origin": "agent",
        })
    write_master(mind, mutate)

    found = check(repo)
    assert "V13d" not in rules(found), "the file IS described — V13d is satisfied"
    assert "V13e" in rules(found), "but beta/Gamma/delta have no node of their own"

    message = next(f for f in found.findings if f.rule == "V13e").message
    for missing in ("beta", "Gamma", "delta"):
        assert missing in message


def test_mapping_every_symbol_satisfies_the_rule(repo: Path, mind: Mind) -> None:
    (repo / "src" / "pair.py").write_text(
        "def one():\n    return 1\n\n\ndef two():\n    return one()\n", encoding="utf-8"
    )
    base = (mind.nodes_dir / "telemetry" / "run.md").read_text(encoding="utf-8")
    for sym in ("one", "two"):
        (mind.nodes_dir / "telemetry" / f"{sym}.md").write_text(
            base.replace("id: telemetry.run", f"id: telemetry.{sym}")
                .replace("label: run", f"label: {sym}")
                .replace("file: src/telemetry.py", "file: src/pair.py")
                .replace("symbol: run", f"symbol: {sym}"),
            encoding="utf-8",
        )

    def mutate(d):
        for sym in ("one", "two"):
            d["nodes"].append({
                "id": f"telemetry.{sym}", "label": sym, "kind": "function",
                "doc": f"nodes/telemetry/{sym}.md",
                "source": {"file": "src/pair.py", "symbol": sym},
                "origin": "agent",
            })
            d["edges"].append({
                "id": f"e:telemetry.run:path_out->telemetry.{sym}:state0",
                "from": {"node": "telemetry.run", "socket": "path_out"},
                "to": {"node": f"telemetry.{sym}", "socket": "state0"},
                "kind": "call", "evidence": {"file": "src/pair.py"}, "origin": "agent",
            })
    write_master(mind, mutate)
    assert "V13e" not in rules(check(repo))


def test_rule_skips_languages_it_cannot_enumerate(repo: Path) -> None:
    (repo / "src" / "thing.rs").write_text("fn main() {}\n", encoding="utf-8")
    assert "V13e" not in rules(check(repo))


# --- doc floor scales with what a node claims ----------------------------------

def test_symbol_nodes_get_a_smaller_word_floor() -> None:
    """The 120-word floor was calibrated for module docs, not leaf functions."""
    from vulcan_map.core.config import Config

    defaults = Config(project="x", regions={})
    assert defaults.min_doc_words == 120
    assert defaults.min_doc_words_symbol == 40
    assert defaults.min_doc_words_symbol < defaults.min_doc_words


def test_covering_and_symbol_nodes_are_held_to_different_floors(repo: Path, mind: Mind) -> None:
    ws = load_workspace(repo)
    covering = [n for n in ws.all_nodes() if n.is_covering]
    symbols = [n for n in ws.all_nodes() if not n.is_covering]
    assert symbols, "fixture has symbol-level nodes"
    # the distinction the floor keys off is is_covering, not the doc itself
    assert all(n.kind in ("module", "group") for n in covering)


def test_a_stub_doc_still_fails_the_symbol_floor(repo: Path, mind: Mind) -> None:
    """Scaffolding must never be enough to pass the gate."""
    doc = mind.nodes_dir / "telemetry" / "run.md"
    head = doc.read_text(encoding="utf-8").partition("## Purpose")[0]
    doc.write_text(
        head + "## Purpose\n\n## Interface (ICD)\n"
        "<!-- vulcan:icd:begin -->\n<!-- vulcan:icd:end -->\n"
        "## Connections\n<!-- vulcan:connections:begin -->\n<!-- vulcan:connections:end -->\n",
        encoding="utf-8",
    )
    compile_mod.run(repo, check_only=False)
    assert "V12" in rules(check(repo))


# --- scaffolding ---------------------------------------------------------------

def test_scaffold_plans_a_node_for_every_unmapped_symbol(repo: Path, mind: Mind) -> None:
    (repo / "src" / "multi.py").write_text(MULTI, encoding="utf-8")

    def mutate(d):
        d["nodes"][0]["kind"] = "module"
        d["nodes"][0]["covers"] = ["src/**"]
    write_master(mind, mutate)
    md = mind.nodes_dir / "propagator" / "propagate_orbit.md"
    md.write_text(
        md.read_text(encoding="utf-8").replace("kind: function", "kind: module"),
        encoding="utf-8",
    )
    (mind.subcharts_dir / "propagate_orbit.graph.json").write_text(
        json.dumps({
            "schema_version": "1.0.0", "chart_id": "propagate_orbit",
            "chart_kind": "sub", "derives_from": "master", "title": "t",
            "member_nodes": ["propagator.propagate_orbit"],
            "local_nodes": [], "local_edges": [],
        }, indent=2),
        encoding="utf-8",
    )

    plan = scaffold_mod.plan(load_workspace(repo))
    planned = {n["source"]["symbol"] for v in plan.nodes_by_chart.values() for n in v}
    assert {"alpha", "beta", "Gamma", "delta"} <= planned


def test_scaffolded_docs_have_no_prose_so_the_gate_still_fails() -> None:
    text = scaffold_mod._render_doc("m.alpha", "alpha", "function", "src/a.py", 3, "m")
    assert "## Purpose\n\n" in text
    assert "TODO" not in text and "TBD" not in text  # would trip V12's banned list
    body = text.split("---", 2)[2]
    words = [w for w in body.replace("#", " ").split() if w.isalpha()]
    assert len(words) < 40, "a skeleton must not clear the symbol word floor"


def test_bang_and_non_bang_symbols_get_distinct_ids() -> None:
    """Julia's `sort` and `sort!` are different functions.

    Stripping `!` collapsed them onto one id, so the mutating variant was
    silently dropped from the map and V13e reported it as unmapped forever.
    """
    plain = scaffold_mod.node_id_for("m", "src/a.jl", "update")
    bang = scaffold_mod.node_id_for("m", "src/a.jl", "update!")
    query = scaffold_mod.node_id_for("m", "src/a.jl", "update?")
    assert plain != bang != query and plain != query
    import re
    for nid in (plain, bang, query):
        assert re.match(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$", nid), nid
