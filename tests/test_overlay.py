"""Offline checks of the built plugin and the overlay functions."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "egm"

spec = importlib.util.spec_from_file_location("sync_upstream", ROOT / "scripts" / "sync_upstream.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

PERSONAS = sorted((PLUGIN / "agents").glob("*.md"))
SKILLS = sorted((PLUGIN / "skills").glob("*/SKILL.md"))


def name_of(path: Path) -> str | None:
  return sync.frontmatter_value(path.read_text(), "name")


def test_plugin_is_built() -> None:
  assert PERSONAS and SKILLS


@pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p.stem)
def test_reviewers_are_read_only_and_skip_claude_md(persona: Path) -> None:
  text = persona.read_text()
  if name_of(persona) in sync.ORCHESTRATORS:
    assert sync.frontmatter_value(text, "tools") is None
    assert sync.OVERLAY_MARK not in text
    return
  assert sync.frontmatter_value(text, "tools") == "Read, Grep, Glob"
  assert sync.frontmatter_value(text, "omitClaudeMd") == "true"
  assert sync.frontmatter_value(text, "model") == "inherit"
  assert sync.frontmatter_value(text, "memory") is None


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_skills_point_to_the_guide(skill: Path) -> None:
  text = skill.read_text()
  assert "${CLAUDE_PLUGIN_ROOT}/docs/claude-code.md" in text
  assert text.count(sync.OVERLAY_MARK) == 1


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_skill_folder_matches_its_name(skill: Path) -> None:
  # Claude Code names the command after the folder: /egm:<folder>.
  assert skill.parent.name == name_of(skill)


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_resources_named_by_skills_exist(skill: Path) -> None:
  text = skill.read_text()
  for path in set(re.findall(r"`((?:agents|resources)/[\w./-]+\.md)`", text)):
    assert (PLUGIN / path).is_file(), path
  for path in set(re.findall(r"\((references/[\w./-]+\.md)\)|`(references/[\w./-]+\.md)`", text)):
    relative = next(p for p in path if p)
    assert (skill.parent / relative).is_file(), relative


def test_guide_names_every_agent_and_skill() -> None:
  guide = (PLUGIN / "docs" / "claude-code.md").read_text()
  for skill in SKILLS:
    assert f"/egm:{skill.parent.name}`" in guide, skill.parent.name


def test_guide_is_not_named_like_claude_md() -> None:
  # macOS file systems are case-insensitive, so docs/claude.md would load as a nested CLAUDE.md.
  assert not [p for p in PLUGIN.rglob("*") if p.name.lower() == "claude.md"]


def test_manifest_matches_marketplace_and_lock() -> None:
  manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
  marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
  lock = json.loads((ROOT / "upstream.json").read_text())
  entry = next(p for p in marketplace["plugins"] if p["name"] == manifest["name"])
  assert (ROOT / entry["source"]).resolve() == PLUGIN
  assert manifest["metadata"]["upstream"]["commit"] == lock["commit"]
  assert manifest["version"].endswith("+" + lock["commit"][:7])


def test_overlay_is_idempotent() -> None:
  persona = "---\nname: egm-x\ndescription: d\n---\n\nBody\n"
  once = sync.restrict_reviewer(persona)
  assert sync.restrict_reviewer(once) == once
  skill = "---\nname: egm-y\ndescription: d\n---\n\n# Title\n"
  once = sync.add_skill_note(skill)
  assert sync.add_skill_note(once) == once
  assert once.startswith(skill.split("\n# Title")[0])


def test_overlay_keeps_upstream_reviewer_keys() -> None:
  persona = "---\nname: egm-x\ntools: Read\n---\nBody\n"
  out = sync.restrict_reviewer(persona)
  assert sync.frontmatter_value(out, "tools") == "Read"
  assert sync.frontmatter_value(out, "omitClaudeMd") == "true"
