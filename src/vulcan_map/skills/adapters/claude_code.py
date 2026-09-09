"""Claude Code adapter: .claude/skills/<name>/SKILL.md with YAML frontmatter."""

from __future__ import annotations

from pathlib import Path

from .. import Skill
from .base import Adapter, write_if_changed


class ClaudeCodeAdapter(Adapter):
    key = "claude-code"
    label = "Claude Code"

    def install(self, repo_root: Path, skills: list[Skill]) -> list[Path]:
        written: list[Path] = []
        for skill in skills:
            path = repo_root / ".claude" / "skills" / skill.name / "SKILL.md"
            if write_if_changed(path, skill.with_frontmatter()):
                written.append(path)
        return written
