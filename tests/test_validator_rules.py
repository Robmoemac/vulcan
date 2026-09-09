"""Every validator rule must actually fire. A rule that cannot fail is not a gate."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import rules, write_master

from vulcan_map.core import compile as compile_mod
from vulcan_map.core.repo import Mind


def check(repo: Path, strict: bool = False):
    return compile_mod.run(repo, check_only=True, strict=strict).report


def test_baseline_fixture_passes_strict(repo: Path) -> None:
    report = check(repo, strict=True)
    assert report.ok(strict=True), [f.format() for f in report.findings]


def test_v2_duplicate_node_id(repo: Path, mind: Mind) -> None:
    def mutate(d):
        dup = dict(d["nodes"][0])
        d["nodes"].append(dup)
    write_master(mind, mutate)
    # A duplicate inside one chart is caught by uniqueness of the id map; the
    # cross-chart case is covered by test_v2_subchart_may_not_redefine.
    report = check(repo)
    assert not report.ok()


def test_v3_edge_to_unknown_node(repo: Path, mind: Mind) -> None:
    def mutate(d):
        d["edges"][0]["to"]["node"] = "does.not.exist"
        d["edges"][0]["id"] = "e:x:y->does.not.exist:z"
    write_master(mind, mutate)
    assert "V3" in rules(check(repo))


def test_v4_edge_to_undeclared_socket(repo: Path, mind: Mind) -> None:
    def mutate(d):
        d["edges"][0]["to"]["socket"] = "no_such_socket"
    write_master(mind, mutate)
    assert "V4" in rules(check(repo))


def test_v5_cycle_is_rejected(repo: Path, mind: Mind) -> None:
    def mutate(d):
        d["edges"].append(
            {
                "id": "e:telemetry.write_telemetry:written_path->telemetry.run:path",
                "from": {"node": "telemetry.write_telemetry", "socket": "written_path"},
                "to": {"node": "telemetry.run", "socket": "path"},
                "kind": "dataflow",
                "evidence": {"file": "src/telemetry.py"},
                "origin": "agent",
            }
        )
    write_master(mind, mutate)
    assert "V5" in rules(check(repo))


def test_v5_feedback_edge_is_exempt(repo: Path, mind: Mind) -> None:
    """D5: recursion is mapped, not dropped — feedback edges bypass acyclicity."""
    def mutate(d):
        d["edges"].append(
            {
                "id": "e:telemetry.write_telemetry:written_path->telemetry.run:path",
                "from": {"node": "telemetry.write_telemetry", "socket": "written_path"},
                "to": {"node": "telemetry.run", "socket": "path"},
                "kind": "feedback",
                "evidence": {"file": "src/telemetry.py"},
                "origin": "agent",
            }
        )
    write_master(mind, mutate)
    assert "V5" not in rules(check(repo))


def test_v6_hallucinated_symbol_fails(repo: Path, mind: Mind) -> None:
    """The central anti-hallucination gate."""
    def mutate(d):
        d["nodes"][0]["source"]["symbol"] = "definitely_not_in_this_file"
    write_master(mind, mutate)
    findings = [f for f in check(repo).findings if f.rule == "V6"]
    assert findings
    assert "definitely_not_in_this_file" in findings[0].message


def test_v6_nonexistent_file_fails(repo: Path, mind: Mind) -> None:
    def mutate(d):
        d["nodes"][0]["source"]["file"] = "src/imaginary.py"
    write_master(mind, mutate)
    assert "V6" in rules(check(repo))


def test_v7_edge_evidence_must_exist(repo: Path, mind: Mind) -> None:
    def mutate(d):
        d["edges"][0]["evidence"]["file"] = "src/nowhere.py"
    write_master(mind, mutate)
    assert "V7" in rules(check(repo))


def test_v8_missing_doc(repo: Path, mind: Mind) -> None:
    (mind.nodes_dir / "telemetry" / "run.md").unlink()
    assert "V8" in rules(check(repo))


def test_v9_orphan_doc(repo: Path, mind: Mind) -> None:
    def mutate(d):
        d["nodes"] = [n for n in d["nodes"] if n["id"] != "telemetry.run"]
        d["edges"] = [
            e for e in d["edges"]
            if "telemetry.run" not in (e["from"]["node"], e["to"]["node"])
        ]
    write_master(mind, mutate)
    assert "V9" in rules(check(repo))


def test_v10_socket_only_in_json(repo: Path, mind: Mind) -> None:
    def mutate(d):
        d["nodes"][0]["sockets"] = {"outputs": [{"id": "ghost_socket"}]}
    write_master(mind, mutate)
    assert "V10" in rules(check(repo))


def test_v11_node_outside_region(repo: Path, mind: Mind) -> None:
    outside = mind.repo_root / "other"
    outside.mkdir()
    (outside / "stray.py").write_text("def stray():\n    return 1\n", encoding="utf-8")

    def mutate(d):
        d["nodes"][0]["source"] = {"file": "other/stray.py", "symbol": "stray"}
    write_master(mind, mutate)
    assert "V11" in rules(check(repo))


def test_v12_banned_phrase(repo: Path, mind: Mind) -> None:
    doc = mind.nodes_dir / "telemetry" / "run.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "## Purpose", "## Purpose\nThis is a helper function.\n"
        ),
        encoding="utf-8",
    )
    assert "V12" in rules(check(repo))


def test_v12_word_floor_ignores_generated_blocks(repo: Path, mind: Mind) -> None:
    """A stub cannot be padded past the floor by generated tables."""
    doc = mind.nodes_dir / "telemetry" / "run.md"
    text = doc.read_text(encoding="utf-8")
    head, _, _ = text.partition("## Purpose")
    doc.write_text(
        head + "## Purpose\nShort.\n\n"
        "## Interface (ICD)\n<!-- vulcan:icd:begin -->\n<!-- vulcan:icd:end -->\n"
        "## Connections\n<!-- vulcan:connections:begin -->\n<!-- vulcan:connections:end -->\n",
        encoding="utf-8",
    )
    compile_mod.run(mind.repo_root, check_only=False)
    assert "V12" in rules(check(mind.repo_root))


def test_v13_unmapped_file_fails(repo: Path) -> None:
    (repo / "src" / "unmapped.py").write_text("def lonely():\n    return 0\n", encoding="utf-8")
    findings = [f for f in check(repo).findings if f.rule == "V13"]
    assert findings
    assert "src/unmapped.py" in findings[0].message


def test_v13_covers_accounts_for_files(repo: Path, mind: Mind) -> None:
    """D3: module nodes account for files via `covers` instead of one node per file."""
    (repo / "src" / "extra.py").write_text("def extra():\n    return 0\n", encoding="utf-8")
    assert "V13" in rules(check(repo))

    def mutate(d):
        d["nodes"][0]["covers"] = ["src/extra.py"]
        d["nodes"][0]["kind"] = "module"
    write_master(mind, mutate)
    doc = mind.nodes_dir / "propagator" / "propagate_orbit.md"
    doc.write_text(doc.read_text(encoding="utf-8").replace("kind: function", "kind: module"), encoding="utf-8")
    assert "V13" not in rules(check(repo))


def test_v13a_covers_may_not_escape_module_root(repo: Path, mind: Mind) -> None:
    def mutate(d):
        d["nodes"][0]["kind"] = "module"
        d["nodes"][0]["covers"] = ["**"]
    write_master(mind, mutate)
    doc = mind.nodes_dir / "propagator" / "propagate_orbit.md"
    doc.write_text(doc.read_text(encoding="utf-8").replace("kind: function", "kind: module"), encoding="utf-8")
    assert "V13a" in rules(check(repo))


def test_v13a_allows_anchor_in_a_subdirectory(repo: Path, mind: Mind) -> None:
    """Regression: real modules often have no top-level file.

    src/dynamics/ in SpaceAGORA.jl contains only subdirectories, so its anchor
    necessarily sits deeper than the subtree it covers. Deriving the module root
    from the anchor's parent rejected that; it is derived from `covers` instead.
    """
    (repo / "src" / "sub").mkdir()
    (repo / "src" / "sub" / "deep.py").write_text("def deep():\n    return 1\n", encoding="utf-8")

    def mutate(d):
        d["nodes"][0]["kind"] = "module"
        d["nodes"][0]["covers"] = ["src/**"]
        d["nodes"][0]["source"] = {"file": "src/sub/deep.py", "symbol": "deep"}
    write_master(mind, mutate)
    doc = mind.nodes_dir / "propagator" / "propagate_orbit.md"
    text = doc.read_text(encoding="utf-8").replace("kind: function", "kind: module")
    text = text.replace("file: src/propagator.py", "file: src/sub/deep.py")
    text = text.replace("symbol: propagate_orbit", "symbol: deep")
    doc.write_text(text, encoding="utf-8")

    assert "V13a" not in rules(check(repo))


def test_v13a_rejects_anchor_outside_what_it_covers(repo: Path, mind: Mind) -> None:
    (repo / "other").mkdir()
    (repo / "other" / "stray.py").write_text("def stray():\n    return 1\n", encoding="utf-8")

    def mutate(d):
        d["nodes"][0]["kind"] = "module"
        d["nodes"][0]["covers"] = ["src/**"]
        d["nodes"][0]["source"] = {"file": "other/stray.py", "symbol": "stray"}
    write_master(mind, mutate)
    doc = mind.nodes_dir / "propagator" / "propagate_orbit.md"
    text = doc.read_text(encoding="utf-8").replace("kind: function", "kind: module")
    text = text.replace("file: src/propagator.py", "file: other/stray.py")
    text = text.replace("symbol: propagate_orbit", "symbol: stray")
    doc.write_text(text, encoding="utf-8")

    assert "V13a" in rules(check(repo))


def test_v13c_two_modules_may_not_claim_the_same_file(repo: Path, mind: Mind) -> None:
    def mutate(d):
        for node in d["nodes"][:2]:
            node["kind"] = "module"
            node["covers"] = ["src/**"]
    write_master(mind, mutate)
    for rel in ("propagator/propagate_orbit.md", "telemetry/write_telemetry.md"):
        doc = mind.nodes_dir / rel
        doc.write_text(
            doc.read_text(encoding="utf-8").replace("kind: function", "kind: module"),
            encoding="utf-8",
        )
    assert "V13c" in rules(check(repo))


def test_v13b_module_needs_expanding_subchart(repo: Path, mind: Mind) -> None:
    def mutate(d):
        d["nodes"][0]["kind"] = "module"
        d["nodes"][0]["covers"] = ["src/propagator.py"]
    write_master(mind, mutate)
    doc = mind.nodes_dir / "propagator" / "propagate_orbit.md"
    doc.write_text(doc.read_text(encoding="utf-8").replace("kind: function", "kind: module"), encoding="utf-8")
    assert "V13b" in rules(check(repo))


def test_v14_isolated_node_warns(repo: Path, mind: Mind) -> None:
    def mutate(d):
        d["edges"] = [
            e for e in d["edges"]
            if "telemetry.write_telemetry" not in (e["from"]["node"], e["to"]["node"])
        ]
    write_master(mind, mutate)
    compile_mod.run(repo, check_only=False)  # edit -> compile -> check, as an agent would
    report = check(repo)
    assert "V14" in rules(report)
    assert report.ok()          # warning only
    assert not report.ok(True)  # but blocks under --strict


def test_v15_hand_edited_generated_block_is_drift(repo: Path, mind: Mind) -> None:
    compile_mod.run(repo, check_only=False)
    doc = mind.nodes_dir / "telemetry" / "run.md"
    text = doc.read_text(encoding="utf-8").replace(
        "<!-- vulcan:connections:begin -->",
        "<!-- vulcan:connections:begin -->\nhand-edited nonsense",
    )
    doc.write_text(text, encoding="utf-8")
    assert "V15" in rules(check(repo))


def test_v16_prose_wikilink_without_edge_warns(repo: Path, mind: Mind) -> None:
    doc = mind.nodes_dir / "propagator" / "propagate_orbit.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "## Purpose", "## Purpose\nRelated: [[telemetry.write_telemetry]].\n"
        ),
        encoding="utf-8",
    )

    def mutate(d):
        d["edges"] = [
            e for e in d["edges"]
            if not (e["from"]["node"] == "propagator.propagate_orbit"
                    and e["to"]["node"] == "telemetry.write_telemetry")
        ]
    write_master(mind, mutate)
    assert "V16" in rules(check(repo))


def test_v17_stale_lines_warn(repo: Path, mind: Mind) -> None:
    def mutate(d):
        d["nodes"][0]["source"]["lines"] = [900, 950]
    write_master(mind, mutate)
    assert "V17" in rules(check(repo))
