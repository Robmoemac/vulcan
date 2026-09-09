"""`vulcan region` — inspect and modify regions (PLAN.md §5.2).

`add` exists so an agent can persist a natural-language scope as explicit globs
rather than acting on an unwritten interpretation of it.
"""

from __future__ import annotations

import argparse

import yaml

from ..core.config import load_config
from ._common import colour, resolve_mind, resolve_repo, DIM, GREEN


def run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo(args)
    mind = resolve_mind(args)
    cfg = load_config(mind.config_path)

    if args.action == "list":
        for name, region in sorted(cfg.regions.items()):
            marker = "*" if name == cfg.default_region else " "
            print(f" {marker} {name:<16} {region.granularity:<9} {region.description}")
        print()
        print(colour("* = default region", DIM))
        return 0

    if args.action == "show":
        name = args.name or cfg.default_region
        region = cfg.region(name)
        files = cfg.in_scope_files(repo_root, region)
        print(f"region:      {region.name}")
        print(f"granularity: {region.granularity}")
        print(f"description: {region.description or '—'}")
        print(f"include:     {', '.join(region.include)}")
        print(f"exclude:     {', '.join(region.exclude) or '—'}")
        print(f"in scope:    {len(files)} file(s)")
        for f in files[:25]:
            print(f"    {f}")
        if len(files) > 25:
            print(f"    ... and {len(files) - 25} more")
        return 0

    # add
    if not args.name:
        raise SystemExit("`vulcan region add` needs a region name")
    if not args.include:
        raise SystemExit("`vulcan region add` needs at least one --include glob")

    raw = yaml.safe_load(mind.config_path.read_text(encoding="utf-8"))
    body: dict[str, object] = {"include": list(args.include)}
    if args.exclude:
        body["exclude"] = list(args.exclude)
    body["granularity"] = args.granularity
    if args.description:
        body["description"] = args.description
    raw.setdefault("regions", {})[args.name] = body

    mind.config_path.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8", newline="\n"
    )

    cfg = load_config(mind.config_path)
    region = cfg.region(args.name)
    files = cfg.in_scope_files(repo_root, region)
    print(colour(f"region {args.name!r} written to {mind.rel(mind.config_path)}", GREEN))
    print(f"  include: {', '.join(region.include)}")
    print(f"  exclude: {', '.join(region.exclude) or '—'}")
    print(f"  → {len(files)} file(s) in scope")
    return 0
