"""`vulcan check` — the completion gate (PLAN.md P1)."""

from __future__ import annotations

import argparse
import json

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


def run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo(args)
    result = compile_mod.run(repo_root, region=args.region, check_only=True, strict=args.strict)
    report = result.report

    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(args.strict), indent=2))
        return 0 if report.ok(args.strict) else 1

    for line in report_lines(result, args.strict):
        print(line)

    n_err = len([f for f in report.findings if f.severity == "error"])
    n_warn = len(report.warnings())
    ws = result.workspace

    print()
    print(
        colour(
            f"{len(ws.all_nodes())} nodes · {sum(len(list(c.all_edges())) for c in ws.charts)} edges "
            f"· region {ws.region.name!r} · {len(ws.charts)} chart(s)",
            DIM,
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
