"""`vulcan export` — a view-only HTML snapshot anyone can open in a browser."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..core import export as export_mod
from ..core.repo import Mind
from ._common import resolve_repo


def run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo(args)
    mind = Mind(repo_root)
    if args.out:
        out = Path(args.out)
    else:
        from ..core.config import load_config

        project = load_config(mind.config_path).project
        out = mind.build_dir / "export" / f"{project}.html"
    result = export_mod.export_html(repo_root, out, region=args.region)
    print(f"exported {result.charts} chart(s) · {result.nodes} node(s) · {result.docs} doc(s) "
          f"· {result.bytes / 1e6:.1f} MB")
    print(f"  {result.path.resolve()}")
    print("Open it in any browser. It is a view-only snapshot; it cannot edit the map.")
    return 0
