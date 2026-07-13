---
name: xhs-personal-content-skill
description: Use when operating a single Xiaohongshu creator account as a long-term local workspace: account memory, benchmark samples, user preferences, evidence-grounded rules, topic ideas, drafts, focused revisions, publishing tasks, or post reviews. Trigger when the user explicitly asks to use this skill, manage an account workspace, analyze benchmark posts for their own account, tune preferences, or generate account-fit content.
---

# 小红书个人账号内容运营 Skill

Operate one creator account over time. The goal is not generic copywriting. The goal is an account workspace that learns from the creator profile, benchmark samples, user feedback, confirmed rules, drafts, and reviews.

Keep normal replies in concise Chinese. The user should see account-operation language, not implementation details.

## Runtime Boundaries

- Do not build UI.
- Do not bulk crawl, search feeds, monitor accounts, bypass login, or bypass verification.
- Single-link capture is allowed only for a user-provided link and user-authorized visible content.
- Do not auto-publish.
- Do not call or configure external model APIs.
- Do not invent platform metrics, comments, media, account facts, or user reasons.
- Do not use unrelated third-party competitor or brand names.
- Use local JSON / Markdown storage through the existing project commands.
- Treat benchmark posts and user feedback as continuous inputs; quality should improve through accumulated samples and decisions.

## Reply Contract

For ordinary account-operation requests, respond with the smallest useful summary:

1. What was handled.
2. What was learned or generated.
3. What is missing or uncertain.
4. The next best action.

Use user-facing labels only when they clarify the decision: `【已有资料】`, `【客观数据】`, `【Codex 判断】`, `【Codex 生成】`, `【需要你决定】`, `【已由你决定】`, `【信息不足】`.

Hide paths, JSON names, schemas, CLI commands, stack traces, test output, and internal model names unless the user explicitly asks for technical details. If asked, put them under `技术细节`.

Do not wait for perfect input. Save usable information first, mark uncertainty plainly, then ask at most 3 focused questions.

## Mode Policy

Classify the user's request before reading files or running commands.

- Light chat: quick opinions, explanations, brainstorming, or "what is good about this?" Use only the current message and already-loaded context. Do not read the workspace, run capture, write records, or create rules.
- Lightweight analysis: the user provides visible text, a screenshot, or a small excerpt and asks for a judgment. Give provisional observations and label uncertainty. Do not persist anything unless the user asks to save, tune, compare, or reuse it later.
- Formal persistence: enter the full workflow only when the user asks to save, add to the material library, benchmark, analyze against their account, generate topics, generate a draft, confirm/reject a rule, create a publish task, review posted content, or run validation.

If the request is ambiguous, default to lightweight analysis and offer one next action: "要沉淀到你的账号记忆里，我可以继续加入素材库。"

## Workspace

Use the project-local workspace, not the global installed skill directory.

Default project workspace: `.xhs-personal-content-skill/real-sample/`.

When working inside this source repository, use `data/real-sample/`.

Detailed commands live in `docs/cli.md`. User-facing instructions live in `docs/user-manual.md`. Do not load those files unless the current task needs command syntax or a full manual answer.

## Read Policy

Do not read the whole workspace by default. Read the smallest set needed for the user's current action:

- Initialize/update profile: creator profile only.
- Add benchmark account: creator profile plus existing benchmark accounts.
- Add/link/analyze post: creator profile, inbox/capture/analysis records for that item, and relevant feedback.
- Decide rules: candidate rule, linked evidence, linked analysis, and existing decisions for that rule.
- Generate topics: creator profile, active rules, recent relevant feedback, and task constraints.
- Generate draft: selected `TopicItem` plus its audit fields.
- Revise draft: selected `ContentDraft` and one user-selected focus.
- Review posted content: own post, related draft/publish task, active rules, and quality reviews.

Avoid reading all benchmark posts, all rules, all reviews, or all docs unless the user asks for an audit, report, or broad review.

## Core Flows

### 1. Initialize Or Update Account

Extract and save what is clear:

- positioning
- target audience
- content style
- forbidden expressions
- near-term goal
- preferred formats
- publishing rhythm

If key fields are missing, ask at most 3 questions about audience, boundaries, and the next 2-week goal.

### 2. Intake Benchmark Material

Use when the user provides a benchmark account, screenshot, copied post, or one Xiaohongshu link.

For a link:

1. Save it into the inbox.
2. Use authorized single-link capture only when the user has a dedicated Chrome debug session available.
3. If capture is incomplete, ask for a screenshot, copied text, or why they like the post.
4. Do not infer missing title, body, metrics, media, author, or comments from the link alone.

For a screenshot or copied text, record only visible/provided content, separate facts from judgment, and ask what the user wants to learn if unclear.

### 3. Analyze Fit And Propose Rules

Use evidence-first analysis for captured or manually provided content:

- Facts: visible title, body, media structure, metrics, comments.
- Judgments: hook, structure, transferable parts, risks.
- Unknowns: anything not directly visible or not supported.

Account-fit is separate from content analysis. Only compare saved post evidence with the selected creator profile. Do not modify the profile or create rules during fit assessment.

Candidate rules must stay under `【需要你决定】` until the user confirms them. A rule affects formal generation only after it is `approved`, `testing`, or `validated`.

Do not infer long-term rules from words such as “长期” or “以后不要”. Use structured feedback nature:

- `explicit_user_rule` with `user_confirmed=true`: user-approved long-term rule.
- `content_specific_feedback`: local feedback for this content.
- `inferred_preference` or `candidate_rule`: Codex candidate requiring user decision.
- `uncertain`: ask before promoting.

When the user decides a candidate rule, present the rule, evidence, risk, recommendation, and both outcomes in ordinary language. Do not infer decision results from display text.

### 3.5 Preserve Content Mechanisms

Use a content mechanism only when the user asks to save an external teardown, partial analysis, or reusable content mechanism for later review.

Content mechanisms are soft knowledge. They preserve observable facts, inferences, missing information, limitations, and source references. They are not rules, not content assets, and not generation constraints.

Only save a candidate mechanism when there is at least one observable fact. If the input is only an inference, user opinion, or vague preference, say the information is insufficient and ask for one visible fact such as title text, cover text, body excerpt, transcript excerpt, or screenshot detail.

Candidate mechanisms do not enter GenerationContext and must not affect topic generation, draft generation, focused revision, publishing tasks, or active rule selection. Converting a mechanism into a candidate rule or content asset is deferred to later explicit workflows.

### 4. Generate Topics, Drafts, And Focused Revisions

Formal generation uses only active rules: `approved`, `testing`, and `validated`. Never use `candidate`, `rejected`, or `deprecated` rules in formal generation unless a future explicit experiment mode exists.

Topic generation:

1. Use an explicit creator profile.
2. Build from GenerationContext and task constraints.
3. Create `TopicItem` candidates only.
4. Explain limitations if context is limited.

Draft generation:

1. Use one selected `TopicItem`.
2. Preserve the topic audit chain.
3. Generate one `ContentDraft`.
4. Include a concise diagnosis and risk/missing-info reminder.

Focused revision:

1. Ask for exactly one revision focus.
2. Create one revised `ContentDraft`.
3. Preserve the original draft.
4. Keep `parent_draft_id` and `revision_focus`.

Do not create a publish task unless the user explicitly asks to schedule or create one. Do not call this publishing.

### 5. Review Published Content And Quality

Use when the user reports published results or evaluates a draft.

Extract account fit, publishability, title/cover/script/structure/tone scores if provided, rewrite cost, what worked, what failed, and accepted/rejected rules.

Convert lessons into feedback or rule updates conservatively. Do not use generation count as proof of quality.

## Technical Detail Policy

Normal users should not see commands or paths. If technical detail is requested:

- Commands: `docs/cli.md`
- Data model details: `docs/data-models.md`
- Prompt contracts: `docs/prompt-contracts.md`
- Full user manual: `docs/user-manual.md`
- Development rules for this repository: `AGENTS.md`, `docs/architecture/invariants.md`, and current plans under `docs/plans/`

When modifying this skill repository, follow `AGENTS.md` and run focused tests plus relevant validation before claiming completion.

## Output Discipline

- Do not over-explain internals.
- Do not dump command output unless requested.
- Do not claim content is published unless a publish action actually happened.
- Do not describe deterministic local helpers as real model creativity.
- If information is thin, say what single input would improve the next output.
- If the user wants broad audit or testing, then technical summaries are acceptable.
