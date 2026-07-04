# Quickstart

## 目标

从一个空数据目录开始，导入最小样例数据，并运行“对标帖子到发布任务”的本地闭环。

本流程只读写本地 JSON 文件，不抓取真实平台内容，不调用真实模型 API，不自动发布。

## 1. 进入项目目录

```bash
cd xhs-personal-content-skill
```

## 2. 准备空数据目录

任选一个目录作为本次试运行的数据目录，例如：

```bash
mkdir -p tmp/quickstart-data
```

## 3. 导入最小样例数据

导入主账号档案：

```bash
python3 -m app.cli.main --data-dir tmp/quickstart-data import-json creator-profiles data/examples/creator-profile.json
```

导入对标帖子：

```bash
python3 -m app.cli.main --data-dir tmp/quickstart-data import-json benchmark-posts data/examples/benchmark-post.json
```

导入自定义标签：

```bash
python3 -m app.cli.main --data-dir tmp/quickstart-data import-json custom-tags data/examples/custom-tag.json
```

## 4. 确认数据已导入

```bash
python3 -m app.cli.main --data-dir tmp/quickstart-data list creator-profiles
python3 -m app.cli.main --data-dir tmp/quickstart-data list benchmark-posts
python3 -m app.cli.main --data-dir tmp/quickstart-data list custom-tags
```

## 5. 运行本地工作流

```bash
python3 -m app.cli.main \
  --data-dir tmp/quickstart-data \
  run-workflow \
  --creator-id creator-main \
  --benchmark-post-id benchmark-post-001 \
  --planned-publish-time 2026-07-05T20:00:00+08:00 \
  --topic-count 1
```

## 6. 查看生成结果

查看规则卡片：

```bash
python3 -m app.cli.main --data-dir tmp/quickstart-data list rule-cards
```

查看选题：

```bash
python3 -m app.cli.main --data-dir tmp/quickstart-data list topic-pool
```

查看草稿：

```bash
python3 -m app.cli.main --data-dir tmp/quickstart-data list content-drafts
```

查看发布任务：

```bash
python3 -m app.cli.main --data-dir tmp/quickstart-data list publish-tasks
```

## 生成文件

工作流会写入：

- `tmp/quickstart-data/rule-cards/rule-card-from-benchmark-post-001-1.json`
- `tmp/quickstart-data/topic-pool/topic-from-benchmark-post-001-1.json`
- `tmp/quickstart-data/content-drafts/draft-from-benchmark-post-001-1.json`
- `tmp/quickstart-data/publish-tasks/publish-task-from-benchmark-post-001-1.json`

## 下一步人工检查

运行完成后，建议人工检查：

- 对标帖子分析是否贴合主账号定位。
- 规则卡片是否适合长期复用。
- 选题是否具体、有目标、有来源。
- 草稿是否避开账号禁用表达。
- 发布任务材料清单是否足够执行。
