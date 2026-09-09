---
id: grounding.regex.regex_grounder
label: RegexGrounder
kind: struct
source:
  file: src/vulcan_map/core/grounding/regex.py
  symbol: RegexGrounder
  lines:
  - 10
  - 16
inputs:
- id: interface
  type: Grounder
  units: n/a
  required: true
  description: The abstract base contract this class implements.
outputs:
- id: matcher
  type: Grounder
  units: n/a
  description: A language-agnostic whole-word matcher, also used as a fallback.
tags:
- grounding
charts:
- master
origin: agent
---

# RegexGrounder

## Purpose
The language-agnostic grounder. Serves both as the default for file types with no
dedicated grounder and as the fallback inside the Julia and Python grounders.

## Theory & Math
The match is a whole-word test built from negative lookarounds:

$$
\text{(?<![A-Za-z0-9\_])}\;\; \mathrm{escape}(s) \;\;\text{(?![A-Za-z0-9\_])}
$$

for a symbol $s$. The lookarounds prevent a substring match, so searching for
`run` does not match `runner` or `prerun`. `re.escape` neutralises regex
metacharacters, which matters because symbol names in some languages contain
characters such as `!` or `?`.

## Model & Assumptions
- Identifier characters are ASCII letters, digits, and underscore. Symbols
  containing other characters still match, but the word-boundary guarantee
  applies only to that character class.
- An empty symbol never matches; this is checked before the search so that a
  node with a blank symbol fails grounding rather than matching everything.

## Design & Implementation
`contains_symbol` returns whether `re.search` finds the bounded pattern anywhere
in the text. The pattern is constructed per call rather than cached, since the
symbol differs on nearly every call and compilation is dominated by the search
itself.

## Interface (ICD)
<!-- vulcan:icd:begin -->
| Direction | Socket | Type | Units | Required | Description |
|---|---|---|---|---|---|
| in | `interface` | Grounder | n/a | yes | The abstract base contract this class implements. |
| out | `matcher` | Grounder | n/a | — | A language-agnostic whole-word matcher, also used as a fallback. |
<!-- vulcan:icd:end -->

## Connections
<!-- vulcan:connections:begin -->
**Upstream**

- [[grounding.base.grounder|Grounder]] · `interface` → `interface` · reads · `src/vulcan_map/core/grounding/regex.py:10-10`

**Downstream**

- `matcher` → [[grounding.julia.julia_grounder|JuliaGrounder]] · `fallback` · dataflow · `src/vulcan_map/core/grounding/julia.py:33-34`
- `matcher` → [[grounding.python.python_grounder|PythonGrounder]] · `fallback` · dataflow · `src/vulcan_map/core/grounding/python.py:14-15`
- `matcher` → [[grounding.registry.grounder_for|grounder_for]] · `regex` · dataflow · `src/vulcan_map/core/grounding/__init__.py:13-20`
<!-- vulcan:connections:end -->

## Limitations
Matches occurrences in comments and string literals, and cannot distinguish a
definition from a reference. It will also match a symbol that appears only in an
import statement, so a re-exporting module grounds symbols it does not define.

## Provenance
Mapped from `src/vulcan_map/core/grounding/regex.py`.
