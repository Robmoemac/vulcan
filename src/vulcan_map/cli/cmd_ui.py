"""`vulcan ui` — open the node-graph editor."""

from __future__ import annotations

import argparse

from ._common import resolve_repo


def run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo(args)

    try:
        from ..ui.app import launch
    except ImportError as exc:
        raise SystemExit(
            f"The UI needs PySide6, which is not importable ({exc}).\n"
            "Create the environment from conda-forge only (D1 — no pip):\n"
            "    conda create -n vulcan --override-channels -c conda-forge \\\n"
            "        python=3.12 pyyaml jsonschema networkx pyside6 matplotlib-base markdown-it-py\n"
            "Then run `vulcan doctor`."
        ) from exc

    return launch(repo_root, region=args.region, chart_id=getattr(args, "chart", None))
