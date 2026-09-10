"""`vulcan scaffold` — generate the nodes and doc skeletons D11 requires.

Structure is derived from source; prose is not. A scaffolded map still fails the
gate, and it should: the skeletons exist, nobody has read the code yet.
"""

from __future__ import annotations

import argparse

from ..core import scaffold as scaffold_mod
from ..core.workspace import load_workspace
from ._common import colour, resolve_repo, DIM, GREEN, YELLOW


def run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo(args)
    ws = load_workspace(repo_root, args.region)
    plan = scaffold_mod.plan(ws)

    if not plan.node_count:
        print(colour("Nothing to scaffold — every significant symbol has a node.", GREEN))
        return 0

    print(f"{plan.node_count} node(s) and {len(plan.docs)} doc(s) to create:")
    for chart_id, nodes in sorted(plan.nodes_by_chart.items()):
        print(f"  {chart_id:<14} +{len(nodes)}")

    if args.dry_run:
        print()
        print(colour("dry run — nothing written", DIM))
        return 0

    nodes, docs = scaffold_mod.apply(ws, plan)
    print()
    print(colour(f"created {nodes} node(s) and {docs} doc skeleton(s)", GREEN))
    print(colour(
        "These are skeletons: Purpose and Design are empty, so the gate still "
        "fails on V12 until the prose is written. That is intended — a scaffold "
        "is not a map.", YELLOW,
    ))
    print("Next: `vulcan compile`, then fill in the docs and re-check.")
    return 0
