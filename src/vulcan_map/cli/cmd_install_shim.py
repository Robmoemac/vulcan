"""`vulcan install-shim` — cross-shell launcher (PLAN.md §12.2).

Layer 2 of the CLI story: makes `vulcan` work when the conda env is *not*
activated, by invoking the env's interpreter directly.

On Windows the primary artefact is a `.cmd`, because a .cmd is callable from both
cmd.exe and PowerShell, whereas a .ps1 is not callable from cmd.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ._common import colour, DIM, GREEN, YELLOW

WINDOWS = os.name == "nt"


def shim_dir() -> Path:
    if WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Vulcan" / "bin"
    return Path.home() / ".local" / "bin"


def source_root() -> Path | None:
    """The `src` directory when running from a checkout rather than an install.

    The shim must carry it, otherwise `python -m vulcan_map.cli` fails with
    ModuleNotFoundError for anyone who has not installed the package.
    """
    import vulcan_map

    pkg = Path(vulcan_map.__file__).resolve().parent  # .../src/vulcan_map
    src = pkg.parent
    in_site = any(part in ("site-packages", "dist-packages") for part in src.parts)
    return None if in_site else src


def _posix_shim(python: Path, src: Path | None) -> str:
    export = f'PYTHONPATH="{src}${{PYTHONPATH:+:$PYTHONPATH}}"\nexport PYTHONPATH\n' if src else ""
    return f'#!/usr/bin/env sh\n{export}exec "{python}" -m vulcan_map.cli "$@"\n'


def _cmd_shim(python: Path, src: Path | None) -> str:
    setpath = f'set "PYTHONPATH={src};%PYTHONPATH%"\r\n' if src else ""
    return f'@echo off\r\n{setpath}"{python}" -m vulcan_map.cli %*\r\n'


def _ps1_shim(python: Path, src: Path | None) -> str:
    setpath = f'$env:PYTHONPATH = "{src};" + $env:PYTHONPATH\r\n' if src else ""
    return f'{setpath}& "{python}" -m vulcan_map.cli @args\r\nexit $LASTEXITCODE\r\n'


def planned_files(python: Path) -> dict[Path, str]:
    d = shim_dir()
    src = source_root()
    if WINDOWS:
        return {
            d / "vulcan.cmd": _cmd_shim(python, src),
            d / "vulcan.ps1": _ps1_shim(python, src),
        }
    return {d / "vulcan": _posix_shim(python, src)}


def _on_path(d: Path) -> bool:
    entries = [Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    return any(p.resolve() == d.resolve() for p in entries if p.exists())


def run(args: argparse.Namespace) -> int:
    python = Path(sys.executable)
    files = planned_files(python)
    d = shim_dir()

    print(f"interpreter: {python}")
    print(f"shim dir:    {d}")
    for path in files:
        print(f"  → {path.name}")

    if args.dry_run:
        print()
        print(colour("dry run — nothing written", DIM))
        return 0

    d.mkdir(parents=True, exist_ok=True)
    for path, text in files.items():
        path.write_text(text, encoding="utf-8")
        if not WINDOWS:
            path.chmod(0o755)
    print()
    print(colour(f"installed {len(files)} shim(s)", GREEN))

    if _on_path(d):
        print(colour("shim dir is already on PATH — `vulcan` is ready", GREEN))
        return 0

    if not args.path:
        print()
        print(colour("Shim dir is NOT on your PATH.", YELLOW))
        print("PATH is a persistent, user-visible change, so it is not made without consent.")
        print("Re-run with --path to add it, or add it yourself:")
        if WINDOWS:
            print(f'    setx PATH "%PATH%;{d}"')
        else:
            print(f'    echo \'export PATH="{d}:$PATH"\' >> ~/.profile')
        return 0

    return _add_to_path(d)


def _posix_style(d: Path) -> str:
    """Windows path rendered for a POSIX-ish shell (Git Bash)."""
    s = str(d).replace("\\", "/")
    if len(s) > 1 and s[1] == ":":
        s = f"/{s[0].lower()}{s[2:]}"
    return s


def _broadcast_environment_change() -> bool:
    """Tell running processes the environment changed.

    Writing HKCU\\Environment alone is not enough: Explorer caches the block it
    hands to every process it launches, so without this broadcast even a shell
    opened *after* the change inherits the stale PATH until the user logs out.
    """
    import ctypes
    from ctypes import wintypes

    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    SMTO_ABORTIFHUNG = 0x0002

    send = ctypes.windll.user32.SendMessageTimeoutW
    send.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR,
        wintypes.UINT, wintypes.UINT, ctypes.POINTER(wintypes.DWORD),
    ]
    result = wintypes.DWORD()
    ok = send(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
        SMTO_ABORTIFHUNG, 5000, ctypes.byref(result),
    )
    return bool(ok)


def _add_to_path(d: Path) -> int:
    if WINDOWS:
        # Registry rather than setx: setx truncates PATH at 1024 characters.
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                            winreg.KEY_READ | winreg.KEY_WRITE) as key:
            try:
                current, kind = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current, kind = "", winreg.REG_EXPAND_SZ
            parts = [p for p in current.split(os.pathsep) if p]
            if str(d) not in parts:
                parts.append(str(d))
                winreg.SetValueEx(key, "Path", 0, kind, os.pathsep.join(parts))

        broadcast = _broadcast_environment_change()
        print(colour(f"added {d} to user PATH", GREEN))
        if broadcast:
            print("Open a NEW shell to pick it up (this one keeps its old PATH).")
        else:
            print(colour(
                "Could not broadcast the change; you may need to sign out and back in.",
                YELLOW,
            ))
        print(colour("To use it in the shell you are in right now:", DIM))
        print(f'    $env:PATH = "{d};$env:PATH"      # PowerShell')
        print(f'    set "PATH={d};%PATH%"            # cmd')
        print(f'    export PATH="{_posix_style(d)}:$PATH"   # bash')
        return 0

    profile = Path.home() / ".profile"
    line = f'export PATH="{d}:$PATH"'
    existing = profile.read_text(encoding="utf-8") if profile.exists() else ""
    if line not in existing:
        with profile.open("a", encoding="utf-8") as fh:
            fh.write(f"\n# added by vulcan install-shim\n{line}\n")
    print(colour(f"added {d} to PATH via ~/.profile (open a new shell to pick it up)", GREEN))
    return 0
