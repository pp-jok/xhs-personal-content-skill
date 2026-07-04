# Workflows

## Phase 3：对标内容到发布任务闭环

当前已实现 `BenchmarkToPublishWorkflow`，用于跑通本地闭环：

1. 读取创作者账号档案。
2. 读取一篇对标帖子。
3. 读取自定义标签。
4. 调用 mock 协议分析对标帖子。
5. 更新对标帖子的分析字段。
6. 从分析结果提取规则卡片并写入 `data/rule-cards/`。
7. 基于账号档案、规则卡片和参考帖子生成选题并写入 `data/topic-pool/`。
8. 从选题生成草稿并写入 `data/content-drafts/`。
9. 从草稿创建发布任务并写入 `data/publish-tasks/`。

## 输入

- `creator_profile_id`：主账号档案 id。
- `benchmark_post_id`：要分析的对标帖子 id。
- `planned_publish_time`：计划发布时间字符串。
- `topic_count`：生成选题数量，当前 mock 服务最多生成 5 个。

## 输出

`BenchmarkToPublishResult` 包含：

- 更新后的 `BenchmarkPost`。
- 新增或更新的 `RuleCard` 列表。
- 新增或更新的 `TopicItem` 列表。
- 新增或更新的 `ContentDraft`。
- 新增或更新的 `PublishTask`。
- `warnings` 列表。

## 边界

当前工作流只使用本地 JSON 文件和 mock 服务。

它不会：

- 抓取真实平台内容。
- 调用真实模型 API。
- 自动发布内容。
- 开发 UI。
- 替代人工审核。

## 重复运行策略

工作流使用固定派生 id，并通过 `upsert` 写入结果。重复运行同一篇对标帖子时，会更新同一组派生记录，便于人工检查差异和后续迁移。
