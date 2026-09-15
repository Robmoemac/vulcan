"""`vulcan export`: a self-contained, view-only HTML snapshot of the map."""

from __future__ import annotations

import json
import re
from pathlib import Path

from vulcan_map.core import export as export_mod
from vulcan_map.core.repo import Mind


def _payload_from(html: str) -> dict:
    m = re.search(r"window\.VULCAN = (.*?);\n</script>", html, re.DOTALL)
    assert m, "embedded data block not found"
    return json.loads(m.group(1).replace("<\\/", "</"))


def test_export_writes_one_self_contained_file(repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "map.html"
    res = export_mod.export_html(repo, out)
    assert out.exists() and res.bytes > 10_000
    html = out.read_text(encoding="utf-8")
    # Nothing is fetched from anywhere: no external scripts, styles or images.
    assert not re.search(r'<(script|link|img)[^>]+(src|href)="(https?:)?//', html)
    payload = _payload_from(html)
    assert res.charts == len(payload["charts"]) == 1
    assert "master" in payload["charts"]
    assert payload["verdict"] == "PASS"


def test_export_embeds_every_doc_rendered_and_wikilinks_become_node_links(repo: Path, tmp_path: Path) -> None:
    mind = Mind(repo)
    doc = mind.nodes_dir / "telemetry" / "run.md"
    doc.write_text(doc.read_text(encoding="utf-8").replace(
        "## Purpose\n", "## Purpose\nCalls [[propagator.propagate_orbit|the propagator]] first.\n"), encoding="utf-8")
    out = tmp_path / "map.html"
    export_mod.export_html(repo, out)
    payload = _payload_from(out.read_text(encoding="utf-8"))
    assert set(payload["docs"]) >= {"telemetry.run", "propagator.propagate_orbit", "telemetry.write_telemetry"}
    run_html = payload["docs"]["telemetry.run"]
    assert "<h2>Purpose</h2>" in run_html
    assert 'data-node="propagator.propagate_orbit"' in run_html and "the propagator" in run_html
    # frontmatter is not leaked into the rendered body
    assert "origin: agent" not in run_html


def test_export_never_writes_into_the_map(repo: Path, tmp_path: Path) -> None:
    mind = Mind(repo)
    before = {p: p.read_bytes() for p in mind.root.rglob("*") if p.is_file() and "_build" not in p.parts}
    export_mod.export_html(repo, tmp_path / "map.html")
    after = {p: p.read_bytes() for p in mind.root.rglob("*") if p.is_file() and "_build" not in p.parts}
    assert before == after


def test_export_records_drill_targets_for_nested_sheets(tmp_path: Path) -> None:
    from test_cluster import _big_repo, LAYOUT, EDGES
    from vulcan_map.core import compile as compile_mod
    from vulcan_map.core.cluster import group_id

    root = _big_repo(tmp_path, LAYOUT, EDGES)
    compile_mod.run(root, check_only=False)
    out = tmp_path / "map.html"
    export_mod.export_html(root, out)
    payload = _payload_from(out.read_text(encoding="utf-8"))
    alpha = group_id("src/big/alpha")
    target = payload["drill"].get(f"big|{alpha}")
    assert target and target in payload["charts"]
    assert payload["hierarchy"][target]["derives_from"] == "big"


def test_script_end_tag_inside_data_cannot_break_the_page(repo: Path, tmp_path: Path) -> None:
    mind = Mind(repo)
    doc = mind.nodes_dir / "telemetry" / "run.md"
    doc.write_text(doc.read_text(encoding="utf-8").replace(
        "## Purpose\n", "## Purpose\nWatch out for `</script>` in prose.\n"), encoding="utf-8")
    out = tmp_path / "map.html"
    export_mod.export_html(repo, out)
    html = out.read_text(encoding="utf-8")
    data_block = html.split("window.VULCAN = ", 1)[1].split("\n</script>", 1)[0]
    assert "</script>" not in data_block
