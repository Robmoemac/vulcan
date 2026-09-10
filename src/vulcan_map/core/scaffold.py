"""Generate the nodes and doc skeletons that D11 requires.

Per-symbol granularity means a real map has thousands of nodes. Their *structure*
— id, label, kind, source file, declaration line, socket stubs, chart membership
— is fully derivable from the source, so an agent should not be hand-typing it;
that work is mechanical and error-prone by hand.

What is deliberately NOT generated is the prose. A scaffolded doc has empty
Purpose and Design sections and therefore fails V12's word floor, so the gate
keeps failing until someone actually reads the code and writes it. Scaffolding
gets you a correct skeleton, never a false "done".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import _match_any
from .grounding import grounder_for
from .model import Node
from .repo import Mind
from .workspace import Workspace

_ID_SAFE = str.maketrans({"!": "", "?": "", "-": "_", ".": "_"})

DOC_TEMPLATE = """---
{frontmatter}---

# {label}

## Purpose

## Design & Implementation

## Interface (ICD)
<!-- vulcan:icd:begin -->
<!-- vulcan:icd:end -->

## Connections
<!-- vulcan:connections:begin -->
<!-- vulcan:connections:end -->

## Limitations

## Provenance
Mapped from `{file}` line {line}.
"""


@dataclass(slots=True)
class ScaffoldPlan:
    """What scaffolding would create, before anything is written."""

    nodes_by_chart: dict[str, list[dict]] = field(default_factory=dict)
    docs: dict[Path, str] = field(default_factory=dict)

    @property
    def node_count(self) -> int:
        return sum(len(v) for v in self.nodes_by_chart.values())


def node_id_for(prefix: str, file: str, symbol: str) -> str:
    """A globally unique, pattern-valid id.

    The file stem is included because the same symbol name recurs across files,
    and node ids must be unique map-wide (V2).
    """
    stem = Path(file).stem.lower().translate(_ID_SAFE)
    return f"{prefix}.{stem}_{symbol.lower().translate(_ID_SAFE)}"


def _owning_module(node_list: list[Node], rel: str) -> Node | None:
    """The module node whose `covers` claims this file."""
    for n in node_list:
        if n.is_covering and n.covers and _match_any(rel, n.covers):
            return n
    return None


def plan(ws: Workspace) -> ScaffoldPlan:
    """Everything D11 requires that does not yet exist."""
    nodes = ws.all_nodes()
    mapped: dict[str, set[str]] = {}
    for n in nodes:
        if n.source.file and n.source.symbol and not n.is_covering:
            mapped.setdefault(n.source.file, set()).add(n.source.symbol)

    existing_ids = {n.id for n in nodes}
    out = ScaffoldPlan()

    for rel in ws.in_scope_files():
        abs_path = ws.repo_root / rel
        if not abs_path.is_file():
            continue
        grounder = grounder_for(abs_path, ws.config.symbol_search)
        if not grounder.enumerates:
            continue
        try:
            text = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        module = _owning_module(nodes, rel)
        if module is None:
            continue
        chart_id = module.id.split(".", 1)[-1]
        prefix = chart_id.translate(_ID_SAFE)

        for decl in grounder.declarations(text):
            if decl.symbol in mapped.get(rel, set()):
                continue
            nid = node_id_for(prefix, rel, decl.symbol)
            if nid in existing_ids:
                continue
            existing_ids.add(nid)

            doc_rel = f"nodes/{chart_id}/{nid.split('.', 1)[1]}.md"
            out.nodes_by_chart.setdefault(chart_id, []).append({
                "id": nid,
                "label": decl.symbol,
                "kind": decl.kind,
                "doc": doc_rel,
                "source": {"file": rel, "symbol": decl.symbol,
                           "lines": [decl.line, decl.line]},
                "expands": module.id,
                "origin": "agent",
            })
            out.docs[ws.mind.root / doc_rel] = _render_doc(
                nid, decl.symbol, decl.kind, rel, decl.line, chart_id
            )
    return out


def _render_doc(nid: str, symbol: str, kind: str, file: str, line: int, chart: str) -> str:
    import yaml

    meta = {
        "id": nid,
        "label": symbol,
        "kind": kind,
        "source": {"file": file, "symbol": symbol, "lines": [line, line]},
        "inputs": [{
            "id": "module_api", "type": "Module", "units": "n/a", "required": False,
            "description": "Re-exported through the owning module's public surface.",
        }],
        "outputs": [{
            "id": "result", "type": "Any", "units": "n/a",
            "description": "Value produced by this symbol.",
        }],
        "tags": [chart],
        "charts": [chart],
        "origin": "agent",
    }
    fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    return DOC_TEMPLATE.format(frontmatter=fm, label=symbol, file=file, line=line)


def apply(ws: Workspace, plan_: ScaffoldPlan) -> tuple[int, int]:
    """Write the planned nodes and docs. Returns (nodes, docs) written."""
    mind: Mind = ws.mind

    docs_written = 0
    for path, text in plan_.docs.items():
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        docs_written += 1

    nodes_written = 0
    for chart_id, new_nodes in plan_.nodes_by_chart.items():
        path = mind.subcharts_dir / f"{chart_id}.graph.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        have = {n["id"] for n in data.get("local_nodes", [])}
        added = [n for n in new_nodes if n["id"] not in have]
        if not added:
            continue
        data.setdefault("local_nodes", []).extend(added)
        data["local_nodes"].sort(key=lambda n: n["id"])
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
        nodes_written += len(added)

    return nodes_written, docs_written
