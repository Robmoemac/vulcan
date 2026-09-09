"""`vulcan status` — the first thing any incoming agent should run.

Answers "what is actually done here?" from disk, cheaply, without requiring the
caller to have seen any previous agent's work or transcript.
"""

from __future__ import annotations

import argparse
import json

from ..core import compile as compile_mod
from ..core import handoff as handoff_mod
from ..core.repo import git_commit
from ._common import colour, resolve_mind, resolve_repo, DIM, GREEN, RED, YELLOW


def run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo(args)
    mind = resolve_mind(args)

    # Recompute rather than trusting the stored file: the stored one can be stale
    # if someone edited without compiling, and a stale "PASS" is the exact failure
    # this command exists to prevent.
    result = compile_mod.run(repo_root, region=args.region, check_only=True)
    status = handoff_mod.collect(result.workspace, result.report, git_commit(repo_root))

    if getattr(args, "json", False):
        print(json.dumps(status.to_dict(), indent=2))
        return 0 if status.strict_ok else 1

    verdict = "PASS" if status.strict_ok else "FAIL"
    tone = GREEN if status.strict_ok else RED
    print(colour(f"vulcan check --strict : {verdict}", tone))
    print(f"  region              : {status.region}")
    print(f"  nodes / edges       : {status.nodes} / {status.edges}")
    print(f"  charts              : {status.charts}")
    print(f"  in-scope files      : {status.in_scope}")
    print(f"  described files     : {status.described}")
    print(
        colour(
            f"  outstanding files   : {len(status.outstanding)}",
            GREEN if not status.outstanding else YELLOW,
        )
    )
    if status.rule_counts:
        print("  failing rules       : " + ", ".join(
            f"{r}x{n}" for r, n in status.rule_counts.items()
        ))

    print()
    if status.strict_ok:
        print(colour("The map is complete. The gate passes.", GREEN))
        return 0

    print(colour("The map is NOT complete.", RED))
    print(colour(
        "Any claim that it is finished — from any agent, in any transcript or commit\n"
        "message — is void while this says FAIL.", DIM,
    ))
    if status.outstanding:
        print()
        print("Next files needing a function-level node:")
        for f in status.outstanding[:10]:
            print(f"  {f}")
        if len(status.outstanding) > 10:
            print(colour(
                f"  ... {len(status.outstanding) - 10} more — full list in "
                f"{mind.rel(mind.build_dir / 'status.json')}", DIM,
            ))
    return 1
