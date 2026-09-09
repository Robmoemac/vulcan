"""Skill documents and the D7 adapter baseline."""

from __future__ import annotations

from pathlib import Path

import pytest

from vulcan_map.skills import SKILLS, all_skills, load_skill
from vulcan_map.skills import adapters as adapters_mod


def test_all_three_skills_load() -> None:
    names = {s.name for s in all_skills()}
    assert names == {"vulcan-map", "vulcan-subchart", "vulcan-augment"}


@pytest.mark.parametrize("key", sorted(SKILLS))
def test_includes_are_resolved(key: str) -> None:
    """Emitted skills must be self-contained; no agent resolves {{include}}."""
    skill = load_skill(key)
    assert "{{include" not in skill.body
    assert "COMPLETION CONTRACT" in skill.body


@pytest.mark.parametrize("key", sorted(SKILLS))
def test_completion_gate_is_stated(key: str) -> None:
    skill = load_skill(key)
    assert "vulcan check --strict" in skill.body
    assert "Forbidden stopping points" in skill.body


def test_skill_frontmatter_round_trips() -> None:
    skill = load_skill("master")
    text = skill.with_frontmatter()
    assert text.startswith("---\n")
    assert "name: vulcan-map" in text
    assert text.count("---") >= 2


def test_default_adapter_set_is_the_d7_baseline() -> None:
    assert adapters_mod.DEFAULT_KEYS == ("claude-code", "codex", "devin", "agents-md")
    assert "cursor" not in adapters_mod.ADAPTERS  # D7: deliberately excluded


def test_unknown_adapter_is_rejected() -> None:
    with pytest.raises(KeyError, match="Unknown adapter"):
        adapters_mod.get(["nope"])


def test_adapters_write_expected_locations(tmp_path: Path) -> None:
    skills = list(all_skills())
    for adapter in adapters_mod.get():
        adapter.install(tmp_path, skills)

    assert (tmp_path / ".claude" / "skills" / "vulcan-map" / "SKILL.md").exists()
    assert (tmp_path / ".claude" / "skills" / "vulcan-subchart" / "SKILL.md").exists()
    assert (tmp_path / ".claude" / "skills" / "vulcan-augment" / "SKILL.md").exists()
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".devin" / "vulcan-map.md").exists()


def test_agents_md_preserves_user_content(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# House rules\n\nAlways run the linter.\n", encoding="utf-8")

    adapters_mod.ADAPTERS["agents-md"].install(tmp_path, list(all_skills()))
    text = agents.read_text(encoding="utf-8")
    assert "Always run the linter." in text
    assert "vulcan-map:begin" in text


def test_agents_md_install_is_idempotent(tmp_path: Path) -> None:
    """Re-running init must not append a second copy of the block."""
    skills = list(all_skills())
    adapter = adapters_mod.ADAPTERS["agents-md"]
    adapter.install(tmp_path, skills)
    first = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    adapter.install(tmp_path, skills)
    second = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert first == second
    assert second.count("vulcan-map:begin") == 1


def test_codex_and_agents_md_share_one_file(tmp_path: Path) -> None:
    """Three of four baseline targets converge on AGENTS.md (D7)."""
    skills = list(all_skills())
    adapters_mod.ADAPTERS["codex"].install(tmp_path, skills)
    adapters_mod.ADAPTERS["agents-md"].install(tmp_path, skills)
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert text.count("vulcan-map:begin") == 1


# --- handoff / anti-self-report hardening -------------------------------------

@pytest.mark.parametrize("key", sorted(SKILLS))
def test_every_skill_forbids_unproven_completion_claims(key: str) -> None:
    """The contract must reach every adapter, not just Claude's."""
    body = load_skill(key).body
    assert "vulcan check --strict --proof" in body
    assert "is void" in body
    assert "vulcan status" in body


@pytest.mark.parametrize("key", sorted(SKILLS))
def test_every_skill_tells_the_agent_not_to_trust_predecessors(key: str) -> None:
    body = load_skill(key).body
    assert "no agent's account of progress is evidence" in body.lower()
    assert "HANDOFF.md" in body


def test_agents_md_header_carries_the_proof_requirement(tmp_path: Path) -> None:
    """Codex/Devin/generic all read AGENTS.md — the rule must be near the top."""
    adapters_mod.ADAPTERS["agents-md"].install(tmp_path, list(all_skills()))
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    head = text[: text.find("## Skill:")]
    assert "vulcan status" in head
    assert "vulcan check --strict --proof" in head
    assert "void" in head


def test_claude_and_devin_targets_carry_it_too(tmp_path: Path) -> None:
    skills = list(all_skills())
    for adapter in adapters_mod.get():
        adapter.install(tmp_path, skills)
    claude = (tmp_path / ".claude" / "skills" / "vulcan-map" / "SKILL.md").read_text(encoding="utf-8")
    devin = (tmp_path / ".devin" / "vulcan-map.md").read_text(encoding="utf-8")
    for text in (claude, devin):
        assert "vulcan check --strict --proof" in text
        assert "HANDOFF.md" in text
