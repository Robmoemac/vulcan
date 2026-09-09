"""Devin adapter.

PLAN.md §14.3 records this as a fact to verify rather than a design decision:
the exact repo-level instruction file Devin reads was not confirmed at design
time. Implemented on the best available judgement — AGENTS.md is the emerging
cross-agent convention and the safest single target — with a secondary copy at
.devin/vulcan-map.md so the content is discoverable either way.

If verification shows Devin reads only one of these, delete the other; the skill
content itself is unaffected.
"""

from __future__ import annotations

from pathlib import Path

from .. import Skill
from .agents_md import AgentsMdAdapter, render_section
from .base import write_if_changed


class DevinAdapter(AgentsMdAdapter):
    key = "devin"
    label = "Devin (Cognition)"

    def install(self, repo_root: Path, skills: list[Skill]) -> list[Path]:
        written = list(super().install(repo_root, skills))
        secondary = repo_root / ".devin" / "vulcan-map.md"
        text = render_section(skills, heading="Vulcan Map") + "\n"
        if write_if_changed(secondary, text):
            written.append(secondary)
        return written
