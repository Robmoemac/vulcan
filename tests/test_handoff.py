"""The handoff checkpoint: tool-written state that survives agent changeover."""

from __future__ import annotations

import json
from pathlib import Path

from vulcan_map.core import compile as compile_mod
from vulcan_map.core.repo import Mind


def handoff_text(mind: Mind) -> str:
    return (mind.root / "HANDOFF.md").read_text(encoding="utf-8")


def test_compile_writes_handoff_and_status(repo: Path, mind: Mind) -> None:
    compile_mod.run(repo, check_only=False)
    assert (mind.root / "HANDOFF.md").exists()
    assert (mind.build_dir / "status.json").exists()


def test_handoff_says_complete_when_the_gate_passes(repo: Path, mind: Mind) -> None:
    compile_mod.run(repo, check_only=False)
    text = handoff_text(mind)
    assert "**PASS**" in text
    assert "Is the map complete? | **YES**" in text


def test_handoff_says_not_complete_and_lists_outstanding(repo: Path, mind: Mind) -> None:
    (repo / "src" / "unmapped.py").write_text("def lonely():\n    return 1\n", encoding="utf-8")
    compile_mod.run(repo, check_only=False)

    text = handoff_text(mind)
    assert "**FAIL**" in text
    assert "Is the map complete? | **NO**" in text
    assert "src/unmapped.py" in text
    assert "This map is NOT finished" in text


def test_handoff_repudiates_predecessor_claims(repo: Path, mind: Mind) -> None:
    """The whole point: an incoming agent must not inherit a 'done' claim."""
    compile_mod.run(repo, check_only=False)
    text = handoff_text(mind)
    assert "void" in text
    assert "written by the tool" in text


def test_status_json_lists_every_outstanding_file(repo: Path, mind: Mind) -> None:
    for name in ("a.py", "b.py", "c.py"):
        (repo / "src" / name).write_text("def f():\n    return 1\n", encoding="utf-8")
    compile_mod.run(repo, check_only=False)

    data = json.loads((mind.build_dir / "status.json").read_text(encoding="utf-8"))
    assert data["gate"]["passes"] is False
    assert data["gate"]["exit_code"] == 1
    assert data["counts"]["outstanding_files"] == 3
    assert set(data["outstanding"]) == {"src/a.py", "src/b.py", "src/c.py"}


def test_handoff_is_deterministic(repo: Path, mind: Mind) -> None:
    """No wall-clock in the committed file, or every compile becomes a diff."""
    compile_mod.run(repo, check_only=False)
    first = handoff_text(mind)
    compile_mod.run(repo, check_only=False)
    assert handoff_text(mind) == first


def test_check_does_not_write_handoff(repo: Path, mind: Mind) -> None:
    compile_mod.run(repo, check_only=False)
    before = handoff_text(mind)
    (repo / "src" / "sneaky.py").write_text("def s():\n    return 1\n", encoding="utf-8")
    compile_mod.run(repo, check_only=True)
    assert handoff_text(mind) == before
