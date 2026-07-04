---
name: xhs-personal-content-skill
description: Use when the user wants to operate a single Xiaohongshu creator account over time: record account profile, add benchmark accounts/posts, tag preferences, analyze benchmark content, extract rule cards, generate topic ideas, draft titles/cover text/video scripts, create publish tasks, review posted content, or validate real samples. Trigger on phrases such as 小红书账号运营, 小红书 Skill, 添加对标帖, 分析对标账号, 生成选题, 生成草稿, 创建发布任务, 复盘内容, 更新我的偏好, 真实样本验证.
---

# 小红书个人账号内容运营 Skill

Operate a single creator account as a long-term local workflow. The user should talk naturally; JSON is internal storage.

## Hard Boundaries

- Do not build UI.
- Do not scrape Xiaohongshu or any external platform.
- Do not auto-publish.
- Do not call or configure external model APIs.
- Do not turn this into a generic content generator.
- Do not introduce unrelated third-party competitor or brand names.
- Use local JSON / Markdown files as storage.
- Treat benchmark accounts/posts as continuous inputs; quality improves through accumulated samples, tags, rules, and reviews.

## Project Paths

Use two separate locations:

- Skill engine: the installed skill folder, usually `~/.codex/skills/xhs-personal-content-skill/`.
- Project workspace: the current Codex project folder.

Store user/account data in the project workspace, not in the global installed skill folder.

Default project-local data workspace:

- `.xhs-personal-content-skill/real-sample/`

If the current project already contains `xhs-personal-content-skill/`, use its `data/real-sample/` while developing the skill itself. Otherwise create/use `.xhs-personal-content-skill/real-sample/`.

Run CLI from the skill engine:

```bash
cd ~/.codex/skills/xhs-personal-content-skill
python3 -m app.cli validate-real-sample --workspace /absolute/path/to/project/.xhs-personal-content-skill/real-sample
```

When working inside this source repository, this shorter form is valid:

```bash
python3 -m app.cli validate-real-sample --workspace data/real-sample
```

Docs for details:

- `docs/cli.md`
- `docs/data-models.md`
- `docs/prompt-contracts.md`
- `docs/workflows.md`
- `docs/05-real-sample-validation.md`

## Triggered Conversation Workflows

### 1. 录入或更新账号档案

Trigger examples:

- “小红书账号运营，更新我的账号档案”
- “账号名是 X，定位是...”

Action:

1. Extract `CreatorProfile` fields from the user message.
2. Ask at most 3 clarifying questions only if required fields are missing.
3. Write or update `<project-local-workspace>/creator_profile.json`.
4. Summarize the stored profile and any uncertainty.

### 2. 添加对标账号

Trigger examples:

- “添加这个对标账号”
- “这个账号值得对标”

Action:

1. Extract account name, URL, niche, reason to follow, learnable points, non-learnable points, tags, and summary.
2. If only a link is provided, ask the user for why this account is worth learning unless already inferable from surrounding context.
3. Write or update `<project-local-workspace>/benchmark_account.json`.

### 3. 添加对标帖子

Trigger examples:

- “添加这篇对标帖”
- “分析这个截图”
- “这篇小红书帖子可以对标”

Action:

1. Extract title, cover text, raw content, visible metrics, tags, and source account.
2. When the user provides an image, inspect it and transcribe only visible content. Do not invent missing text or metrics.
3. Write or update `<project-local-workspace>/benchmark_post.json`.
4. If account info is available, also update `benchmark_account.json`.

### 4. 运行真实样本验证

Trigger examples:

- “跑一下验证”
- “真实样本验证”
- “看看现在结果怎么样”

Action:

Run:

```bash
cd ~/.codex/skills/xhs-personal-content-skill
python3 -m app.cli validate-real-sample --workspace /absolute/path/to/project/.xhs-personal-content-skill/real-sample
```

Then read and summarize:

- `<project-local-workspace>/reports/validation_report.md`
- `<project-local-workspace>/reports/machine_validation_findings.md` if present
- generated rule cards, topics, drafts, and publish tasks when relevant

### 5. 生成选题 / 草稿 / 发布任务

Trigger examples:

- “根据我的账号生成选题”
- “根据这个选题生成草稿”
- “创建发布任务”

Action:

Use stored account profile, tags, benchmark posts, and rule cards. Prefer accumulated rules over one-off generic advice. If current output still comes from `MockPromptService`, clearly say it is for pipeline validation, not final content quality.

### 6. 更新偏好和规则

Trigger examples:

- “这个标题太 AI”
- “这个封面可以”
- “以后不要这样写”
- “这个规则适合我”

Action:

1. Convert user feedback into tags, rule-card notes, or `validation_feedback.json` issues.
2. Preserve the original source and reason.
3. Prefer updating existing rules over creating duplicates.

### 7. 复盘已发布内容

Trigger examples:

- “复盘这篇内容”
- “这篇发布后数据是...”

Action:

1. Record `OwnPost` and `ReviewRecord` data.
2. Extract lessons, next actions, and rule updates.
3. Keep future generation tied to the creator profile and rule cards.

## CLI Commands

List records:

```bash
python3 -m app.cli list creator-profiles
```

Show one record:

```bash
python3 -m app.cli show creator-profiles creator-main
```

Run the local benchmark-to-publish workflow:

```bash
python3 -m app.cli run-workflow --creator-id creator-main --benchmark-post-id benchmark-post-001 --planned-publish-time 2026-07-05T20:00:00+08:00 --topic-count 1
```

Run Phase 6 validation:

```bash
python3 -m app.cli validate-real-sample --workspace data/real-sample
```

## Output Discipline

When completing a user request:

- Tell the user which files changed.
- Tell them whether the result is production content or only pipeline validation.
- If tests or validation were run, include exact commands and results.
- If critical information is missing, state the missing fields and provide a minimal fill-in format.

Before claiming completion, run relevant verification:

```bash
python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=.pycache python3 -m compileall app tests
```
