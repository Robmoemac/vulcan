---
id: grounding.registry.grounder_for
label: grounder_for
kind: function
source:
  file: src/vulcan_map/core/grounding/__init__.py
  symbol: grounder_for
  lines:
  - 26
  - 32
inputs:
- id: julia
  type: Grounder
  units: n/a
  required: true
  description: The Julia grounder, registered under .jl.
- id: python
  type: Grounder
  units: n/a
  required: true
  description: The Python grounder, registered under .py.
- id: regex
  type: Grounder
  units: n/a
  required: true
  description: The language-agnostic grounder, used as the default.
outputs:
- id: selected
  type: Grounder
  units: n/a
  description: The grounder the validator will use for one file.
tags:
- grounding
- registry
charts:
- master
origin: agent
---

# grounder_for

## Purpose
Selects which grounder handles a given file, either from the configured
`symbol_search` mode or by file extension.

## Model & Assumptions
- Extension is a sufficient proxy for language. A repository that uses a
  non-standard extension gets the default grounder, which still answers V6
  correctly if less precisely.
- An unrecognised explicit mode is not an error. `_BY_NAME.get(mode, _FALLBACK)`
  degrades to the default rather than raising, because a typo in configuration
  should not abort a whole validation pass.

## Design & Implementation
Module import builds two dictionaries. `_REGISTRY` maps each suffix declared in a
grounder's `suffixes` tuple to that instance, so registration is driven by the
grounder rather than by a separate table that could drift. `_BY_NAME` maps the
configuration strings `regex`, `julia`, and `python` to the same instances.

`grounder_for` returns the named grounder when `mode` is anything other than
`auto`, and otherwise looks up `Path(path).suffix`, defaulting to the shared
`RegexGrounder`. Instances are module-level singletons, so selection allocates
nothing.

## Interface (ICD)
<!-- vulcan:icd:begin -->
| Direction | Socket | Type | Units | Required | Description |
|---|---|---|---|---|---|
| in | `julia` | Grounder | n/a | yes | The Julia grounder, registered under .jl. |
| in | `python` | Grounder | n/a | yes | The Python grounder, registered under .py. |
| in | `regex` | Grounder | n/a | yes | The language-agnostic grounder, used as the default. |
| out | `selected` | Grounder | n/a | — | The grounder the validator will use for one file. |
<!-- vulcan:icd:end -->

## Connections
<!-- vulcan:connections:begin -->
**Upstream**

- [[grounding.julia.julia_grounder|JuliaGrounder]] · `grounder` → `julia` · dataflow · `src/vulcan_map/core/grounding/__init__.py:16-21`
- [[grounding.python.python_grounder|PythonGrounder]] · `grounder` → `python` · dataflow · `src/vulcan_map/core/grounding/__init__.py:16-22`
- [[grounding.regex.regex_grounder|RegexGrounder]] · `matcher` → `regex` · dataflow · `src/vulcan_map/core/grounding/__init__.py:13-20`

**Downstream**

- *none*
<!-- vulcan:connections:end -->

## Limitations
Because the grounders are shared singletons, any future grounder holding
per-file state would need its own instancing strategy. Extension matching is
case-sensitive, so a file named with an uppercase suffix receives the default
grounder rather than the language-specific one.

## Provenance
Mapped from `src/vulcan_map/core/grounding/__init__.py`.
