"""Adapter registry. Baseline set is fixed by D7."""

from __future__ import annotations

from .agents_md import AgentsMdAdapter
from .base import Adapter
from .claude_code import ClaudeCodeAdapter
from .codex import CodexAdapter
from .devin import DevinAdapter

#: D7 baseline. Cursor is deliberately absent.
ADAPTERS: dict[str, Adapter] = {
    a.key: a
    for a in (ClaudeCodeAdapter(), CodexAdapter(), DevinAdapter(), AgentsMdAdapter())
}

DEFAULT_KEYS: tuple[str, ...] = ("claude-code", "codex", "devin", "agents-md")


def get(keys: list[str] | None = None) -> list[Adapter]:
    selected = keys or list(DEFAULT_KEYS)
    unknown = [k for k in selected if k not in ADAPTERS]
    if unknown:
        known = ", ".join(sorted(ADAPTERS))
        raise KeyError(f"Unknown adapter(s): {', '.join(unknown)}. Known: {known}")
    return [ADAPTERS[k] for k in selected]


__all__ = ["Adapter", "ADAPTERS", "DEFAULT_KEYS", "get"]
