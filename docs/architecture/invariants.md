# Architecture Invariants

## Purpose

This document defines stable product and domain rules for the long-term Xiaohongshu account operations Skill.

These invariants apply to models, services, workflows, CLI handlers, prompt contracts, tests, and user-facing output.

## 1. Authority Boundaries

| Concern | Source of truth |
|---|---|
| Current business state | Current domain object, such as `RuleCard.status` |
| User decision fact | Resolved `DecisionRequest` and its resolver |
| Origin and explanation | `ProvenanceRecord` |
| Historical change | `ObjectVersion` |

Do not make multiple models independently authoritative for the same fact.

## 2. Trust Layers

Keep these layers separate:

1. Existing user/account data
2. Observable facts
3. Codex inference
4. Generated artifacts
5. Pending choices
6. User decisions
7. Change history

No layer may silently impersonate another.

User-facing output should preserve the distinctions already defined in `SKILL.md`, including:

- `【已有资料】`
- `【规则约束】`
- `【客观数据】`
- `【Codex 判断】`
- `【Codex 生成】`
- `【需要你决定】`
- `【已由你决定】`
- `【信息不足】`

## 3. Rule Activation

Formal generation may use only:

- `approved`
- `testing`
- `validated`

Formal generation must exclude by default:

- `candidate`
- `rejected`
- `deprecated`

A candidate may be used only through an explicit task-scoped or one-time experimental authorization.

One-time use must:

1. Be recorded
2. Be visible in task context
3. Not change the long-term status automatically
4. Not be described as an approved rule

## 4. Rule Intake

### Explicit durable instruction

A durable rule may be approved directly only when explicit user confirmation is represented structurally and auditably.

### Inferred preference

Codex inference creates a candidate rule.

### Content-specific feedback

Feedback about one topic, draft, or post remains local unless separately promoted and confirmed.

### Uncertain input

Uncertain classification uses a safe default and does not approve anything.

Keywords such as “长期” or “以后不要” are not sufficient by themselves to establish structured confirmation.

## 5. Actor Semantics

- `created_by`: who created the record
- `resolved_by`: who made the decision
- `changed_by`: who changed a versioned object
- provenance `actor`: who or what produced the source relationship or interpretation

These fields are not interchangeable.

A rule is “decided by the user” only when:

- a resolved decision has `resolved_by=user`, or
- explicit user decision provenance exists

## 6. Decision Consistency

| Current rule status | Compatible decision |
|---|---|
| approved / testing / validated | confirmed |
| rejected | rejected |
| deprecated | cancelled or superseded |
| candidate | pending or no resolved decision |

Incompatible state and history must be surfaced as a conflict or `【信息不足】`.

The system must not silently rewrite history or claim that the user made a decision they did not make.

## 7. Provenance Integrity

Every provenance record must reference valid target and source objects and, where applicable, a valid source version.

Business writes must use the centralized provenance validation/save path.

Provenance explains origin. It does not override current domain status.

## 8. Versioning

`ObjectVersion` stores historical snapshots.

It is not the source of current state.

Versioning should be limited to objects whose evolution materially affects future behavior.

## 9. Capture and Evidence

1. Capture only user-provided or user-visible content.
2. Do not infer missing metrics, comments, media, author facts, or platform state.
3. Capture success does not imply benchmark suitability.
4. Capture evidence must remain separate from semantic analysis.
5. Analysis must distinguish observable evidence, inference, and uncertainty.
6. Public metrics must not be treated as proof of causal success.

## 10. User Interaction

Normal users should speak naturally.

They should not need to understand:

- model names
- JSON fields
- internal status values
- repository paths
- CLI commands
- provenance schemas

Durable or high-impact choices should be presented as plain outcomes, such as:

- Confirm for future use
- Use only for this content
- Try once
- Keep pending
- Reject
- This is not what I meant

Every durable decision request should explain:

1. Recommendation
2. Reason
3. Affected scope
4. Whether it can be changed later

## 11. Decision Burden

Not every uncertainty requires immediate user interruption.

- Low impact: use a safe, reversible default
- Medium impact: batch and summarize
- High or durable impact: request explicit confirmation

Candidate rules should be grouped when possible. Avoid producing large numbers of pending decisions from one post.

## 12. Context Assembly

All formal generation paths must eventually use one centralized context assembly mechanism.

The context should include only relevant information:

- current account profile
- relevant active rules
- explicitly authorized task-local candidate rules
- current task requirements
- selected references
- current local feedback
- necessary source summaries

Do not load all historical objects by default.

## 13. Completion Standard

A feature is complete only when:

1. The model supports it
2. All writers preserve invariants
3. All readers enforce invariants
4. User-facing behavior is understandable
5. Positive tests pass
6. Negative tests pass
7. Conflict tests pass
8. One end-to-end scenario confirms the intended behavior
