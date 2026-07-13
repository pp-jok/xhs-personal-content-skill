# Runtime Skill Slimming Plan

## Goal

Reduce Codex token usage when this skill is installed in other projects, without weakening the core product behavior:

```text
creator profile
→ benchmark samples
→ evidence-first analysis
→ account-fit assessment
→ user-confirmed rules
→ topics
→ drafts
→ focused revisions
→ reviews
```

## Objective Assessment

The previous runtime `SKILL.md` was too heavy for normal account-operation use:

- It mixed runtime guidance, CLI reference, user manual, examples, development governance, and verification commands.
- It encouraged broad workspace reads for tasks that only need a small subset of local memory.
- It repeated command examples already documented in `docs/cli.md`.
- It kept repository-development instructions in the same path used by normal users after installation.

The issue was not that the feature set was too large. The issue was that the always-loaded runtime instructions carried too much implementation detail.

## What Changed

`SKILL.md` is now a lightweight runtime guide:

- Shorter trigger description.
- Concise user-facing response contract.
- Explicit mode policy so many requests stay as light chat or lightweight analysis instead of entering persistence workflows.
- Explicit minimal-read policy.
- Five core flows instead of ten detailed workflow blocks.
- No command catalog.
- No long response examples.
- Development governance moved behind references.

Detailed references remain available:

- `docs/cli.md` for command syntax.
- `docs/user-manual.md` for full user instructions.
- `docs/data-models.md` for model details.
- `AGENTS.md` and architecture docs for repository development.

## What Must Not Be Removed

The following remain core behavior and should not be slimmed away:

- Single-account long-term memory.
- Continuous benchmark sample input.
- User preference and feedback accumulation.
- Evidence-first content analysis.
- Account-fit assessment.
- Candidate rules requiring user confirmation.
- Active-rule-only formal generation.
- Topic audit chain.
- Draft audit chain.
- One focused revision per user request.
- No auto-publish.
- No bulk crawling.
- No external model API configuration.

## Runtime Policy

The agent should read only what the task requires:

- Light chat and lightweight analysis do not read the workspace or write records by default.
- Profile update: profile memory only.
- Link/post intake: profile plus the specific inbox/capture/analysis records.
- Rule decision: the specific candidate, evidence, analysis, and decisions.
- Topic generation: profile, active rules, relevant feedback, task constraints.
- Draft generation: selected topic only.
- Focused revision: selected draft only.
- Review: own post, related draft/task, active rules, quality reviews.

Large docs and full CLI references are opt-in.

## Expected Impact

This should reduce routine installed-skill context usage while preserving the workflow guarantees that make the skill different from a generic content generator.
