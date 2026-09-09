"""Adapter interface: write the skill set where a given agent will look for it."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .. import Skill

BEGIN_MARK = "<!-- vulcan-map:begin -->"
END_MARK = "<!-- vulcan-map:end -->"


class Adapter(ABC):
    #: Stable key used by `vulcan init --agents ...`.
    key: str = ""
    #: Human-facing name for reporting.
    label: str = ""

    @abstractmethod
    def install(self, repo_root: Path, skills: list[Skill]) -> list[Path]:
        """Write skill files; return the paths written."""


def write_if_changed(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def splice_section(existing: str, section: str) -> str:
    """Insert or replace the vulcan-map block in a shared file.

    Anything the user wrote outside the markers is preserved byte-for-byte —
    AGENTS.md is usually not ours alone.
    """
    block = f"{BEGIN_MARK}\n{section.strip()}\n{END_MARK}"
    i = existing.find(BEGIN_MARK)
    j = existing.find(END_MARK)
    if i != -1 and j != -1 and j > i:
        return existing[:i] + block + existing[j + len(END_MARK) :]
    prefix = existing.rstrip("\n")
    return f"{prefix}\n\n{block}\n" if prefix else f"{block}\n"
