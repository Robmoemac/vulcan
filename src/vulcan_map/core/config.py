"""Config loading and region resolution (PLAN.md §5)."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from .schemas import validate_against

DEFAULT_BANNED_PHRASES: tuple[str, ...] = (
    "a helper function",
    "various",
    "and so on",
    "etc.",
    "some kind of",
    "handles the logic",
    "TODO",
    "TBD",
)

SOURCE_SUFFIXES: tuple[str, ...] = (
    ".py", ".jl", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java",
    ".c", ".h", ".cc", ".cpp", ".hpp", ".rb", ".m", ".f90", ".jl.in",
)

_ALWAYS_EXCLUDE = (
    "**/.git/**",
    "**/vulcan_mind/**",
    "**/node_modules/**",
    "**/__pycache__/**",
    "**/.venv/**",
)


class ConfigError(Exception):
    pass


def _match_any(rel_posix: str, patterns: Iterable[str]) -> bool:
    """Glob match with `**` treated as spanning directories.

    fnmatch's `*` already crosses `/`, which makes `src/**` behave as intended
    here; the explicit `/**` -> `` rewrite makes `src/**` also match `src` itself.
    """
    for pat in patterns:
        if fnmatch.fnmatch(rel_posix, pat):
            return True
        if pat.endswith("/**") and fnmatch.fnmatch(rel_posix, pat[:-3]):
            return True
    return False


@dataclass(frozen=True, slots=True)
class Region:
    name: str
    include: tuple[str, ...]
    exclude: tuple[str, ...] = ()
    granularity: str = "module"
    description: str = ""

    def matches(self, rel_posix: str) -> bool:
        if _match_any(rel_posix, _ALWAYS_EXCLUDE):
            return False
        if self.exclude and _match_any(rel_posix, self.exclude):
            return False
        return _match_any(rel_posix, self.include)


@dataclass(slots=True)
class Config:
    project: str
    regions: dict[str, Region]
    default_region: str = "all"
    languages: tuple[str, ...] = ()
    require_symbol_match: bool = True
    symbol_search: str = "auto"
    banned_phrases: tuple[str, ...] = DEFAULT_BANNED_PHRASES
    min_doc_words: int = 120
    min_doc_words_symbol: int = 40
    require_every_in_scope_file_mapped: bool = True
    require_subchart_per_module: bool = True
    require_function_node_per_file: bool = True
    require_node_per_symbol: bool = True
    # D13: a sheet that renders more than this many nodes is unreadable and
    # fails V20; compile clusters it into group nodes with nested sheets.
    max_nodes_per_sheet: int = 40
    # Clusters smaller than this are merged into one "small files" group.
    cluster_min_group: int = 3
    path: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def region(self, name: str | None = None) -> Region:
        key = name or self.default_region
        if key not in self.regions:
            known = ", ".join(sorted(self.regions)) or "(none)"
            raise ConfigError(f"Unknown region {key!r}. Defined regions: {known}")
        return self.regions[key]

    def in_scope_files(self, repo_root: Path, region: Region) -> list[str]:
        """Every source file the region selects, as repo-relative POSIX paths."""
        found: list[str] = []
        for path in repo_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in SOURCE_SUFFIXES:
                continue
            rel = path.relative_to(repo_root).as_posix()
            if region.matches(rel):
                found.append(rel)
        return sorted(found)


def load_config(path: Path) -> Config:
    if not path.exists():
        raise ConfigError(
            f"No config at {path}. Run `vulcan init` to create vulcan_mind/."
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc

    errors = validate_against("config.schema.json", raw)
    if errors:
        joined = "\n  ".join(errors)
        raise ConfigError(f"{path}: config does not validate:\n  {joined}")

    regions = {
        name: Region(
            name=name,
            include=tuple(body["include"]),
            exclude=tuple(body.get("exclude", ())),
            granularity=body.get("granularity", "module"),
            description=body.get("description", ""),
        )
        for name, body in raw["regions"].items()
    }

    grounding = raw.get("grounding", {})
    lint = raw.get("lint", {})
    coverage = raw.get("coverage", {})

    cfg = Config(
        project=raw["project"],
        regions=regions,
        default_region=raw.get("default_region", next(iter(regions))),
        languages=tuple(raw.get("languages", ())),
        require_symbol_match=grounding.get("require_symbol_match", True),
        symbol_search=grounding.get("symbol_search", "auto"),
        banned_phrases=tuple(lint.get("banned_phrases", DEFAULT_BANNED_PHRASES)),
        min_doc_words=lint.get("min_doc_words", 120),
        min_doc_words_symbol=lint.get("min_doc_words_symbol", 40),
        require_every_in_scope_file_mapped=coverage.get(
            "require_every_in_scope_file_mapped", True
        ),
        require_subchart_per_module=coverage.get("require_subchart_per_module", True),
        require_function_node_per_file=coverage.get(
            "require_function_node_per_file", True
        ),
        require_node_per_symbol=coverage.get("require_node_per_symbol", True),
        max_nodes_per_sheet=coverage.get("max_nodes_per_sheet", 40),
        cluster_min_group=coverage.get("cluster_min_group", 3),
        path=path,
        raw=raw,
    )
    if cfg.default_region not in cfg.regions:
        raise ConfigError(
            f"{path}: default_region {cfg.default_region!r} is not defined under regions:"
        )
    return cfg
