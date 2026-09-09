"""Repo-root discovery and the vulcan_mind directory layout (PLAN.md §4, §12.3)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

MIND_DIRNAME = "vulcan_mind"


class RepoNotFound(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Mind:
    """Paths inside a target repo's vulcan_mind/ directory."""

    repo_root: Path

    @property
    def root(self) -> Path:
        return self.repo_root / MIND_DIRNAME

    @property
    def config_path(self) -> Path:
        return self.root / "vulcan.config.yaml"

    @property
    def graph_dir(self) -> Path:
        return self.root / "graph"

    @property
    def subcharts_dir(self) -> Path:
        return self.graph_dir / "subcharts"

    @property
    def nodes_dir(self) -> Path:
        return self.root / "nodes"

    @property
    def build_dir(self) -> Path:
        return self.root / "_build"

    @property
    def templates_dir(self) -> Path:
        return self.root / "templates"

    @property
    def master_path(self) -> Path:
        return self.graph_dir / "master.graph.json"

    @property
    def pending_path(self) -> Path:
        """Queue of UI edits awaiting the next compile.

        Deliberately *not* under _build/: these are authored intent, not
        generated output, and must survive anything that clears the build dir.
        """
        return self.root / "pending.json"

    @property
    def worklist_path(self) -> Path:
        return self.build_dir / "worklist.json"

    @property
    def index_path(self) -> Path:
        return self.build_dir / "index.json"

    @property
    def report_path(self) -> Path:
        return self.build_dir / "validation-report.json"

    def resolved_path(self, chart_id: str) -> Path:
        return self.build_dir / f"{chart_id}.resolved.json"

    def exists(self) -> bool:
        return self.root.is_dir()

    def chart_paths(self) -> list[Path]:
        """Master first, then subcharts sorted by name — deterministic ordering."""
        paths: list[Path] = []
        if self.master_path.exists():
            paths.append(self.master_path)
        if self.subcharts_dir.is_dir():
            paths.extend(sorted(self.subcharts_dir.glob("*.graph.json")))
        return paths

    def node_doc_paths(self) -> list[Path]:
        if not self.nodes_dir.is_dir():
            return []
        return sorted(self.nodes_dir.rglob("*.md"))

    def rel(self, path: Path) -> str:
        """Path relative to vulcan_mind/, POSIX-style — the form stored in JSON."""
        return path.relative_to(self.root).as_posix()


def find_repo_root(start: Path | None = None, *, here: bool = False) -> Path:
    """Resolve the repo this invocation targets (PLAN.md §12.3).

    Walks up from `start` looking for vulcan_mind/, then for .git/. The nearest
    match wins, so a nested repo scopes to itself rather than its parent.
    """
    start = (start or Path.cwd()).resolve()
    if here:
        return start

    for parent in (start, *start.parents):
        if (parent / MIND_DIRNAME).is_dir():
            return parent
    for parent in (start, *start.parents):
        if (parent / ".git").exists():
            return parent

    raise RepoNotFound(
        f"No vulcan_mind/ or .git/ found at or above {start}.\n"
        "Run `vulcan init` inside a repository, or pass --repo PATH."
    )


def git_commit(repo_root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None
