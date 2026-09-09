---
id: grounding.julia.decl_patterns
label: _decl_patterns
kind: function
source:
  file: src/vulcan_map/core/grounding/julia.py
  symbol: _decl_patterns
  lines:
  - 15
  - 28
inputs:
- id: symbol
  type: str
  units: n/a
  required: true
  description: The Julia identifier whose declaration forms are being sought.
outputs:
- id: patterns
  type: list
  units: n/a
  description: Compiled multiline patterns, one per Julia declaration form.
tags:
- grounding
- julia
charts:
- master
origin: agent
---

# _decl_patterns

## Purpose
Builds the set of regular expressions that recognise a Julia declaration of a
given symbol, so the Julia grounder can distinguish a definition from an
incidental mention.

## Model & Assumptions
- Declarations begin at the start of a line, modulo leading whitespace. Every
  pattern is anchored with `^\s*` under `re.MULTILINE`.
- The nine forms covered are: `function f(`, `function Mod.f(`, the short form
  `f(...) =`, `struct`, `mutable struct`, `abstract type`, `primitive type`,
  `macro`, `const`, and `module`.
- Symbols defined by metaprogramming (`@eval`, generated code) are not matched by
  any pattern, which is why the caller falls back to plain occurrence.

## Design & Implementation
The symbol is passed through `re.escape` before interpolation, so identifiers
containing regex metacharacters — common in Julia, where `!` and `?` are legal in
names — are matched literally. Each pattern is compiled with `re.MULTILINE` so
the `^` anchor applies per line rather than once per file.

The short-form pattern uses a non-greedy `.*?` between the parentheses so that a
single-line definition with nested parentheses terminates at the first `=`
following the argument list rather than at a later one.

## Interface (ICD)
<!-- vulcan:icd:begin -->
| Direction | Socket | Type | Units | Required | Description |
|---|---|---|---|---|---|
| in | `symbol` | str | n/a | yes | The Julia identifier whose declaration forms are being sought. |
| out | `patterns` | list | n/a | — | Compiled multiline patterns, one per Julia declaration form. |
<!-- vulcan:icd:end -->

## Connections
<!-- vulcan:connections:begin -->
**Upstream**

- *none*

**Downstream**

- `patterns` → [[grounding.julia.julia_grounder|JuliaGrounder]] · `patterns` · dataflow · `src/vulcan_map/core/grounding/julia.py:39-40`
<!-- vulcan:connections:end -->

## Limitations
Patterns are rebuilt on every call rather than cached, so a validation pass over
many Julia nodes recompiles the same nine expressions repeatedly. Multi-line
function signatures whose name and opening parenthesis are separated by a newline
are not matched. Neither limitation causes a false failure, because the caller
falls back to occurrence matching.

## Provenance
Mapped from `src/vulcan_map/core/grounding/julia.py`.
