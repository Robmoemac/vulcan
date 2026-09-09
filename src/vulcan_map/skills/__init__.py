"""Skill document loading and `{{include}}` resolution.

Includes are resolved at install time so emitted files are self-contained — no
agent runtime resolves includes (PLAN.md §9.4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from typing import Iterator

import yaml

_INCLUDE_RE = re.compile(r"^\{\{include\s+(?P<path>[^}]+?)\s*\}\}\s*$", re.MULTILINE)
_FM_RE = re.compile(r"\A---\r?\n(?P<fm>.*?)\r?\n---[ \t]*\r?\n(?P<body>.*)\Z", re.DOTALL)

#: Skill directory name -> the agent-facing skill name.
SKILLS: dict[str, str] = {
    "master": "vulcan-map",
    "subchart": "vulcan-subchart",
    "augment": "vulcan-augment",
}


@dataclass(slots=True)
class Skill:
    key: str
    name: str
    description: str
    body: str

    @property
    def frontmatter(self) -> str:
        meta = {"name": self.name, "description": self.description}
        return yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=10_000).rstrip("\n")

    def with_frontmatter(self) -> str:
        return f"---\n{self.frontmatter}\n---\n\n{self.body.strip()}\n"


def _read(relpath: str) -> str:
    parts = relpath.strip().split("/")
    ref = resources.files("vulcan_map.skills")
    for part in parts:
        ref = ref.joinpath(part)
    return ref.read_text(encoding="utf-8")


def _resolve_includes(text: str, depth: int = 0) -> str:
    if depth > 4:
        raise RecursionError("include nesting too deep in skill documents")

    def sub(m: re.Match[str]) -> str:
        return _resolve_includes(_read(m.group("path")).strip(), depth + 1)

    return _INCLUDE_RE.sub(sub, text)


def load_skill(key: str) -> Skill:
    raw = _read(f"{key}/SKILL.md")
    m = _FM_RE.match(raw)
    if not m:
        raise ValueError(f"skill {key!r} is missing frontmatter")
    meta = yaml.safe_load(m.group("fm")) or {}
    return Skill(
        key=key,
        name=meta["name"],
        description=meta["description"],
        body=_resolve_includes(m.group("body")),
    )


def all_skills() -> Iterator[Skill]:
    for key in SKILLS:
        yield load_skill(key)
