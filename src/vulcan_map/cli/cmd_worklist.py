"""`vulcan worklist` — the durable progress ledger (PLAN.md P4)."""

from __future__ import annotations

import argparse
import json

from ..core.worklist import build_worklist, pending
from ..core.workspace import load_workspace
from ._common import colour, resolve_mind, resolve_repo, DIM, GREEN


def run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo(args)
    mind = resolve_mind(args)

    if args.build or not mind.worklist_path.exists():
        ws = load_workspace(repo_root, args.region)
        data = build_worklist(ws)
        mind.build_dir.mkdir(parents=True, exist_ok=True)
        mind.worklist_path.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    else:
        data = json.loads(mind.worklist_path.read_text(encoding="utf-8"))

    counts = data["counts"]

    if args.remaining:
        print(data["remaining"])
        return 0

    if args.next:
        files = pending(data, args.next)
        if not files:
            print(colour("No pending files. Run `vulcan check --strict`.", GREEN))
            return 0
        for f in files:
            print(f)
        print(
            colour(
                f"\n{len(files)} of {counts['pending']} pending shown "
                f"· region {data['region']!r} · granularity {data['granularity']}",
                DIM,
            )
        )
        return 0

    print(f"region:      {data['region']} ({data['granularity']} granularity)")
    print(f"total:       {counts['total']}")
    print(f"mapped:      {counts['mapped']}")
    print(f"covered:     {counts['covered']}")
    print(f"pending:     {counts['pending']}")
    if counts["pending"]:
        print()
        print(colour("Not done. `vulcan worklist --next 8` for the next batch.", DIM))
    return 0
