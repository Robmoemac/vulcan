"""Codex adapter.

Codex reads AGENTS.md at the repo root, so this is a thin wrapper over the shared
implementation rather than a parallel code path (D7).
"""

from __future__ import annotations

from pathlib import Path

from .. import Skill
from .agents_md import AgentsMdAdapter


class CodexAdapter(AgentsMdAdapter):
    key = "codex"
    label = "Codex (OpenAI)"

    def install(self, repo_root: Path, skills: list[Skill]) -> list[Path]:
        # Identical target to the generic adapter; installing both is a no-op for
        # the second one because the section is spliced by marker, not appended.
        return super().install(repo_root, skills)
