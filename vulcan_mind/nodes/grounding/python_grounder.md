---
id: grounding.python.python_grounder
label: PythonGrounder
kind: struct
source:
  file: src/vulcan_map/core/grounding/python.py
  symbol: PythonGrounder
  lines:
  - 11
  - 49
inputs:
- id: interface
  type: Grounder
  units: n/a
  required: true
  description: The abstract base contract this class implements.
- id: fallback
  type: Grounder
  units: n/a
  required: true
  description: The RegexGrounder used when the file will not parse.
outputs:
- id: grounder
  type: Grounder
  units: n/a
  description: Registered under the .py suffix in the registry.
tags:
- grounding
- python
charts:
- master
origin: agent
---

# PythonGrounder

## Purpose
Grounds Python symbols using the standard library's abstract syntax tree, giving
a genuine definition check rather than a textual one.

## Model & Assumptions
- The stdlib `ast` module costs no dependency, which is why Python gets real
  parsing while Julia does not.
- A file that fails to parse is not a grounding failure. Syntax errors happen in
  work-in-progress code, and refusing to ground the whole file would produce V6
  errors unrelated to the map's correctness, so the fallback handles it.
- Definitions counted are functions, async functions, classes, and any name bound
  in a store context, which covers module-level constants and assignments.

## Design & Implementation
`_defined_names` parses the source and walks every node, collecting `name` from
`FunctionDef`, `AsyncFunctionDef`, and `ClassDef`, plus `id` from any `Name` in a
`Store` context. It returns `None` — distinct from an empty set — when parsing
raises `SyntaxError`, so the caller can tell "parsed, found nothing" apart from
"could not parse".

`contains_symbol` consults that set and defers to the fallback when it is `None`
or the symbol is absent. `symbol_line` re-parses and returns the `lineno` of the
matching definition, which is exact rather than heuristic.

## Interface (ICD)
<!-- vulcan:icd:begin -->
| Direction | Socket | Type | Units | Required | Description |
|---|---|---|---|---|---|
| in | `interface` | Grounder | n/a | yes | The abstract base contract this class implements. |
| in | `fallback` | Grounder | n/a | yes | The RegexGrounder used when the file will not parse. |
| out | `grounder` | Grounder | n/a | — | Registered under the .py suffix in the registry. |
<!-- vulcan:icd:end -->

## Connections
<!-- vulcan:connections:begin -->
**Upstream**

- [[grounding.base.grounder|Grounder]] · `interface` → `interface` · reads · `src/vulcan_map/core/grounding/python.py:11-11`
- [[grounding.regex.regex_grounder|RegexGrounder]] · `matcher` → `fallback` · dataflow · `src/vulcan_map/core/grounding/python.py:14-15`

**Downstream**

- `grounder` → [[grounding.registry.grounder_for|grounder_for]] · `python` · dataflow · `src/vulcan_map/core/grounding/__init__.py:16-22`
<!-- vulcan:connections:end -->

## Limitations
Both `contains_symbol` and `symbol_line` parse the file independently, so
grounding a node costs up to two parses of the same source. Names bound only by
tuple unpacking inside comprehensions, or created dynamically through `setattr`
and similar, are not collected and fall through to the textual fallback.

## Provenance
Mapped from `src/vulcan_map/core/grounding/python.py`.
