# Claude Code integration

This guide maps the harness-neutral EGM skills onto Claude Code. It is part of
the Claude Code overlay maintained at
[kurcontko/egm-claude-code](https://github.com/kurcontko/egm-claude-code); the
skills, personas, and standards themselves come unchanged from
[google/elephant-goldfish-model](https://github.com/google/elephant-goldfish-model).

Requires Claude Code 2.1.271 or later (`omitClaudeMd` support). On older
versions, reviewers load your `CLAUDE.md` files and the review is not a verified
Goldfish review.

## Invocation

The skills are user-invoked only (`disable-model-invocation: true`), so Claude
never starts them on its own. Run them with the plugin prefix:

| Skill | Command |
| --- | --- |
| Brainstorm | `/egm:egm-brainstorm` |
| Draft | `/egm:egm-draft` |
| Review | `/egm:egm-review` |
| Resolve review findings | `/egm:egm-resolve` |
| Review loop | `/egm:egm-review-loop` |
| Bootstrap READMEs | `/egm:egm-bootstrap` |
| Drift report | `/egm:egm-drift-report` |

## Paths

- **Plugin resources.** `agents/`, `resources/`, and `docs/` resolve against
  the plugin root that the invoked skill states in its Claude Code note. That
  note already carries the absolute path. This guide is read as a plain file, so
  it cannot carry the path itself. Never guess a plugin cache version, and never
  search other installed copies.
- **Skill references.** A skill's own `references/` folder resolves against
  the skill's base directory, which Claude Code shows when the skill loads.
- **User artifacts.** Concepts briefs, design docs, review reports, and other
  generated files belong in the user's working directory. Never write into the
  plugin directory. Claude Code has no separate artifact directory or side
  panel; where a skill mentions one, use the working directory.

## Tool mapping

| Skill wording | Claude Code |
| --- | --- |
| "subagent tool", `invoke_subagent` | `Agent` tool |
| Named subagent `egm-<persona>` | `subagent_type: "egm:egm-<persona>"`, for example `egm:egm-zoom-out` |
| Structured question tool, `ask_question` | `AskUserQuestion`. It takes 2 to 4 options per question and always adds "Other"; when a skill needs more options, ask in plain chat |
| File-writing tool, `write_to_file` | `Write` (or `Edit` for an existing file) |
| `view_file`, `list_dir` | `Read`, `Glob` |
| Runtime subagent definition (`define_subagent`, the bootstrap `goldfish-explorer` scout) | Claude Code cannot define subagents at runtime. Use the built-in read-only `Explore` agent and pass the scout's system prompt and output schema in the task prompt |

## Goldfish isolation

A Goldfish review is only valid in a fresh context. In Claude Code:

1. **Spawn a new named agent for every review.** Call `Agent` with the
   persona's `egm:` subagent type. Never use a fork (a subagent that inherits
   the conversation), never use `/subtask`, and never continue a previous
   reviewer with `SendMessage`. Each of those carries the Elephant's history
   into the review.
2. **Pass only what the Goldfish may know.** Send the task, the absolute path
   of the target document, the absolute paths of the persona and standard
   files, and any context the skill explicitly says to supply. Do not summarize
   the conversation, your reasoning, or earlier reviewer output into the prompt.
3. **Wait for the report.** Run reviewers in the foreground and wait for each
   result before acting on it. To run reviewers in parallel, send several
   `Agent` calls in one message.
4. **Nesting works.** By default a subagent can spawn subagents up to three
   levels deep, so the `egm:egm-synthesizer` path works as written. If
   `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` is set to `1`, use direct dispatch
   instead of the synthesizer.

The overlay sets three keys in the frontmatter of every reviewer persona in
`agents/`:

- `tools: Read, Grep, Glob`: reviewers cannot edit files, run shell commands,
  or spawn agents. The Elephant applies fixes.
- `omitClaudeMd: true`: reviewers start without user, project, and local
  `CLAUDE.md` files. Managed policy files still load.
- `model: inherit`: reviewers use the session's model.

The orchestrator personas (`egm-synthesizer`, `egm-bootstrap-orchestrator`)
keep their full tool set because they spawn and coordinate other agents.

This is context and tool isolation, not filesystem isolation. Reviewers can
still read any file they can reach, so keep logs, notes, and transcripts that
hold Elephant reasoning out of the paths you hand them.
