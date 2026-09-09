---
id: grounding.base.grounder
label: Grounder
kind: struct
source:
  file: src/vulcan_map/core/grounding/base.py
  symbol: Grounder
  lines:
  - 14
  - 34
inputs: []
outputs:
- id: interface
  type: ABC
  units: n/a
  description: The abstract contract every concrete grounder implements.
tags:
- grounding
- interface
charts:
- master
origin: agent
---

# Grounder

## Purpose
Defines the contract that every language-specific grounder implements, and which
rule V6 depends on: given a file and a symbol name, decide whether that symbol
actually occurs in that file.

## Model & Assumptions
- Grounders answer **occurrence**, not semantics. They do not resolve scope,
  imports, or overloads, and they do not attempt to prove that the symbol at the
  cited location is the one the map means.
- Occurrence is sufficient for V6, whose claim is only that a mapped identifier
  is not invented.
- Files are decodable as UTF-8; `check` passes `errors="replace"` so that binary
  or mis-encoded content degrades to a failed match rather than an exception.

## Design & Implementation
`Grounder` is an `ABC` with one abstract method, `contains_symbol`, and two
concrete ones. `symbol_line` provides a default line lookup by scanning for the
first line containing the symbol, which subclasses override with declaration-aware
searches. `check` is the entry point used by the validator: it reads the file
from disk and delegates to `contains_symbol`, returning `False` on `OSError` so
an unreadable file is a grounding failure rather than a crash.

The `suffixes` class attribute is the registration key used by the registry in
`grounder_for`.

## Interface (ICD)
<!-- vulcan:icd:begin -->
| Direction | Socket | Type | Units | Required | Description |
|---|---|---|---|---|---|
| out | `interface` | ABC | n/a | — | The abstract contract every concrete grounder implements. |
<!-- vulcan:icd:end -->

## Connections
<!-- vulcan:connections:begin -->
**Upstream**

- *none*

**Downstream**

- `interface` → [[grounding.base.check|check]] · `impl` · call · `src/vulcan_map/core/grounding/base.py:33-34`
- `interface` → [[grounding.julia.julia_grounder|JuliaGrounder]] · `interface` · reads · `src/vulcan_map/core/grounding/julia.py:30-30`
- `interface` → [[grounding.python.python_grounder|PythonGrounder]] · `interface` · reads · `src/vulcan_map/core/grounding/python.py:11-11`
- `interface` → [[grounding.regex.regex_grounder|RegexGrounder]] · `interface` · reads · `src/vulcan_map/core/grounding/regex.py:10-10`
<!-- vulcan:connections:end -->

## Limitations
Because the contract is occurrence-based, a symbol mentioned only inside a
comment or a string literal satisfies it. This is a deliberate trade: tightening
it would require a parser for every supported language, which the conda-only
constraint rules out for Julia. The consequence is that V6 catches invented
identifiers but not misattributed ones.

## Provenance
Mapped from `src/vulcan_map/core/grounding/base.py`.
