"""`vulcan` entry point.

Default action with no subcommand is to open the UI scoped to the current repo
(PLAN.md §12.1/§12.3).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .. import __version__


def _add_repo_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--repo", type=Path, default=None, help="Target repo root (default: discover from cwd)")
    p.add_argument("--here", action="store_true", help="Use cwd literally; do not walk up")
    p.add_argument("--region", default=None, help="Region name from vulcan.config.yaml")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vulcan",
        description="Vulcan Map — build and browse a grounded map of a codebase.",
    )
    p.add_argument("--version", action="version", version=f"vulcan-map {__version__}")
    _add_repo_args(p)

    sub = p.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Create vulcan_mind/ and install skill docs")
    _add_repo_args(p_init)
    p_init.add_argument("--project", default=None, help="Project name (default: repo directory name)")
    p_init.add_argument(
        "--agents", default=None,
        help="Comma-separated adapters (default: claude-code,codex,devin,agents-md)",
    )
    p_init.add_argument("--force", action="store_true", help="Overwrite an existing config")

    p_compile = sub.add_parser("compile", help="Run the compile pipeline and write _build/")
    _add_repo_args(p_compile)
    p_compile.add_argument("--strict", action="store_true", help="Treat warnings as errors")

    p_check = sub.add_parser("check", help="Validate without writing (the completion gate)")
    _add_repo_args(p_check)
    p_check.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    p_check.add_argument("--json", action="store_true", help="Emit the report as JSON")
    p_check.add_argument(
        "--proof", action="store_true",
        help="Print a quotable attestation of the gate result (required when reporting done)",
    )

    p_status = sub.add_parser(
        "status", help="Authoritative progress state — run this first when picking up a map"
    )
    _add_repo_args(p_status)
    p_status.add_argument("--json", action="store_true", help="Machine-readable output")

    p_scaffold = sub.add_parser(
        "scaffold", help="Generate nodes and doc skeletons for unmapped symbols (D11)"
    )
    _add_repo_args(p_scaffold)
    p_scaffold.add_argument("--dry-run", action="store_true", help="Show what would be created")

    p_find = sub.add_parser("find", help="Search already-mapped nodes by name, tag, path or prose")
    _add_repo_args(p_find)
    p_find.add_argument("query", help="Substring to look for")
    p_find.add_argument("--limit", type=int, default=40)

    p_flow = sub.add_parser("workflow", help="Cross-cutting workflow views (D12)")
    _add_repo_args(p_flow)
    p_flow.add_argument("action", choices=["list", "add"])
    p_flow.add_argument("name", nargs="?", help="Workflow chart id")
    p_flow.add_argument("--seed", action="append", default=[], help="Entry-point node id (repeatable)")
    p_flow.add_argument("--title", default=None)
    p_flow.add_argument("--why", default=None, help="Why these seeds define the workflow")
    p_flow.add_argument("--direction", choices=["downstream", "upstream", "both"], default="downstream")
    p_flow.add_argument("--depth", type=int, default=4)
    p_flow.add_argument("--force", action="store_true")

    p_wl = sub.add_parser("worklist", help="Durable progress ledger")
    _add_repo_args(p_wl)
    p_wl.add_argument("--build", action="store_true", help="Rebuild the ledger from disk")
    p_wl.add_argument("--next", type=int, metavar="N", help="Print the next N pending files")
    p_wl.add_argument("--remaining", action="store_true", help="Print the pending count only")

    p_region = sub.add_parser("region", help="Inspect or modify regions")
    _add_repo_args(p_region)
    p_region.add_argument("action", choices=["list", "show", "add"])
    p_region.add_argument("name", nargs="?", help="Region name (for show/add)")
    p_region.add_argument("--include", action="append", default=[], help="Include glob (repeatable)")
    p_region.add_argument("--exclude", action="append", default=[], help="Exclude glob (repeatable)")
    p_region.add_argument("--granularity", choices=["module", "file", "function"], default="module")
    p_region.add_argument("--description", default="")

    p_ui = sub.add_parser("ui", help="Open the node-graph UI")
    _add_repo_args(p_ui)
    p_ui.add_argument("--chart", default=None, help="Chart to open (default: master)")

    sub.add_parser("doctor", help="Check conda, environment and PATH shims")

    p_shim = sub.add_parser("install-shim", help="Install the cross-shell `vulcan` launcher")
    p_shim.add_argument("--path", action="store_true", help="Also add the shim dir to user PATH")
    p_shim.add_argument("--dry-run", action="store_true", help="Show what would be written")

    return p


def _force_utf8_output() -> None:
    """Windows consoles default to a legacy codepage that cannot encode the
    arrows and box characters used in findings; without this, printing a report
    raises UnicodeEncodeError instead of reporting the map's problems."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)

    from . import (
        cmd_check, cmd_compile, cmd_doctor, cmd_init, cmd_install_shim,
        cmd_region, cmd_scaffold, cmd_status, cmd_ui, cmd_workflow, cmd_worklist,
    )

    handlers = {
        "init": cmd_init.run,
        "compile": cmd_compile.run,
        "check": cmd_check.run,
        "status": cmd_status.run,
        "scaffold": cmd_scaffold.run,
        "find": cmd_workflow.run_find,
        "workflow": cmd_workflow.run_workflow,
        "worklist": cmd_worklist.run,
        "region": cmd_region.run,
        "ui": cmd_ui.run,
        "doctor": cmd_doctor.run,
        "install-shim": cmd_install_shim.run,
    }

    handler = handlers.get(args.command or "ui")
    try:
        return handler(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # surfaced as a clean message, not a traceback
        print(f"vulcan: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
