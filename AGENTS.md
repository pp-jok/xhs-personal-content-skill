# AGENTS.md

## Scope

This file governs repository development, code review, repair work, and PR planning for `xhs-personal-content-skill`.

It does not replace the user-facing workflows in `SKILL.md`.

Before modifying this repository, read:

1. `AGENTS.md`
2. `docs/architecture/invariants.md`
3. the current implementation plan under `docs/plans/`
4. `SKILL.md` for product and user-facing behavior

## Product Priority

Prioritize, in order:

1. Semantic correctness
2. User trust and control
3. User-facing simplicity
4. Small verifiable delivery
5. Maintainability
6. Feature breadth

Do not trade the first four for faster feature expansion.

## Permanent Development Rules

1. One PR should implement one primary user-visible behavior.
2. Do not combine collection, analysis, rule activation, user decision, and generation in one PR.
3. Do not start implementation before repository impact analysis is complete.
4. A local code change is incomplete until all readers and writers of the affected state have been checked.
5. Reuse existing provenance, decision, versioning, lifecycle, and active-rule mechanisms.
6. Do not introduce parallel systems for the same responsibility.
7. Keep CLI handlers thin. Put domain behavior in focused modules or services.
8. Do not expose internal models, paths, commands, or statuses to normal users.
9. Complete the requested PR and stop. Do not automatically begin the next roadmap item.
10. Do not create work only to satisfy a roadmap. Skip a PR when current behavior already meets the contract.

## Required Three-Stage Workflow

### Stage A — Impact Analysis

Do not modify code.

Output:

1. Exact user-visible behavior
2. Existing repository capability
3. Models and state transitions involved
4. All read paths
5. All write paths
6. Cross-module invariants
7. Positive tests
8. Negative tests
9. Conflict and migration tests
10. Expected changed files
11. Explicit non-goals
12. Whether implementation is actually required

Stop after Stage A.

### Stage B — Scoped Implementation

Start only after Stage A is approved.

Requirements:

1. Implement only the approved scope.
2. Prefer 8–12 changed files or fewer.
3. Prefer one state machine at most.
4. Reuse centralized selectors and validators.
5. Do not duplicate lifecycle or status logic.
6. Run focused tests during development.
7. Add positive, negative, and conflict tests.
8. Perform one end-to-end acceptance scenario.
9. Do not expand into the next PR.
10. Open a Draft PR when implementation is ready for review.

### Stage C — Diff Audit

Review the feature branch against `main`.

Verify:

1. The diff matches Stage A
2. All read paths enforce invariants
3. All write paths preserve invariants
4. Provenance is not bypassed
5. DecisionRequest is not bypassed
6. Active-rule selection is not bypassed
7. Actor fields are not confused
8. User-facing output hides technical details
9. No duplicate architecture was added
10. Positive, negative, conflict, and end-to-end tests pass

Then run once:

```bash
python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=.pycache python3 -m compileall app tests
git diff --check
git status --short
```

Output a Merge or Request Changes recommendation, then stop.

## Testing Standard

Every behavior-changing PR must include:

### Positive tests

The intended behavior works.

### Negative tests

Prohibited behavior does not occur.

Examples:

- Candidate rules do not enter formal generation.
- Missing confirmation does not approve a rule.
- Codex-created records are not shown as user decisions.
- Rejected or deprecated rules are excluded.

### Conflict tests

Inconsistent history or state is surfaced.

Examples:

- A rejected user decision conflicts with an approved current rule.
- Provenance points to an invalid source.
- A system resolver is presented as the user.

### End-to-end acceptance

Validate the user-visible loop using a temporary or real sample workspace.

## Codex Cost Discipline

1. For narrow repairs, do not re-read or redesign the whole repository.
2. Search for symbols and read/write paths before opening broad files.
3. Repair prompts should contain only:
   - current branch or commit
   - remaining defect
   - affected files
   - invariants to preserve
   - required tests
4. During development, run focused tests only.
5. Run the full suite once during Stage C.
6. Reference repository governance files instead of repeating long background.
7. Do not generate extra plans or documentation unless requested.
8. Stop after the current stage.

## Completion Report

Report:

1. Behavior implemented
2. Files changed
3. Invariants verified
4. Tests and results
5. End-to-end acceptance result
6. Known limitations
7. Commit SHA
8. Draft PR URL
9. Merge recommendation
