"""The durable progress ledger (PLAN.md P4).

Long mapping runs exceed any agent's context window. Progress therefore lives on
disk, not in the agent's head: running out of context becomes a resumable
interruption rather than a silent early stop.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import _match_any
from .workspace import Workspace


def build_worklist(ws: Workspace) -> dict[str, Any]:
    in_scope = ws.in_scope_files()
    nodes = ws.all_nodes()

    direct: dict[str, list[str]] = {}
    for n in nodes:
        if n.source.file:
            direct.setdefault(n.source.file, []).append(n.id)

    covering = [n for n in nodes if n.is_covering and n.covers]

    items: list[dict[str, Any]] = []
    for rel in in_scope:
        node_ids = sorted(direct.get(rel, []))
        covered_by = sorted(n.id for n in covering if _match_any(rel, n.covers))
        if node_ids:
            status = "mapped"
        elif covered_by:
            status = "covered"
        else:
            status = "pending"
        items.append(
            {
                "file": rel,
                "status": status,
                "nodes": node_ids,
                "covered_by": covered_by,
            }
        )

    counts = {
        "total": len(items),
        "mapped": sum(1 for i in items if i["status"] == "mapped"),
        "covered": sum(1 for i in items if i["status"] == "covered"),
        "pending": sum(1 for i in items if i["status"] == "pending"),
    }
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "region": ws.region.name,
        "granularity": ws.region.granularity,
        "counts": counts,
        "remaining": counts["pending"],
        "items": items,
    }


def pending(worklist: dict[str, Any], limit: int | None = None) -> list[str]:
    files = [i["file"] for i in worklist.get("items", []) if i["status"] == "pending"]
    return files[:limit] if limit else files
