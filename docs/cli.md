# CLI

## 目标

Phase 4 提供一个轻量命令行入口，用于手动导入 JSON、查看本地记录和运行本地工作流。

Phase 7 增加面向 Codex 操作流程的工作区命令。Codex 负责理解用户输入和生成内容，CLI 负责稳定写入、合并、校验和报告。

Phase 8 增加素材收件箱与单链接采集记录。CLI 只处理用户主动提供的单个链接和用户可见内容，不做批量抓取、平台级搜索、自动监控或绕过访问限制。

CLI 只读写本地 JSON 文件，不调用真实模型 API，不自动发布。

CLI 不替代 Codex 做高质量生成。`run-workflow` 和 `validate-real-sample` 中的生成链路仍主要用于本地流程验证。

## 运行方式

在项目目录执行：

```bash
python3 -m app.cli.main --help
```

## 全局参数

- `--data-dir`：JSON 数据目录，默认 `data/`。
- `--prompts-dir`：Prompt Contract 目录，默认 `prompts/`。

## 导入 JSON

```bash
python3 -m app.cli.main import-json creator-profiles data/examples/creator-profile.json
```

如需覆盖同 id 记录：

```bash
python3 -m app.cli.main import-json creator-profiles data/examples/creator-profile.json --upsert
```

## 列出记录

```bash
python3 -m app.cli.main list creator-profiles
```

## 查看单条记录

```bash
python3 -m app.cli.main show creator-profiles creator-main
```

## 初始化账号工作区

```bash
python3 -m app.cli.main init-workspace --workspace .xhs-personal-content-skill/real-sample
```

该命令会创建本地工作区目录、模型集合目录和报告目录，并返回缺失的必需样本。

## 写入或更新账号档案

```bash
python3 -m app.cli.main upsert-profile \
  --workspace .xhs-personal-content-skill/real-sample \
  --file /path/to/creator_profile.json
```

写入结果：

- 更新工作区单文件账号档案。
- 同步更新集合目录中的账号记录。

## 添加对标账号

```bash
python3 -m app.cli.main add-benchmark-account \
  --workspace .xhs-personal-content-skill/real-sample \
  --file /path/to/benchmark_account.json
```

输入文件可以是一个 JSON 对象，也可以是对象数组。相同 `id` 会更新，不会重复追加。

## 添加对标帖子

```bash
python3 -m app.cli.main add-benchmark-post \
  --workspace .xhs-personal-content-skill/real-sample \
  --file /path/to/benchmark_post.json
```

输入文件可以是一个 JSON 对象，也可以是对象数组。命令会校验字段并同步写入集合目录。

## 添加自定义标签

```bash
python3 -m app.cli.main add-custom-tags \
  --workspace .xhs-personal-content-skill/real-sample \
  --file /path/to/custom_tags.json
```

输入文件可以是一个 JSON 对象，也可以是对象数组。相同 `id` 会更新，不会重复追加。

## 记录用户反馈

```bash
python3 -m app.cli.main add-feedback \
  --workspace .xhs-personal-content-skill/real-sample \
  --file /path/to/validation_feedback.json
```

该命令会把新的 `issues` 追加到现有反馈中，适合记录“标题太 AI”“封面可以”“以后不要这样写”等用户偏好。

## 校验工作区

```bash
python3 -m app.cli.main validate-workspace --workspace .xhs-personal-content-skill/real-sample
```

输出包含：

- 是否满足真实样本验证的最低输入要求。
- 缺失的必需样本。
- 对标账号、对标帖子、标签和反馈问题数量。

## 添加素材收件箱链接

```bash
python3 -m app.cli.main add-inbox-item \
  --workspace .xhs-personal-content-skill/real-sample \
  --url "https://www.xiaohongshu.com/explore/xxxx" \
  --user-intent "学习选题和视频结构" \
  --user-reason "开头很吸引人" \
  --focus title \
  --focus structure
```

该命令会保存用户主动提供的单个链接。同一链接重复提交时会更新原记录，并返回 `deduplicated: true`。

## 采集单个链接可见内容

无手动内容时：

```bash
python3 -m app.cli.main capture-xhs-link \
  --workspace .xhs-personal-content-skill/real-sample \
  --inbox-item-id inbox-xxxx
```

该命令不会绕过登录、验证码、风控或访问限制。如果没有可见内容输入，会生成 `failed` 采集记录，并明确缺失字段。

使用人工复制或截图转写内容时：

```bash
python3 -m app.cli.main capture-xhs-link \
  --workspace .xhs-personal-content-skill/real-sample \
  --inbox-item-id inbox-xxxx \
  --manual-file /path/to/manual-capture.json
```

`manual-capture.json` 可以包含：

```json
{
  "title": "页面可见标题",
  "body": "页面可见正文",
  "content_type": "image",
  "author": {
    "name": "页面可见账号名"
  },
  "metrics": {
    "likes": null,
    "collects": null,
    "comments": null,
    "shares": null
  },
  "images": [],
  "video": {},
  "comments": []
}
```

缺失指标必须写 `null`，不要写 `0`。

## 查看采集结果

```bash
python3 -m app.cli.main show-capture-result \
  --workspace .xhs-personal-content-skill/real-sample \
  --capture-id capture-from-inbox-xxxx
```

输出包含标题、正文、作者、互动数据、图片、视频、评论、已获得字段、缺失字段和 warnings。

## 生成规则卡片

```bash
python3 -m app.cli.main generate-rule-cards \
  --workspace .xhs-personal-content-skill/real-sample \
  --creator-id creator-main \
  --benchmark-post-id benchmark-post-001
```

该命令使用本地 mock 链路分析一篇对标帖并落盘规则卡。它用于结构化验证，不代表最终内容质量。

## 生成选题

```bash
python3 -m app.cli.main generate-topics \
  --workspace .xhs-personal-content-skill/real-sample \
  --creator-id creator-main \
  --benchmark-post-id benchmark-post-001 \
  --topic-count 5
```

该命令会读取账号档案、标签、规则卡和指定对标帖，生成结构化选题记录。

## 生成草稿

```bash
python3 -m app.cli.main generate-draft \
  --workspace .xhs-personal-content-skill/real-sample \
  --topic-id topic-from-benchmark-post-001-1
```

该命令会生成标题、封面文案、脚本和简单分镜结构，适合用于验证落盘流程。高质量草稿仍应由 Codex 会话读取上下文后生成。

## 创建发布任务

```bash
python3 -m app.cli.main create-publish-task \
  --workspace .xhs-personal-content-skill/real-sample \
  --draft-id draft-from-topic-from-benchmark-post-001-1 \
  --planned-publish-time 2026-07-05T20:00:00+08:00
```

该命令只创建本地发布任务，不会自动发布。

## 复盘已发布内容

```bash
python3 -m app.cli.main review-own-post \
  --workspace .xhs-personal-content-skill/real-sample \
  --own-post-id own-post-001
```

该命令会生成本地复盘记录，并把复盘记录关联回已发布内容。

## 运行本地工作流

运行前需要先在 `data/` 中存在：

- `creator-profiles/<creator-id>.json`
- `benchmark-posts/<benchmark-post-id>.json`
- 至少可以为空目录的 `custom-tags/`

命令：

```bash
python3 -m app.cli.main run-workflow \
  --creator-id creator-main \
  --benchmark-post-id benchmark-post-001 \
  --planned-publish-time 2026-07-05T20:00:00+08:00 \
  --topic-count 1
```

输出包含：

- `rule_card_ids`
- `topic_ids`
- `draft_id`
- `publish_task_id`
- `warnings`

## 运行真实样本验证

准备 `data/real-sample/` 工作目录，并放入人工填写后的样本文件：

- `creator_profile.json`
- `benchmark_account.json`
- `benchmark_post.json`
- `custom_tags.json`

可选文件：

- `own_post.json`
- `weekly_publish_plan.json`
- `validation_feedback.json`

运行：

```bash
python3 -m app.cli validate-real-sample --workspace data/real-sample
```

也可以使用显式入口：

```bash
python3 -m app.cli.main validate-real-sample --workspace data/real-sample
```

输出报告：

- `data/real-sample/reports/validation_report.md`
- `data/real-sample/reports/human_review_form.md`

Phase 7 后，真实样本验证会处理多篇对标帖，并在报告中补充规则合并检查：

- 重复规则
- 冲突规则
- 低置信规则

## 可用 collection

- `creator-profiles`
- `benchmark-accounts`
- `benchmark-posts`
- `content-inbox`
- `capture-records`
- `custom-tags`
- `rule-cards`
- `topic-pool`
- `content-drafts`
- `publish-tasks`
- `own-posts`
- `review-records`
