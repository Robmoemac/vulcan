"""Regression tests for the Julia line-number bugs found by dogfooding.

Two independent mapping agents reported that V17 placed declarations one line
above their true position, and both compensated by recording wrong line numbers.
Both causes are covered here.
"""

from __future__ import annotations

from vulcan_map.core.grounding.julia import JuliaGrounder

G = JuliaGrounder()


def test_blank_line_before_declaration_does_not_shift_the_result() -> None:
    r"""`^\s*` let \s match the preceding newline, starting the match a line early."""
    text = "module M\n\n\nfunction propagate(x)\n    x\nend\n"
    assert text.splitlines()[3].startswith("function propagate")
    assert G.symbol_line(text, "propagate") == 4


def test_docstring_before_declaration_does_not_shift_the_result() -> None:
    text = '"""\ndocs\n"""\nfunction solve(a, b)\n    a\nend\n'
    assert G.symbol_line(text, "solve") == 4


def test_indented_declaration_reports_its_own_line() -> None:
    text = "module M\n\n    function inner(x)\n        x\n    end\nend\n"
    assert G.symbol_line(text, "inner") == 3


def test_earliest_declaration_wins_over_pattern_order() -> None:
    """A struct at line 2 must beat a short-form constructor at line 6.

    Patterns were tried in fixed order, so the `f(...) =` form matched first and
    reported the constructor rather than the type.
    """
    text = (
        "module M\n"
        "struct ProcessPool\n"
        "    n::Int\n"
        "end\n"
        "\n"
        "ProcessPool(x, y) = ProcessPool(x + y)\n"
        "end\n"
    )
    assert G.symbol_line(text, "ProcessPool") == 2


def test_first_line_declaration() -> None:
    assert G.symbol_line("module Alpha\nend\n", "Alpha") == 1


def test_falls_back_to_occurrence_when_not_declared() -> None:
    text = "module M\nusing Other: helper\nend\n"
    assert G.symbol_line(text, "helper") == 2
