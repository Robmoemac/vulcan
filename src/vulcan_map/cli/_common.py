"""Shared CLI helpers."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..core.repo import Mind, find_repo_root


def resolve_repo(args: argparse.Namespace) -> Path:
    if getattr(args, "repo", None):
        return Path(args.repo).resolve()
    return find_repo_root(here=getattr(args, "here", False))


def resolve_mind(args: argparse.Namespace) -> Mind:
    mind = Mind(resolve_repo(args))
    if not mind.exists():
        raise SystemExit(
            f"No vulcan_mind/ under {mind.repo_root}.\nRun `vulcan init` first."
        )
    return mind


GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"


def colour(text: str, code: str) -> str:
    import os
    import sys

    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return text
    return f"{code}{text}{RESET}"
