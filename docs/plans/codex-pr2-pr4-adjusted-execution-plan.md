# Codex Execution Plan: Adjusted PR-2 / PR-3 / PR-4

## Baseline

The repository already contains:

- Single user-provided link intake
- Content inbox
- Authorized Chrome/CDP capture
- HTML snapshot, screenshot, and diagnostics
- Manual fallback
- Captured-post analysis entry points
- Provenance, decisions, object versions, and active-rule selection

Do not rebuild these foundations.

## Execution Rule

For every PR:

1. Run Stage A only
2. Review Stage A
3. Run Stage B only
4. Review implementation
5. Run Stage C only
6. Merge
7. Stop

Never execute this file from beginning to end in one task.

---

## PR-2 — Capture Experience and Contract Audit

### Goal

Determine whether the existing single-link flow is understandable and recoverable for a non-technical user.

This is an audit-first task, not a new capture implementation.

### Stage A prompt

```text
Read and follow:

- AGENTS.md
- docs/architecture/invariants.md
- SKILL.md
- docs/plans/codex-pr2-pr4-adjusted-execution-plan.md

Execute only:

PR-2 — Capture Experience and Contract Audit, Stage A.

Do not modify code.
Do not create a branch.
Do not commit.
Do not create a PR.
Do not execute PR-3 or PR-4.

Inspect the complete user path:

user provides one link
→ inbox item
→ authorized Chrome/CDP capture
→ CaptureRecord
→ success, partial success, or failure recovery
→ manual fallback when required

Check:

1. All link-intake entry points
2. Inbox state transitions
3. CaptureRecord state transitions
4. CDP capture path
5. Manual fallback
6. Success and partial-success states
7. Login, verification, page-structure, and missing-content states
8. All user-visible messages
9. Leakage of CDP, Playwright, JSON, model names, paths, or CLI details
10. Recovery action for every failure state
11. Duplicate capture architecture or duplicated rendering logic
12. Provenance from inbox item to capture
13. Whether implementation is needed at all

Output:

A. User journey
B. Existing capability
C. Read paths
D. Write paths
E. State/failure matrix
F. UX defects
G. Architecture defects
H. Positive tests
I. Negative tests
J. Conflict tests
K. Expected changed files
L. Explicit non-goals
M. Final recommendation:
   - skip PR-2 and proceed to PR-3A
   or
   - implement a minimal PR-2 fix

Forbidden:

- HTTP provider
- Managed Browser
- new provider framework
- background queue
- batch capture
- OCR
- video analysis
- rule extraction
- generation

Stop after Stage A.
```

### Allowed Stage B scope

Only issues proven by Stage A, such as:

- plain-language status mapping
- consistent missing-information messages
- one minimal recovery action per failure
- hiding technical details
- consolidating duplicated result rendering
- repairing a provenance gap

---

## PR-3A — Evidence-First Post Analysis

### Goal

Analyze one captured or user-provided post while separating:

- observable facts
- Codex inference
- missing or uncertain evidence

### Stage A prompt

```text
Read and follow the repository governance files.

Execute only PR-3A Stage A.

Do not modify code.

Inspect current CaptureRecord, BenchmarkPost, BenchmarkAnalysis, prompt contracts, analysis services, and workflows.

The intended user output may include:

- title structure
- title hook
- keywords and emotional words
- body structure
- opening promise
- information density
- narrative path
- action guidance
- language style
- available cover/image evidence
- available video-structure evidence
- explicit missing information

All output must remain distinguishable as:

- 【客观数据】
- 【Codex 判断】
- 【信息不足】

Analyze:

1. Available source evidence
2. Fact fields
3. Inference fields
4. Unavailable fields
5. Current model suitability
6. Required model or contract changes
7. Provenance from capture to analysis
8. Prompt risks that may present inference as fact
9. All read paths
10. All write paths
11. Accidental rule creation or profile mutation
12. User-facing rendering
13. Positive, negative, and conflict tests
14. Expected changed files
15. Explicit non-goals
16. Whether a later minimal multimodal PR is actually needed

Do not include:

- account-fit assessment
- RuleCard creation
- user decision flow
- topic generation
- draft generation
- full OCR
- audio transcription
- full video segmentation

Stop after Stage A.
```

---

## Optional PR-3A.1 — Minimal Multimodal Evidence

Create this PR only when real PR-3A acceptance shows a specific evidence gap that cannot be solved through existing screenshot, HTML, or user-supplied material.

Allowed examples:

- cover-text OCR
- a small number of video keyframes
- extraction of already-visible subtitles

Do not build a general multimodal system.

---

## PR-3B — Account-Fit Assessment

### Goal

Classify analyzed elements as:

- directly borrowable
- adaptable
- not recommended
- risky
- insufficient information

### Stage A prompt

```text
Execute only PR-3B Stage A.

Inspect CreatorProfile, active-rule selection, BenchmarkAnalysis, user-context rendering, and all related readers.

Analyze:

1. Required account fields
2. Active rule states
3. Exclusion of candidate/rejected/deprecated rules
4. Missing-profile behavior
5. Output structure and rationale
6. Provenance and evidence
7. Suitable service boundary
8. CLI growth risk
9. All read paths
10. All write paths
11. Risk of profile mutation
12. Risk of automatic rule creation
13. Positive, negative, and conflict tests
14. Expected changed files
15. Explicit non-goals

Do not:

- modify CreatorProfile automatically
- create approved rules
- begin candidate-rule persistence
- generate topics or drafts

Stop after Stage A.
```

---

## PR-3C — Candidate Rule Proposal

### Goal

Create a small, evidence-backed, deduplicated set of candidate rules.

### Stage A prompt

```text
Execute only PR-3C Stage A.

Inspect RuleCard, RuleEvidence, DecisionRequest, ProvenanceRecord, feedback intake, lifecycle logic, duplicate handling, and active-rule selection.

Analyze:

1. Minimum conditions for proposing a rule
2. Whether one post is sufficient
3. Repeated evidence across posts
4. Existing user feedback as evidence
5. Prevention of content-specific promotion
6. Default maximum of 1–3 proposals
7. Duplicate detection
8. Updating an existing candidate
9. Cases where no rule should be created
10. Required reason, impact, and evidence
11. Batched user presentation
12. Exclusion from formal generation
13. Whether pending DecisionRequests should be created immediately
14. Provenance write path
15. All readers and writers
16. Positive, negative, and conflict tests
17. Expected changed files
18. Explicit non-goals

Forbidden:

- automatic approval
- automatic testing state
- many rules from one post
- keyword-only durable intent
- candidate use in formal generation
- beginning the user-decision UI

Stop after Stage A.
```

---

## PR-4A — User Decision Experience

### Goal

Support plain-language choices:

- use for future content
- use only for this content
- try once
- keep pending
- reject
- correct the interpretation

### Stage A prompt

```text
Execute only PR-4A Stage A.

Inspect DecisionRequest, RuleCard lifecycle, ProvenanceRecord, user-context rendering, active-rule selection, and current decision resolution.

Analyze:

1. Internal behavior for each user choice
2. Which choices change RuleCard.status
3. Task-local instructions
4. One-time candidate authorization
5. Authorization scope and audit evidence
6. Prevention of automatic durable activation
7. Batch decisions
8. Recommendation, reason, scope, and reversibility
9. State/history conflicts
10. User-facing terminology
11. All readers and writers
12. Positive, negative, and conflict tests
13. Expected changed files
14. Explicit non-goals

Do not create a second decision system.
Do not bypass DecisionRequest.
Do not use created_by as resolved_by.
Do not begin generation work.

Stop after Stage A.
```

---

## PR-4B — Central Generation Context

### Goal

Make every formal generation path use one centralized context assembler.

### Stage A prompt

```text
Execute only PR-4B Stage A.

Inspect CreatorProfile, RuleCard, active-rule selection, DecisionRequest, BenchmarkAnalysis, TopicItem, ContentDraft, all generation handlers, workflows, and prompt contracts.

Identify:

1. Every formal generation entry point
2. Current context assembly in each entry point
3. Divergent context behavior
4. Every RuleCard read path
5. Task-local candidate authorization
6. Full-history over-reading
7. Minimal assembler input
8. Unified assembler output
9. Context-size controls
10. Used-source recording
11. User-readable generation basis
12. Active-rule enforcement
13. CLI thinning opportunities
14. Positive, negative, and conflict tests
15. Expected changed files
16. Explicit non-goals

Default context may contain only:

- current account profile
- relevant active rules
- explicitly authorized task-local candidates
- current task requirements
- 1–3 selected references
- current local feedback
- necessary provenance summaries

Do not implement topic or draft generation in this PR.

Stop after Stage A.
```

---

## PR-4C — Persona-Aware Topic Generation

### Goal

Generate 3–5 account-fit topics and explain the basis for each.

Each topic should explain:

- why it fits the account
- which user problem it addresses
- which reference angle it adapts
- which active rules influenced it
- relevant risk

Do not generate drafts in this PR.

---

## PR-4D — Draft and One Focused Revision

### Goal

For one selected topic:

1. Generate one draft in one initial content format
2. Produce a concise quality diagnosis
3. Show the most important 1–3 issues
4. Let the user select one revision focus
5. Perform one focused revision

Do not:

- automatically rewrite repeatedly
- support multiple formats at once
- automatically approve durable rules
- publish automatically
- begin publish-task or review-loop work

---

## Generic Stage B Prompt

```text
Execute Stage B for the approved PR.

Read and follow:

- AGENTS.md
- docs/architecture/invariants.md
- the approved Stage A analysis

Implement only the approved scope.

Requirements:

1. Do not redesign approved decisions.
2. Do not expand into later PRs.
3. Prefer the expected files from Stage A.
4. Reuse existing repositories, lifecycles, selectors, provenance, and decisions.
5. Keep business logic out of app/cli/main.py where a service is appropriate.
6. Run focused tests during development.
7. Add positive, negative, and conflict tests.
8. Perform one end-to-end acceptance.
9. Create a dedicated feature branch.
10. Open a Draft PR.
11. Stop.

Report:

- behavior implemented
- files changed
- invariants preserved
- focused tests
- acceptance result
- known limitations
- commit SHA
- Draft PR URL
```

## Generic Stage C Prompt

```text
Execute Stage C for the current PR.

Compare the feature branch against main.

Verify:

1. Diff matches Stage A.
2. Every read path enforces invariants.
3. Every write path preserves invariants.
4. Provenance is not bypassed.
5. DecisionRequest is not bypassed.
6. Active-rule selection is not bypassed.
7. Actor fields are not confused.
8. User-facing output hides technical details.
9. No duplicate architecture was added.
10. Positive, negative, conflict, and end-to-end tests exist and pass.

Run once:

python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=.pycache python3 -m compileall app tests
git diff --check
git status --short

If defects exist, repair only the current PR scope.

Output:

A. Review conclusion
B. Blocking issues
C. Non-blocking issues
D. Invariant verification
E. Test results
F. Acceptance result
G. Changed files
H. Latest commit SHA
I. PR URL
J. Merge recommendation

Stop after Stage C.
```

## Immediate Instruction

Begin only with:

`PR-2 — Capture Experience and Contract Audit, Stage A`

If the audit proves that existing behavior already satisfies the contract, skip PR-2 and proceed later to PR-3A Stage A.
