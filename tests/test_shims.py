"""Cross-shell launcher (PLAN.md §12.2).

The shims are generated into a temp directory and executed; nothing on the
developer's machine is modified, and PATH is never touched by these tests.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from vulcan_map.cli import cmd_install_shim as shim

WINDOWS = os.name == "nt"
REPO_SRC = str(Path(__file__).resolve().parents[1] / "src")


@pytest.fixture
def shim_dir(tmp_path: Path, monkeypatch) -> Path:
    target = tmp_path / "bin"
    monkeypatch.setattr(shim, "shim_dir", lambda: target)
    return target


def install(shim_dir: Path) -> None:
    for path, text in shim.planned_files(Path(sys.executable)).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if not WINDOWS:
            path.chmod(0o755)


def env() -> dict[str, str]:
    e = dict(os.environ)
    e["PYTHONPATH"] = REPO_SRC
    return e


def test_planned_files_match_platform(shim_dir: Path) -> None:
    names = {p.name for p in shim.planned_files(Path(sys.executable))}
    if WINDOWS:
        # .cmd is primary: callable from BOTH cmd.exe and PowerShell,
        # whereas a .ps1 is not callable from cmd.
        assert names == {"vulcan.cmd", "vulcan.ps1"}
    else:
        assert names == {"vulcan"}


def test_shim_invokes_the_env_interpreter_directly(shim_dir: Path) -> None:
    """Layer 2 must work with no conda env activated."""
    text = next(iter(shim.planned_files(Path(sys.executable)).values()))
    assert sys.executable.replace("\\", "\\") in text or sys.executable in text
    assert "vulcan_map.cli" in text


@pytest.mark.skipif(not WINDOWS, reason="cmd.exe only exists on Windows")
def test_cmd_shim_runs_from_cmd(shim_dir: Path) -> None:
    install(shim_dir)
    out = subprocess.run(
        ["cmd.exe", "/c", str(shim_dir / "vulcan.cmd"), "--version"],
        capture_output=True, text=True, env=env(), timeout=180,
    )
    assert out.returncode == 0, out.stderr
    assert "vulcan-map" in out.stdout


@pytest.mark.skipif(
    not WINDOWS or shutil.which("powershell") is None, reason="PowerShell unavailable"
)
def test_cmd_shim_runs_from_powershell(shim_dir: Path) -> None:
    """The .cmd — not the .ps1 — is what makes one artefact serve both shells."""
    install(shim_dir)
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"& '{shim_dir / 'vulcan.cmd'}' --version"],
        capture_output=True, text=True, env=env(), timeout=180,
    )
    assert out.returncode == 0, out.stderr
    assert "vulcan-map" in out.stdout


@pytest.mark.skipif(
    not WINDOWS or shutil.which("powershell") is None, reason="PowerShell unavailable"
)
def test_ps1_shim_runs_from_powershell(shim_dir: Path) -> None:
    install(shim_dir)
    out = subprocess.run(
        ["powershell", "-NoProfile", "-File", str(shim_dir / "vulcan.ps1"), "--version"],
        capture_output=True, text=True, env=env(), timeout=180,
    )
    assert out.returncode == 0, out.stderr
    assert "vulcan-map" in out.stdout


@pytest.mark.skipif(WINDOWS, reason="POSIX shim")
def test_posix_shim_runs_from_sh(shim_dir: Path) -> None:
    install(shim_dir)
    out = subprocess.run(
        ["sh", str(shim_dir / "vulcan"), "--version"],
        capture_output=True, text=True, env=env(), timeout=180,
    )
    assert out.returncode == 0, out.stderr
    assert "vulcan-map" in out.stdout


def test_install_shim_does_not_touch_path_without_consent(shim_dir: Path, capsys) -> None:
    """PATH is a persistent user-visible change; --path is required."""
    import argparse

    args = argparse.Namespace(dry_run=False, path=False)
    assert shim.run(args) == 0
    out = capsys.readouterr().out
    assert "NOT on your PATH" in out
    assert "--path" in out


def test_dry_run_writes_nothing(shim_dir: Path, capsys) -> None:
    import argparse

    assert shim.run(argparse.Namespace(dry_run=True, path=False)) == 0
    assert not shim_dir.exists()
    assert "dry run" in capsys.readouterr().out


def test_shim_carries_source_path_when_not_installed(shim_dir: Path) -> None:
    """Running from a checkout, the shim must set PYTHONPATH itself.

    Otherwise `python -m vulcan_map.cli` fails with ModuleNotFoundError for
    anyone who has not pip-installed the package — which, under the conda-only
    rule, is everyone.
    """
    src = shim.source_root()
    assert src is not None, "test suite runs from a source checkout"
    for text in shim.planned_files(Path(sys.executable)).values():
        assert str(src) in text
        assert "PYTHONPATH" in text
