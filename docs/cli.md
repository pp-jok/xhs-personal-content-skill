# CLI

## 目标

Phase 4 提供一个轻量命令行入口，用于手动导入 JSON、查看本地记录和运行本地工作流。

CLI 只读写本地 JSON 文件，不抓取外部内容，不调用真实模型 API，不自动发布。

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

## 可用 collection

- `creator-profiles`
- `benchmark-accounts`
- `benchmark-posts`
- `custom-tags`
- `rule-cards`
- `topic-pool`
- `content-drafts`
- `publish-tasks`
- `own-posts`
- `review-records`
