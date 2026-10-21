# EGM for Claude Code

A Claude Code plugin for the [Elephant-Goldfish Model](https://egm.dev/) (EGM),
Google's open-source method for spec-driven development with AI coding agents.

An **Elephant** (your long-running session) brainstorms and drafts a design doc.
**Goldfish** reviewers (fresh subagents with no conversation history) then check
whether the doc stands on its own before any code is written. The skills,
personas, and document standards come unchanged from
[google/elephant-goldfish-model](https://github.com/google/elephant-goldfish-model).
This repository adds only what Claude Code needs to run them correctly.

> Community project. Not an official Google or Anthropic product. Upstream
> officially supports Antigravity and Gemini CLI.

## Install

Requires Claude Code 2.1.271 or later.

```text
/plugin marketplace add kurcontko/egm-claude-code
/plugin install egm@egm-community
```

Or from a shell:

```bash
claude plugin marketplace add kurcontko/egm-claude-code
claude plugin install egm@egm-community
```

## Use

| Step | Command | Who |
| --- | --- | --- |
| 1. Clarify an idea into a concepts brief | `/egm:egm-brainstorm <idea>` | Elephant |
| 2. Draft the design doc in `docs/designs/` | `/egm:egm-draft` | Elephant |
| 3. Review it with isolated reviewers | `/egm:egm-review docs/designs/<doc>.md` | Goldfish |
| 4. Work through the findings | `/egm:egm-resolve` | Elephant |
| 5. Build from the reviewed spec | your usual prompt | |
| Weekly: compare docs against code | `/egm:egm-drift-report` | |
| Existing codebase: generate READMEs bottom-up | `/egm:egm-bootstrap` | |

`/egm:egm-review-loop` runs an automated review-and-fix loop over any document.
The skills run only when you invoke them; Claude never starts them on its own.
See [egm.dev](https://egm.dev/) and the
[upstream getting-started guide](https://github.com/google/elephant-goldfish-model/blob/main/docs/getting_started.md)
for the method itself.

## What the overlay changes

Upstream's skills are harness-neutral: they say "spawn a subagent" and
reference `agents/` and `resources/` by relative path.
[`scripts/sync_upstream.py`](scripts/sync_upstream.py) copies upstream at the
commit pinned in [`upstream.json`](upstream.json) and applies a small,
mechanical overlay:

| Change | Why |
| --- | --- |
| Reviewer personas get `tools: Read, Grep, Glob`, `omitClaudeMd: true`, `model: inherit` | Without these, Claude Code subagents can edit files and load your `CLAUDE.md`, so a Goldfish is not really context-free |
| Each skill gets a note with the resolved `${CLAUDE_PLUGIN_ROOT}` and a pointer to [`docs/claude-code.md`](overlay/claude-code.md) | Installed skills live in the plugin cache, so relative paths would resolve against your project |
| [`docs/claude-code.md`](overlay/claude-code.md) maps the skills' wording onto Claude Code tools | `invoke_subagent` becomes `Agent` with `egm:egm-<persona>`; forks are ruled out because a fork inherits the whole conversation |
| Skill folders are renamed to their frontmatter names (`egm_review` → `egm-review`) | Claude Code names plugin commands after the folder |

Everything else is copied byte for byte. The orchestrator personas
(`egm-synthesizer`, `egm-bootstrap-orchestrator`) keep their full tool set,
because they spawn the reviewers.

## Verification

- `python scripts/sync_upstream.py --check` rebuilds the plugin from the pinned
  commit and fails if `plugins/egm/` differs.
- `pytest tests` checks the overlay: reviewer frontmatter, skill notes, resource
  paths, and that the manifest matches the marketplace and lock file.
- `tests/live_probe.py` runs one headless Claude Code session (about $0.15)
  in a throwaway workspace. It confirms that `/egm:egm-review` reads the guide
  from the plugin root and spawns `egm:egm-zoom-out` as a new agent, not a fork.
  It also confirms that the reviewer sees neither a `CLAUDE.md` marker nor a
  parent-prompt marker, and that it has only read-only tools.

CI runs the first two plus `claude plugin validate`. A weekly workflow rebuilds
from upstream `main` and opens a pull request when upstream changes.

## Contributing

Edit `overlay/` or `scripts/`, never `plugins/egm/` directly, then run:

```bash
python scripts/sync_upstream.py            # rebuild from the pinned commit
python scripts/sync_upstream.py --ref main # or move the pin to upstream main
pytest tests
```

## License

Apache-2.0, the same as upstream. See [LICENSE](LICENSE) and [NOTICE](NOTICE)
for what is changed from the upstream files.
