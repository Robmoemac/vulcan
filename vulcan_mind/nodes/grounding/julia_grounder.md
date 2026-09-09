---
id: grounding.julia.julia_grounder
label: JuliaGrounder
kind: struct
source:
  file: src/vulcan_map/core/grounding/julia.py
  symbol: JuliaGrounder
  lines:
  - 30
  - 50
inputs:
- id: interface
  type: Grounder
  units: n/a
  required: true
  description: The abstract base contract this class implements.
- id: patterns
  type: list
  units: n/a
  required: true
  description: Declaration patterns from _decl_patterns.
- id: fallback
  type: Grounder
  units: n/a
  required: true
  description: The RegexGrounder used when no declaration form matches.
outputs:
- id: grounder
  type: Grounder
  units: n/a
  description: Registered under the .jl suffix in the registry.
tags:
- grounding
- julia
charts:
- master
origin: agent
---

# JuliaGrounder

## Purpose
Grounds Julia symbols, preferring a real declaration match and falling back to
plain occurrence when no declaration form is recognised.

## Model & Assumptions
- Declaration-aware matching is a refinement, not a gate. A symbol that is
  re-exported or produced by metaprogramming still grounds, because failing it
  would produce false V6 errors on valid maps.
- This class stays regex-based by decision, not oversight: no Julia parser is
  installable from conda-forge under the project's conda-only constraint, and V6
  requires only occurrence.

## Design & Implementation
`__init__` constructs a private `RegexGrounder` as the fallback.
`contains_symbol` first tests every pattern from `_decl_patterns`, returning
immediately on the first hit, then defers to the fallback's whole-word search.

`symbol_line` is the more valuable override: it walks the declaration patterns in
order and converts a match offset to a one-based line number with
`text.count("\n", 0, m.start()) + 1`. Because the patterns are ordered from most
to least specific, the reported line is the declaration rather than the first
incidental mention, which is what makes rule V17's staleness check meaningful for
Julia sources.

## Interface (ICD)
<!-- vulcan:icd:begin -->
| Direction | Socket | Type | Units | Required | Description |
|---|---|---|---|---|---|
| in | `interface` | Grounder | n/a | yes | The abstract base contract this class implements. |
| in | `patterns` | list | n/a | yes | Declaration patterns from _decl_patterns. |
| in | `fallback` | Grounder | n/a | yes | The RegexGrounder used when no declaration form matches. |
| out | `grounder` | Grounder | n/a | — | Registered under the .jl suffix in the registry. |
<!-- vulcan:icd:end -->

## Connections
<!-- vulcan:connections:begin -->
**Upstream**

- [[grounding.base.grounder|Grounder]] · `interface` → `interface` · reads · `src/vulcan_map/core/grounding/julia.py:30-30`
- [[grounding.julia.decl_patterns|_decl_patterns]] · `patterns` → `patterns` · dataflow · `src/vulcan_map/core/grounding/julia.py:39-40`
- [[grounding.regex.regex_grounder|RegexGrounder]] · `matcher` → `fallback` · dataflow · `src/vulcan_map/core/grounding/julia.py:33-34`

**Downstream**

- `grounder` → [[grounding.registry.grounder_for|grounder_for]] · `julia` · dataflow · `src/vulcan_map/core/grounding/__init__.py:16-21`
<!-- vulcan:connections:end -->

## Limitations
Inherits every weakness of the fallback whenever no declaration matches, so a
symbol mentioned only in a comment still grounds. Multiple methods of the same
generic function all match the first pattern, so `symbol_line` reports the first
method rather than the one the map means.

## Provenance
Mapped from `src/vulcan_map/core/grounding/julia.py`.
