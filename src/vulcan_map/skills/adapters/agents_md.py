"""Generic AGENTS.md adapter — the shared path for three of the four baseline
targets (D7). Codex and Devin subclass this rather than duplicating it.
"""

from __future__ import annotations

from pathlib import Path

from .. import Skill
from .base import Adapter, splice_section, write_if_changed


def render_section(skills: list[Skill], *, heading: str = "Vulcan Map") -> str:
    parts: list[str] = [
        f"# {heading}",
        "",
        "This repository is mapped with Vulcan Map. The instructions below are the",
        "full skill set — follow them exactly when asked to map, chart, or deepen",
        "the map of this codebase.",
        "",
        "**The definition of done is `vulcan check --strict` exiting 0.** Nothing else.",
        "",
    ]
    for skill in skills:
        parts += [
            f"## Skill: `{skill.name}`",
            "",
            f"*{skill.description}*",
            "",
            skill.body.strip(),
            "",
        ]
    return "\n".join(parts)


class AgentsMdAdapter(Adapter):
    key = "agents-md"
    label = "Generic AGENTS.md"
    filename = "AGENTS.md"
    heading = "Vulcan Map"

    def install(self, repo_root: Path, skills: list[Skill]) -> list[Path]:
        path = repo_root / self.filename
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        merged = splice_section(existing, render_section(skills, heading=self.heading))
        return [path] if write_if_changed(path, merged) else []
