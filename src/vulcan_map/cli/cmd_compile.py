"""`vulcan compile` — run the pipeline and write."""

from __future__ import annotations

import argparse

from ..core import compile as compile_mod
from ._common import colour, resolve_repo, DIM, GREEN, RED, YELLOW


def run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo(args)
    result = compile_mod.run(repo_root, region=args.region, check_only=False, strict=args.strict)
    report = result.report

    for f in report.findings:
        print(colour(f.format(), RED if f.severity == "error" else YELLOW))

    print()
    parts = [f"compiled · {result.sockets_lifted} socket set(s) lifted"]
    if result.pending_applied:
        parts.append(f"{result.pending_applied} queued UI edit(s) folded")
    parts.append(f"{result.positions_assigned} position(s) assigned")
    parts.append(f"{len(result.written)} file(s) written")
    print(colour(" · ".join(parts), DIM))
    for chart_id, graph in sorted(result.resolved.items()):
        print(f"  {chart_id:<24} {len(graph.nodes):>4} nodes  {len(graph.edges):>4} edges")

    if report.ok(args.strict):
        print(colour("check: PASS", GREEN))
        return 0
    n_err = len([f for f in report.findings if f.severity == "error"])
    print(colour(f"check: FAIL — {n_err} error(s). Not done.", RED))
    return 1
