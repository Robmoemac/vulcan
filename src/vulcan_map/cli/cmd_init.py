"""`vulcan init` — scaffold vulcan_mind/ and install skill docs."""

from __future__ import annotations

import argparse
import json
from importlib import resources
from pathlib import Path

from .. import SCHEMA_VERSION
from ..core.repo import Mind, find_repo_root
from ..skills import all_skills
from ..skills import adapters as adapters_mod
from ._common import colour, GREEN, DIM

_LANG_BY_SUFFIX = {".py": "python", ".jl": "julia", ".ts": "typescript",
                   ".js": "javascript", ".rs": "rust", ".go": "go", ".java": "java"}


def _detect_languages(repo_root: Path) -> list[str]:
    counts: dict[str, int] = {}
    for path in repo_root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        lang = _LANG_BY_SUFFIX.get(path.suffix)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    return [k for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:3]]


def _template(name: str) -> str:
    return resources.files("vulcan_map.templates").joinpath(name).read_text(encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo).resolve() if args.repo else find_repo_root(here=args.here)
    mind = Mind(repo_root)
    project = args.project or repo_root.name

    for d in (mind.graph_dir, mind.subcharts_dir, mind.nodes_dir, mind.build_dir, mind.templates_dir):
        d.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []

    if not mind.config_path.exists() or args.force:
        langs = _detect_languages(repo_root)
        text = (
            _template("vulcan.config.yaml")
            .replace("__PROJECT__", project)
            .replace("__LANGUAGES__", ", ".join(langs))
        )
        mind.config_path.write_text(text, encoding="utf-8", newline="\n")
        created.append(mind.config_path)

    node_tmpl = mind.templates_dir / "node.md"
    if not node_tmpl.exists() or args.force:
        node_tmpl.write_text(_template("node.md"), encoding="utf-8", newline="\n")
        created.append(node_tmpl)

    if not mind.master_path.exists():
        master = {
            "schema_version": SCHEMA_VERSION,
            "chart_id": "master",
            "chart_kind": "master",
            "title": f"{project} — Master Flow",
            "region": "all",
            "provenance": {"generator": "vulcan init"},
            "nodes": [],
            "edges": [],
        }
        mind.master_path.write_text(
            json.dumps(master, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        created.append(mind.master_path)

    build_ignore = mind.build_dir / ".gitignore"
    if not build_ignore.exists():
        build_ignore.write_text("*\n", encoding="utf-8", newline="\n")
        created.append(build_ignore)

    keys = [k.strip() for k in args.agents.split(",")] if args.agents else None
    skills = list(all_skills())
    installed: list[Path] = []
    for adapter in adapters_mod.get(keys):
        installed.extend(adapter.install(repo_root, skills))

    print(colour(f"Initialised vulcan_mind/ in {repo_root}", GREEN))
    for p in created:
        print(f"  created  {p.relative_to(repo_root).as_posix()}")
    for p in sorted(set(installed)):
        print(f"  skill    {p.relative_to(repo_root).as_posix()}")

    print()
    print(colour("vulcan_mind/ is meant to be committed (D4); _build/ is ignored.", DIM))
    print("Next: run the `vulcan-map` skill with your coding agent, or `vulcan check`.")
    return 0
