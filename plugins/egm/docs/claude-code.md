# Claude Code integration

The EGM skills are written for any harness. This page is for the agent running
them in Claude Code. It comes from the Claude Code packaging at
[kurcontko/egm-claude-code](https://github.com/kurcontko/egm-claude-code); the
skills, personas, and standards come from
[google/elephant-goldfish-model](https://github.com/google/elephant-goldfish-model).

Requires Claude Code 2.1.271 or later, the first version that supports
[`omitClaudeMd`](https://code.claude.com/docs/en/sub-agents).

- **Commands**: `/egm-review` in a skill means `/egm:egm-review` in Claude
  Code. The same goes for every other `/egm-<name>`.
- **Paths**: Read `agents/`, `resources/`, and `skills/` from the plugin root
  that each skill states near its top. Everything else, including
  `docs/designs/` and every file the skills write, is in the working directory.
  A skill's `references/` folder is relative to the skill's own directory.
  Never search for other installed copies.
- **Subagents**: Start each one with a new `Agent` call whose `subagent_type`
  is `egm:<persona name>`, for example `egm:egm-zoom-out`. Never fork the
  conversation or continue an earlier reviewer with `SendMessage`; both carry
  the Elephant's history into the review. Pass the task, absolute paths to the
  document and standards, and only the context the skill says to pass. To run
  reviewers in parallel, send several `Agent` calls in one message.
- **Chained skills**: The skills set `disable-model-invocation: true`, so the
  `Skill` tool refuses when one skill invokes another (for example
  `egm-review` invoking `egm-review-loop` or `egm-resolve`). Read that skill's
  `SKILL.md` from the plugin root and follow it in the same thread.
- **Questions**: Use `AskUserQuestion` with one question per call and
  `multiSelect: false`. Keep the skill's options and order, use each option's
  text as its description with a short label, and don't add "(Recommended)".
  The automatic "Other" answer is the user's write-in.
- **Runtime subagents**: Claude Code cannot register the bootstrap
  `goldfish-explorer` scout at runtime. Use a new `Explore` agent and put the
  scout's instructions and output schema in its prompt.

The reviewer personas allow only `Read`, `Grep`, and `Glob`, and set
`omitClaudeMd: true`, so reviewers cannot edit files or run commands and do not
load the user's or project's `CLAUDE.md`. The synthesizer may also spawn agents
and write its report. Reviewers can still read any file they can reach, so
don't point them at notes or logs that hold the Elephant's reasoning.
