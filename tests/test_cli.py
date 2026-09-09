"""CLI behaviour, especially the exit codes the completion gate depends on."""

from __future__ import annotations

import json
from pathlib import Path

from vulcan_map.cli.__main__ import main


def run(*argv: str) -> int:
    return main(list(argv))


def test_check_exits_zero_on_a_complete_map(repo: Path, capsys) -> None:
    assert run("check", "--repo", str(repo)) == 0
    assert "PASS" in capsys.readouterr().out


def test_check_exits_nonzero_when_incomplete(repo: Path, capsys) -> None:
    """The gate must fail, or it is not a gate."""
    (repo / "src" / "unmapped.py").write_text("def x():\n    return 1\n", encoding="utf-8")
    assert run("check", "--repo", str(repo)) == 1
    out = capsys.readouterr().out
    assert "V13" in out and "You are not done" in out


def test_check_json_output_is_machine_readable(repo: Path, capsys) -> None:
    run("check", "--repo", str(repo), "--json")
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["error_count"] == 0


def test_init_scaffolds_and_installs_skills(tmp_path: Path, capsys) -> None:
    root = tmp_path / "fresh"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")

    assert run("init", "--repo", str(root)) == 0
    assert (root / "vulcan_mind" / "vulcan.config.yaml").exists()
    assert (root / "vulcan_mind" / "graph" / "master.graph.json").exists()
    assert (root / ".claude" / "skills" / "vulcan-map" / "SKILL.md").exists()
    assert (root / "AGENTS.md").exists()


def test_init_then_check_fails_because_nothing_is_mapped(tmp_path: Path) -> None:
    """A fresh install is not a finished map — the gate says so immediately."""
    root = tmp_path / "fresh"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    run("init", "--repo", str(root))
    assert run("check", "--repo", str(root)) == 1


def test_worklist_remaining_counts_pending_files(repo: Path, capsys) -> None:
    (repo / "src" / "extra.py").write_text("def e():\n    return 1\n", encoding="utf-8")
    assert run("worklist", "--build", "--remaining", "--repo", str(repo)) == 0
    assert capsys.readouterr().out.strip() == "1"


def test_worklist_next_lists_files(repo: Path, capsys) -> None:
    (repo / "src" / "extra.py").write_text("def e():\n    return 1\n", encoding="utf-8")
    run("worklist", "--build", "--next", "5", "--repo", str(repo))
    assert "src/extra.py" in capsys.readouterr().out


def test_region_add_persists_globs(repo: Path, capsys) -> None:
    code = run(
        "region", "add", "sim",
        "--include", "src/propagator.py",
        "--exclude", "src/telemetry.py",
        "--description", "Propagation only.",
        "--repo", str(repo),
    )
    assert code == 0
    text = (repo / "vulcan_mind" / "vulcan.config.yaml").read_text(encoding="utf-8")
    assert "sim:" in text and "src/propagator.py" in text


def test_region_scopes_the_check(repo: Path) -> None:
    """V11/V13 must follow the active region, not the default one."""
    run("region", "add", "sim",
        "--include", "src/propagator.py",
        "--repo", str(repo))
    # telemetry nodes are now out of region -> V11 fires
    assert run("check", "--repo", str(repo), "--region", "sim") == 1


def test_compile_exit_code_tracks_validity(repo: Path) -> None:
    assert run("compile", "--repo", str(repo)) == 0


def test_unknown_region_is_a_clean_error(repo: Path, capsys) -> None:
    assert run("check", "--repo", str(repo), "--region", "ghost") == 2
    assert "Unknown region" in capsys.readouterr().err
