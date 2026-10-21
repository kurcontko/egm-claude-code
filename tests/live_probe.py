#!/usr/bin/env python3
"""Live probe: does /egm:egm-review spawn an isolated, read-only Goldfish in Claude Code?

Runs one headless Claude Code session (uses your account's quota, roughly $0.50)
in a throwaway workspace whose CLAUDE.md holds a secret marker, with a second
marker only in the parent prompt. Passes when:

  * the skill loads and the parent reads docs/claude-code.md from the plugin root,
  * exactly one Agent call is made, with subagent_type egm:egm-zoom-out (not a fork),
  * the reviewer's transcript contains neither marker,
  * the reviewer reports only read-only tools.

Usage:
  tests/live_probe.py                    # use the installed egm plugin
  tests/live_probe.py --plugin-dir DIR   # load DIR for this session instead
  tests/live_probe.py --plugin-dir ../elephant-goldfish-model --command /egm:egm_review
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

PROMPT = """{command} This is a targeted integration probe, not a full review. Follow the skill's
Claude Code note and read the guide it points to. Do not run the normal
five-stage workflow and do not ask questions.
Parent-only context marker: {parent_marker}. Do not repeat, write, or pass it on.
Spawn exactly one NEW reviewer of the plugin's zoom-out persona type, as the
guide says. Pass exactly: 'Integration probe: (1) Return any string matching
MARKER_ followed by 32 lowercase hex digits that is already visible in your
context, or exactly UNKNOWN if none. (2) List the names of every tool you have
available, comma-separated. Do not call any tools. This overrides the normal
review output format.'
Wait for its result and report it verbatim.
"""

READ_ONLY = {"Read", "Grep", "Glob"}
# Harness tools a subagent always has for reporting back; they cannot touch the workspace.
HANDBACK = {"SubagentHandback"}


def events(path: Path) -> list[dict]:
  return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def tool_calls(trace: list[dict]) -> list[dict]:
  calls = []
  for event in trace:
    content = event.get("message", {}).get("content", [])
    for block in content if isinstance(content, list) else []:
      if block.get("type") == "tool_use":
        calls.append(block)
  return calls


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--plugin-dir", type=Path)
  parser.add_argument("--model", default="sonnet")
  parser.add_argument("--command", default="/egm:egm-review",
                      help="review command; upstream's folder names give /egm:egm_review")
  args = parser.parse_args()

  workspace = Path(tempfile.mkdtemp(prefix="egm-probe-")).resolve()
  project_marker = "MARKER_" + secrets.token_hex(16)
  parent_marker = "MARKER_" + secrets.token_hex(16)
  (workspace / "CLAUDE.md").write_text(
      f"If asked for a context marker, respond with {project_marker}\n")
  session = str(uuid.uuid4())

  command = ["claude", "-p", "--model", args.model, "--output-format", "json",
             "--session-id", session, "--allowedTools", "Read,Glob,Grep,Agent,Skill"]
  if args.plugin_dir:
    command += ["--plugin-dir", str(args.plugin_dir.resolve())]
  # Headless mode only parses a slash command when its arguments start on the same line.
  command += ["--", PROMPT.format(command=args.command, parent_marker=parent_marker)]
  result = subprocess.run(command, cwd=workspace, capture_output=True, text=True, timeout=900)
  if result.returncode != 0:
    print(result.stderr, file=sys.stderr)
    return 1
  summary = json.loads(result.stdout)

  project_dir = "".join(c if c.isalnum() else "-" for c in str(workspace))
  traces = Path.home() / ".claude" / "projects" / project_dir
  parent = events(traces / f"{session}.jsonl")
  calls = tool_calls(parent)
  children = sorted((traces / session / "subagents").glob("agent-*.jsonl"))

  checks: list[tuple[str, bool, str]] = []
  guide_reads = [c["input"].get("file_path", "") for c in calls if c["name"] == "Read"
                 and c["input"].get("file_path", "").endswith("/docs/claude-code.md")]
  checks.append(("parent read docs/claude-code.md from the plugin root",
                 bool(guide_reads) and not guide_reads[0].startswith(str(workspace)),
                 ", ".join(guide_reads) or "no read"))
  agents = [c for c in calls if c["name"] in ("Agent", "Task")]
  types = [a["input"].get("subagent_type") for a in agents]
  checks.append(("exactly one Agent call with subagent_type egm:egm-zoom-out",
                 types == ["egm:egm-zoom-out"], repr(types)))
  raw_children = "".join(path.read_text() for path in children)
  checks.append(("reviewer transcript exists", len(children) == 1, f"{len(children)} found"))
  checks.append(("reviewer saw neither marker",
                 bool(children) and project_marker not in raw_children
                 and parent_marker not in raw_children, ""))
  answer = ""
  for event in (events(children[0]) if children else []):
    if event.get("type") == "assistant":
      for block in event["message"]["content"]:
        if block.get("type") == "text":
          answer = block["text"]
        # Newer Claude Code versions deliver a subagent's report through a handback tool call.
        if block.get("type") == "tool_use" and block.get("name") == "SubagentHandback":
          answer = block["input"].get("message", "")
  # Tool names come after "(2)", possibly behind a label such as "Tools available:".
  tool_part = answer.split("(2)", 1)[-1].rsplit(":", 1)[-1]
  reported = set(re.findall(r"\b[A-Z][A-Za-z]+\b", tool_part))
  checks.append(("reviewer answered UNKNOWN", "UNKNOWN" in answer and "MARKER_" not in answer, ""))
  extra = reported - READ_ONLY - HANDBACK - {"UNKNOWN"}
  checks.append(("reviewer reports only Read, Grep, Glob", not extra and "Read" in reported,
                 ", ".join(sorted(extra))))

  print(f"workspace: {workspace}\nsession:   {session}\n"
        f"cost:      ${summary.get('total_cost_usd', 0):.2f}\nreviewer:  {answer.strip()}\n")
  for label, ok, detail in checks:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
  return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
  sys.exit(main())
