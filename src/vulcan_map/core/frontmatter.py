"""Node-document parsing: YAML frontmatter plus machine-owned marker blocks.

Generated regions are delimited so the compiler can rewrite them without ever
touching author prose (PLAN.md §7.2 step 9).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ICD_BLOCK = "icd"
CONNECTIONS_BLOCK = "connections"

_FM_RE = re.compile(r"\A---\r?\n(?P<fm>.*?)\r?\n---[ \t]*\r?\n?(?P<body>.*)\Z", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")
_FENCE_RE = re.compile(r"^(```|~~~)", re.MULTILINE)


def block_markers(name: str) -> tuple[str, str]:
    return f"<!-- vulcan:{name}:begin -->", f"<!-- vulcan:{name}:end -->"


class FrontmatterError(Exception):
    pass


@dataclass(slots=True)
class NodeDoc:
    path: Path
    meta: dict[str, Any]
    body: str
    raw: str

    @property
    def id(self) -> str | None:
        return self.meta.get("id")

    def block(self, name: str) -> str | None:
        """Current content of a generated block, or None if the block is absent."""
        begin, end = block_markers(name)
        i = self.body.find(begin)
        if i == -1:
            return None
        j = self.body.find(end, i)
        if j == -1:
            return None
        return self.body[i + len(begin) : j].strip("\n")

    def with_block(self, name: str, content: str) -> str:
        """Body with the named block's content replaced. Missing block → unchanged."""
        begin, end = block_markers(name)
        i = self.body.find(begin)
        if i == -1:
            return self.body
        j = self.body.find(end, i)
        if j == -1:
            return self.body
        return self.body[: i + len(begin)] + "\n" + content.strip("\n") + "\n" + self.body[j:]

    def prose(self) -> str:
        """Author-written text only: generated blocks and code fences removed.

        This is what the vagueness lint (V12) and word-count floor operate on, so
        that generated tables can never pad a stub doc past the threshold.
        """
        text = self.body
        for name in (ICD_BLOCK, CONNECTIONS_BLOCK):
            begin, end = block_markers(name)
            i = text.find(begin)
            if i == -1:
                continue
            j = text.find(end, i)
            if j == -1:
                continue
            text = text[:i] + text[j + len(end) :]

        parts = _FENCE_RE.split(text)
        # split() yields [before, fence, inside, fence, after, ...]; keep even slots
        kept = [p for k, p in enumerate(parts) if k % 4 == 0]
        return "\n".join(kept)

    def wikilinks(self) -> list[str]:
        return [m.group(1).strip() for m in _WIKILINK_RE.finditer(self.prose())]

    def word_count(self) -> int:
        text = re.sub(r"^#{1,6}\s.*$", "", self.prose(), flags=re.MULTILINE)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        return len([w for w in re.split(r"\s+", text) if w.strip()])


def parse(path: Path) -> NodeDoc:
    raw = path.read_text(encoding="utf-8")
    m = _FM_RE.match(raw)
    if not m:
        raise FrontmatterError(
            f"{path}: missing YAML frontmatter. A node doc must open with a '---' block."
        )
    try:
        meta = yaml.safe_load(m.group("fm")) or {}
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"{path}: invalid frontmatter YAML: {exc}") from exc
    if not isinstance(meta, dict):
        raise FrontmatterError(f"{path}: frontmatter must be a mapping.")
    return NodeDoc(path=path, meta=meta, body=m.group("body"), raw=raw)


def render(meta: dict[str, Any], body: str) -> str:
    fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"---\n{fm}\n---\n{body}"
