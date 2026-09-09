"""`vulcan doctor` — environment diagnosis (PLAN.md §12.1, A7).

Never installs anything. Installing a package manager system-wide without
consent is not an acceptable default, so conda absence is reported with the
exact command to run, and nothing more.
"""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .. import __version__
from ._common import colour, DIM, GREEN, RED, YELLOW

CORE_MODULES = ["yaml", "jsonschema", "networkx"]
UI_MODULES = ["PySide6", "matplotlib", "markdown_it"]

MINICONDA = {
    "nt": "winget install --id Anaconda.Miniconda3",
    "posix": "https://docs.conda.io/projects/miniconda/en/latest/  (see platform installer)",
}


def _mark(ok: bool) -> str:
    return colour("ok ", GREEN) if ok else colour("MISSING", RED)


def _check_modules(names: list[str]) -> list[tuple[str, bool, str]]:
    out = []
    for name in names:
        try:
            mod = importlib.import_module(name)
            out.append((name, True, getattr(mod, "__version__", "?")))
        except Exception:
            out.append((name, False, ""))
    return out


def run(args: argparse.Namespace) -> int:
    print(f"vulcan-map {__version__}")
    print(f"python     {sys.version.split()[0]}  ({sys.executable})")
    print()

    conda = shutil.which("conda")
    print("conda")
    if conda:
        try:
            ver = subprocess.run([conda, "--version"], capture_output=True, text=True, timeout=20)
            print(f"  {_mark(True)} {ver.stdout.strip() or 'conda'}  ({conda})")
        except (OSError, subprocess.SubprocessError):
            print(f"  {_mark(True)} found at {conda} (version query failed)")
    else:
        print(f"  {_mark(False)} conda not found on PATH")
        print(colour(f"  install it yourself: {MINICONDA.get(os.name, MINICONDA['posix'])}", YELLOW))
        print(colour("  vulcan will not install a package manager for you (A7).", DIM))

    env = os.environ.get("CONDA_PREFIX")
    print(f"  env        {env or colour('(no conda env active)', YELLOW)}")

    print()
    print("core dependencies")
    core_ok = True
    for name, ok, ver in _check_modules(CORE_MODULES):
        core_ok &= ok
        print(f"  {_mark(ok)} {name:<16} {ver}")

    print()
    print("ui dependencies")
    ui_ok = True
    for name, ok, ver in _check_modules(UI_MODULES):
        ui_ok &= ok
        print(f"  {_mark(ok)} {name:<16} {ver}")

    print()
    print("shims")
    from .cmd_install_shim import planned_files, shim_dir, _on_path

    d = shim_dir()
    files = planned_files(Path(sys.executable))
    present = [p for p in files if p.exists()]
    print(f"  {_mark(bool(present))} {len(present)}/{len(files)} installed in {d}")
    print(f"  {_mark(_on_path(d))} shim dir on PATH")
    if not present:
        print(colour("  run `vulcan install-shim` to make `vulcan` work outside the env", DIM))

    print()
    if core_ok and ui_ok:
        print(colour("doctor: OK", GREEN))
        return 0
    if core_ok:
        print(colour("doctor: core OK, UI unavailable (`vulcan ui` will not run)", YELLOW))
        return 0
    print(colour("doctor: core dependencies missing", RED))
    print("Create the environment with conda-forge only (D1, no pip):")
    print("    conda create -n vulcan --override-channels -c conda-forge \\")
    print("        python=3.12 pyyaml jsonschema networkx pyside6 matplotlib-base markdown-it-py")
    return 1
