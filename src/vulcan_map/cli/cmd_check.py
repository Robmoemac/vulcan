"""`vulcan check` — the completion gate (PLAN.md P1)."""

from __future__ import annotations

import argparse
import json

from .. import __version__
from ..core import compile as compile_mod
from ._common import colour, resolve_repo, GREEN, RED, YELLOW, DIM


def report_lines(result: compile_mod.CompileResult, strict: bool) -> list[str]:
    out: list[str] = []
    errors = [f for f in result.report.findings if f.severity == "error"]
    warnings = result.report.warnings()

    for f in errors:
        out.append(colour(f.format(), RED))
    for f in warnings:
        out.append(colour(f.format(), YELLOW))
    return out


def proof_block(result: compile_mod.CompileResult, repo_root, strict: bool) -> str:
    """A quotable attestation of the gate result.

    Completion claims travel between agents as prose, which is exactly what makes
    them untrustworthy. This block is generated from the run that just happened,
    names the commit it was taken against, and states the verdict either way —
    so a FAIL cannot be hidden by simply not pasting it.
    """
    from ..core import handoff as handoff_mod
    from ..core.repo import git_commit

    status = handoff_mod.collect(result.workspace, result.report, git_commit(repo_root))
    verdict = "PASS" if status.strict_ok else "FAIL"
    lines = [
        "----- VULCAN PROOF OF COMPLETION -----",
        f"tool            : vulcan-map/{__version__}",
        f"repo commit     : {status.repo_commit or 'unknown'}",
        f"region          : {status.region}",
        "gate            : vulcan check --strict",
        f"verdict         : {verdict}",
        f"exit code       : {0 if status.strict_ok else 1}",
        f"errors/warnings : {status.errors}/{status.warnings}",
        f"nodes/edges     : {status.nodes}/{status.edges}",
        f"in-scope files  : {status.in_scope}",
        f"described files : {status.described}",
        f"outstanding     : {len(status.outstanding)}",
        "----- END PROOF -----",
    ]
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo(args)
    result = compile_mod.run(repo_root, region=args.region, check_only=True, strict=args.strict)
    report = result.report

    if getattr(args, "proof", False):
        print(proof_block(result, repo_root, args.strict))
        return 0 if report.ok(args.strict) else 1

    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(args.strict), indent=2))
        return 0 if report.ok(args.strict) else 1

    for line in report_lines(result, args.strict):
        print(line)

    n_err = len([f for f in report.findings if f.severity == "error"])
    n_warn = len(report.warnings())
    ws = result.workspace

    print()
    summary = (
        f"{len(ws.all_nodes())} nodes · "
        f"{sum(len(list(c.all_edges())) for c in ws.charts)} edges "
        f"· region {ws.region.name!r} · {len(ws.charts)} chart(s)"
    )
    print(colour(summary, DIM))
    if result.pending_applied:
        # check validates the folded result but writes nothing, so say so plainly.
        print(
            colour(
                f"includes {result.pending_applied} queued UI edit(s) not yet written "
                "— run `vulcan compile` to fold them in",
                YELLOW,
            )
        )

    if report.ok(args.strict):
        print(colour("check: PASS", GREEN))
        return 0

    summary = f"check: FAIL — {n_err} error(s), {n_warn} warning(s)"
    if args.strict and n_err == 0:
        summary = f"check: FAIL (strict) — {n_warn} warning(s) promoted to errors"
    print(colour(summary, RED))
    print(colour("You are not done. Fix the findings above and run again.", RED))
    return 1
