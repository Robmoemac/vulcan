"""`vulcan find` and `vulcan workflow` — building cross-cutting views (D12).

`find` is how an agent discovers what is *already* mapped before creating
anything. `workflow` records the seeds it chose; membership is computed by the
compiler, never typed in.
"""

from __future__ import annotations

import argparse
import json

from ..core import workflow as workflow_mod
from ..core.workspace import load_workspace
from ._common import colour, resolve_mind, resolve_repo, DIM, GREEN, RED, YELLOW


def _matches(ws, needle: str) -> list[tuple[str, str, str]]:
    """Nodes whose id, label, tags or doc prose mention `needle`."""
    lowered = needle.lower()
    hits: list[tuple[str, str, str]] = []
    docs = {d.id: d for d in ws.docs if d.id}

    for node in ws.all_nodes():
        where = ""
        if lowered in node.id.lower() or lowered in node.label.lower():
            where = "name"
        elif any(lowered in t.lower() for t in node.tags):
            where = "tag"
        elif node.source.file and lowered in node.source.file.lower():
            where = "path"
        else:
            doc = docs.get(node.id)
            if doc is not None and lowered in doc.prose().lower():
                where = "doc"
        if where:
            hits.append((node.id, node.source.file or "", where))
    return sorted(hits)


def run_find(args: argparse.Namespace) -> int:
    repo_root = resolve_repo(args)
    resolve_mind(args)
    ws = load_workspace(repo_root, args.region)

    hits = _matches(ws, args.query)
    if not hits:
        print(colour(f"No mapped node mentions {args.query!r}.", YELLOW))
        print(colour(
            "If the workflow genuinely is not mapped yet, map it first — a "
            "workflow view borrows existing nodes, it does not invent them.", DIM,
        ))
        return 1

    for nid, file, where in hits[: args.limit]:
        print(f"  {nid:<52} {where:<5} {file}")
    if len(hits) > args.limit:
        print(colour(f"  ... and {len(hits) - args.limit} more", DIM))
    print()
    print(colour(f"{len(hits)} node(s) match. Seed a workflow with the entry points:", DIM))
    print(f"  vulcan workflow add <id> --title '...' --seed <node> [--seed <node> ...]")
    return 0


def run_workflow(args: argparse.Namespace) -> int:
    repo_root = resolve_repo(args)
    mind = resolve_mind(args)
    ws = load_workspace(repo_root, args.region)

    if args.action == "list":
        flows = [c for c in ws.charts if c.is_workflow]
        if not flows:
            print(colour("No workflow charts yet.", DIM))
            return 0
        for c in sorted(flows, key=lambda c: c.chart_id):
            seeds = ", ".join(
                s["node"] if isinstance(s, dict) else s for s in c.seeds
            )
            print(f"  {c.chart_id:<18} {len(c.member_nodes):>4} nodes   seeds: {seeds}")
        return 0

    if not args.name:
        raise SystemExit("`vulcan workflow add` needs a name")
    if not args.seed:
        raise SystemExit(
            "`vulcan workflow add` needs at least one --seed.\n"
            "A workflow is defined by its entry points; use `vulcan find` to locate them."
        )

    known = {n.id for n in ws.all_nodes()}
    unknown = [s for s in args.seed if s not in known]
    if unknown:
        raise SystemExit(
            "These seeds are not mapped nodes: " + ", ".join(unknown) +
            "\nMap the symbol first, then seed the workflow with it."
        )

    path = mind.subcharts_dir / f"{args.name}.graph.json"
    if path.exists() and not args.force:
        raise SystemExit(f"{path} already exists; pass --force to replace it.")

    chart = {
        "schema_version": "1.0.0",
        "chart_id": args.name,
        "chart_kind": "workflow",
        "derives_from": "master",
        "title": args.title or f"{args.name} workflow",
        "seeds": [{"node": s, "why": args.why or "entry point"} for s in args.seed],
        "traversal": {"direction": args.direction, "max_depth": args.depth},
        "member_nodes": [],
        "local_nodes": [],
        "local_edges": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(chart, indent=2) + "\n", encoding="utf-8", newline="\n")

    # Show what it will contain, without writing it — compile owns that.
    seeds = [workflow_mod.Seed(node=s) for s in args.seed]
    closure = workflow_mod.compute_closure(
        seeds, ws.charts, ws.all_nodes(),
        workflow_mod.Traversal(direction=args.direction, max_depth=args.depth),
    )
    print(colour(f"workflow {args.name!r} written to {mind.rel(path)}", GREEN))
    print(f"  seeds     : {', '.join(args.seed)}")
    print(f"  traversal : {args.direction}, depth {args.depth}")
    print(f"  reaches   : {len(closure.members)} node(s), depth {closure.depth_reached}")
    if len(closure.members) <= len(seeds):
        print(colour(
            "  The seeds reach nothing beyond themselves. Either the call edges "
            "have not been traced yet, or the direction is wrong.", YELLOW,
        ))
    print()
    print("Run `vulcan compile` — membership is generated from the seeds, not typed in.")
    return 0
