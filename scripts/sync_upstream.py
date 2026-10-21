#!/usr/bin/env python3
"""Build plugins/egm from google/elephant-goldfish-model plus the Claude Code overlay.

Usage:
  scripts/sync_upstream.py                 # rebuild from the commit pinned in upstream.json
  scripts/sync_upstream.py --ref main      # move the pin to upstream main, then rebuild
  scripts/sync_upstream.py --check         # fail if plugins/egm differs from a fresh build
  scripts/sync_upstream.py --source DIR    # use a local upstream checkout instead of cloning

The overlay is deliberately small and mechanical:
  * reviewer personas get read-only tools and a CLAUDE.md-free context,
  * every skill gets a one-paragraph pointer to docs/claude-code.md,
  * docs/claude-code.md and .claude-plugin/plugin.json are added.
Everything else is copied from upstream byte for byte.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "upstream.json"
PLUGIN = ROOT / "plugins" / "egm"
GUIDE = ROOT / "overlay" / "claude-code.md"

# Upstream paths shipped in the plugin. Skills read agents/, resources/, and docs/ at run time.
INCLUDE = ("LICENSE", "agents", "docs", "resources", "skills")
# Upstream test fixtures that live next to skills but are not part of a skill.
EXCLUDE = ("TEST.md", "test_scenarios.yaml")

# Personas that spawn and coordinate other agents keep their full tool set.
# Every other persona is a Goldfish reviewer and is made read-only, so a new
# upstream persona fails closed rather than open.
ORCHESTRATORS = {"egm-bootstrap-orchestrator", "egm-synthesizer"}
REVIEWER_KEYS = {"tools": "Read, Grep, Glob", "omitClaudeMd": "true"}
# The synthesizer spawns reviewers and writes its report; it needs nothing else.
ORCHESTRATOR_KEYS = {"egm-synthesizer": {"tools": "Agent, Read, Grep, Glob, Write"}}

OVERLAY_MARK = "egm-claude-code overlay"
SKILL_NOTE = f"""\
<!-- Added by the {OVERLAY_MARK}: https://github.com/kurcontko/egm-claude-code -->
**Claude Code:** read `agents/`, `resources/`, and `skills/` from the plugin root,
`${{CLAUDE_PLUGIN_ROOT}}`. Everything else, including `docs/designs/` and every
file you write, is in the working directory. Before you start, read
`${{CLAUDE_PLUGIN_ROOT}}/docs/claude-code.md` unless you already have in this
session; it maps these instructions onto Claude Code tools.
"""
ORCHESTRATOR_NOTE = f"""\
<!-- Added by the {OVERLAY_MARK}: https://github.com/kurcontko/egm-claude-code -->
**Claude Code:** read `agents/` and `resources/` from the plugin root,
`${{CLAUDE_PLUGIN_ROOT}}`. Spawn each subagent with the `Agent` tool as a new agent
of type `egm:<persona name>`, for example `egm:egm-zoom-out`, never as a fork.
"""

FRONTMATTER = re.compile(r"\A---\n(.*?\n)---\n", re.DOTALL)


def git(*args: str, cwd: Path | None = None) -> str:
  return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                        text=True).stdout.strip()


def fetch_upstream(repository: str, ref: str, dest: Path) -> str:
  """Check out `ref` of `repository` into `dest` and return the resolved commit."""
  git("init", "-q", str(dest))
  git("fetch", "-q", "--depth", "1", repository, ref, cwd=dest)
  git("checkout", "-q", "FETCH_HEAD", cwd=dest)
  return git("rev-parse", "HEAD", cwd=dest)


def frontmatter_value(text: str, key: str) -> str | None:
  match = FRONTMATTER.match(text)
  if not match:
    return None
  found = re.search(rf"^{re.escape(key)}:\s*(.+)$", match.group(1), re.MULTILINE)
  return found.group(1).strip() if found else None


def restrict_reviewer(text: str, keys: dict[str, str] = REVIEWER_KEYS) -> str:
  """Add Claude Code keys to a persona's frontmatter, keeping any upstream values."""
  match = FRONTMATTER.match(text)
  if not match:
    raise ValueError("persona has no frontmatter")
  body = match.group(1)
  missing = [f"{key}: {value}\n" for key, value in keys.items()
             if not re.search(rf"^{key}:", body, re.MULTILINE)]
  if not missing:
    return text
  added = f"# Claude Code keys added by the {OVERLAY_MARK}\n" + "".join(missing)
  return f"---\n{body}{added}---\n" + text[match.end():]


def add_note(text: str, note: str = SKILL_NOTE) -> str:
  """Insert a Claude Code note right after the frontmatter, once."""
  if f"Added by the {OVERLAY_MARK}" in text:
    return text
  match = FRONTMATTER.match(text)
  if not match:
    raise ValueError("file has no frontmatter")
  return text[:match.end()] + "\n" + note + text[match.end():]


def apply_overlay(plugin: Path, repository: str, commit: str, upstream: Path) -> None:
  for persona in sorted((plugin / "agents").glob("*.md")):
    text = persona.read_text()
    name = frontmatter_value(text, "name")
    if name not in ORCHESTRATORS:
      persona.write_text(restrict_reviewer(text))
    else:
      # Orchestrators run as subagents and never see a skill's note, so they get their own.
      text = add_note(text, ORCHESTRATOR_NOTE)
      persona.write_text(restrict_reviewer(text, ORCHESTRATOR_KEYS.get(name, {})))

  for skill in sorted((plugin / "skills").glob("*/SKILL.md")):
    skill.write_text(add_note(skill.read_text()))
    # Claude Code names a plugin skill command after its folder, so egm_review would run as
    # /egm:egm_review. Rename the folder to the frontmatter name to get /egm:egm-review.
    name = frontmatter_value(skill.read_text(), "name")
    if name and skill.parent.name != name:
      skill.parent.rename(skill.parent.with_name(name))

  shutil.copyfile(GUIDE, plugin / "docs" / "claude-code.md")

  version = json.loads((upstream / "gemini-extension.json").read_text())["version"]
  manifest = {
      "name": "egm",
      "displayName": "Elephant-Goldfish Model",
      "version": f"{version}+{commit[:7]}",
      "description": json.loads((upstream / "plugin.json").read_text())["description"],
      "author": {"name": "Google LLC (upstream); Claude Code overlay by Michał Kurc"},
      "homepage": "https://egm.dev/",
      "repository": "https://github.com/kurcontko/egm-claude-code",
      "license": "Apache-2.0",
      "keywords": ["spec-driven-development", "design-docs", "review", "elephant-goldfish"],
      "metadata": {"upstream": {"repository": repository, "commit": commit}},
  }
  (plugin / ".claude-plugin").mkdir()
  (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def build(upstream: Path, out: Path, repository: str, commit: str) -> None:
  if out.exists():
    shutil.rmtree(out)
  out.mkdir(parents=True)
  for name in INCLUDE:
    src = upstream / name
    if src.is_dir():
      shutil.copytree(src, out / name, ignore=shutil.ignore_patterns(*EXCLUDE))
    else:
      shutil.copyfile(src, out / name)
  apply_overlay(out, repository, commit, upstream)


def diff_trees(a: Path, b: Path) -> list[str]:
  """Return paths that differ between two directory trees."""
  problems = []
  def walk(cmp: filecmp.dircmp, prefix: str) -> None:
    problems.extend(f"only in build: {prefix}{n}" for n in cmp.left_only)
    problems.extend(f"only in plugin: {prefix}{n}" for n in cmp.right_only)
    _, mismatch, errors = filecmp.cmpfiles(cmp.left, cmp.right, cmp.common_files, shallow=False)
    problems.extend(f"differs: {prefix}{n}" for n in mismatch + errors)
    for name, sub in cmp.subdirs.items():
      walk(sub, f"{prefix}{name}/")
  walk(filecmp.dircmp(a, b, ignore=[]), "")
  return problems


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--ref", help="upstream ref to pin (default: keep the pinned commit)")
  parser.add_argument("--source", type=Path, help="local upstream checkout to build from")
  parser.add_argument("--check", action="store_true", help="verify plugins/egm, change nothing")
  args = parser.parse_args()

  lock = json.loads(LOCK.read_text())
  repository = lock["repository"]

  with tempfile.TemporaryDirectory() as tmp:
    if args.source:
      upstream = args.source.resolve()
      commit = git("rev-parse", "HEAD", cwd=upstream)
    else:
      upstream = Path(tmp) / "upstream"
      commit = fetch_upstream(repository, args.ref or lock["commit"], upstream)

    if args.check:
      built = Path(tmp) / "built"
      build(upstream, built, repository, commit)
      problems = diff_trees(built, PLUGIN) if PLUGIN.exists() else ["plugins/egm is missing"]
      if commit != lock["commit"]:
        problems.insert(0, f"source is {commit}, upstream.json pins {lock['commit']}")
      for problem in problems:
        print(problem, file=sys.stderr)
      print("plugins/egm is up to date" if not problems else
            "plugins/egm is stale: run scripts/sync_upstream.py")
      return 1 if problems else 0

    build(upstream, PLUGIN, repository, commit)
    if commit != lock["commit"]:
      lock["commit"] = commit
      LOCK.write_text(json.dumps(lock, indent=2) + "\n")
    print(f"Built plugins/egm from {repository} @ {commit}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
