# Changelog

## 1.1.0 - 2026-07-05

Phase 11：质量提升验证。

### Added

- 新增 `ContentQualityReview`，用于记录草稿或发布前后的人工质量评价。
- 新增质量指标计算：首轮通过率、平均修改次数、大改率、账号适配分、可发布分、标题重写率、脚本重写率、规则命中率和规则验证成功率。
- 新增 CLI：`add-quality-review`、`generate-quality-report`。
- 新增质量周报，回答有效规则、表现差规则、被否定表达、修改成本变化和下一轮样本需求。

### Changed

- 草稿可以保存最近一次质量评价摘要，便于后续判断内容是否越来越贴合账号。
- README、用户手册、CLI 文档、数据模型文档和公开测试指南补充质量复盘用法。

### Boundaries

- 不用生成数量冒充质量提升。
- 不自动把低分规则删除，仍需人工判断原因。
- 不接真实模型 API，不做 UI，不抓取平台内容，不自动发布。

## 1.0.0 - 2026-07-05

Phase 10：规则证据与生命周期。

### Added

- 新增 `RuleEvidence`，用于记录规则的来源片段、可见事实、推断和置信度。
- 扩展 `RuleCard` 生命周期字段：`status`、`strength`、`validation_count`、`success_count`、`failure_count`、`last_validated_at`、`applicable_content_types`、`applicable_audiences`、`conflicts_with`、`supersedes`、`deprecated_reason`。
- 新增规则生命周期 CLI：`create-rule-from-analysis`、`approve-rule`、`mark-rule-testing`、`record-rule-result`、`reject-rule`、`deprecate-rule`。
- 新增 `check-rule-relations`，用于区分重复规则、适用场景不同的规则和需要人工解释的冲突规则。

### Changed

- 旧规则卡默认保持 `approved`，避免破坏 0.9.0 之前的工作区。
- 规则冲突判断不再使用“同类型不同摘要即冲突”的简单逻辑，会先识别重复和场景差异。

### Boundaries

- 不自动删除冲突规则。
- 不自动把候选规则视为已验证规则。
- 冲突规则需要交给 Codex 和运营人员解释后处理。

## 0.9.0 - 2026-07-05

Phase 9：采集内容结构化拆解与提升为对标。

### Added

- 新增 `BenchmarkAnalysis`，用于保存采集内容的事实、推断、不确定项、账号适配判断和候选规则引用。
- 新增 `app.analysis` 分析模块，支持图文和视频使用不同分析模板。
- 新增 CLI：`analyze-captured-post`、`promote-to-benchmark`。
- 新增采集内容提升为 `BenchmarkAccount` 与 `BenchmarkPost` 的本地流程。
- 新增 BenchmarkAnalysis 示例、集合目录和测试。

### Changed

- 采集内容现在可以先拆解，再由运营人员确认是否提升为正式对标样本。
- 文档补充事实与推断分离、公开互动数据仅作表现参考、缺失项保留为不确定项的边界。

### Boundaries

- Phase 9 不做 OCR、音频转写、关键帧抽取或真实多媒体处理。
- 不把公开互动数据解释为确定的爆款原因。
- 不自动把任意链接变成强对标，提升为对标仍需要用户确认。

## 0.8.0 - 2026-07-05

Phase 8：素材收件箱与指定链接采集。

### Added

- 新增 `ContentInboxItem`，用于保存用户主动提供的单个小红书链接、学习意图、关注点、采集状态和缺失字段。
- 新增 `CaptureRecord`，用于保存单链接当前可见内容的标准化采集结果。
- 新增 `app.capture` 本地采集模块，支持手动可见内容标准化，不绕过平台访问限制。
- 新增 CLI：`add-inbox-item`、`capture-xhs-link`、`show-capture-result`。
- 新增素材收件箱与采集记录示例、模板和测试。

### Changed

- `SKILL.md` 边界调整为：允许处理用户主动提供的单个公开链接及用户授权环境中可见内容；仍禁止批量抓取、平台级搜索、自动监控和绕过访问限制。
- README、CLI 文档、数据模型文档和测试指南补充 Phase 8 用法。

### Boundaries

- 不做平台级爬虫。
- 不批量遍历账号、话题或搜索结果。
- 不绕过登录、验证码、风控或访问限制。
- 不自动发布。
- 不接第三方大模型 API。

## 0.7.0 - 2026-07-04

Phase 7：Codex 本地运营流程固化。

### Added

- 新增工作区 CLI：`init-workspace`、`upsert-profile`、`add-benchmark-account`、`add-benchmark-post`、`add-custom-tags`、`add-feedback`、`validate-workspace`。
- 新增结构化产物 CLI：`generate-rule-cards`、`generate-topics`、`generate-draft`、`create-publish-task`、`review-own-post`。
- 所有模型支持低门槛录入元数据：`missing_fields`、`confidence`、`source_type`、`source_note`、`user_reason`、`created_from`。
- 用户反馈可沉淀为规则卡片，用于后续偏好调教。
- 真实样本验证支持多篇对标帖，并输出重复规则、冲突规则和低置信规则检查。

### Changed

- `SKILL.md` 增强为更硬的 Codex 操作流程：每个场景明确读取、提取、写入、缺失判断和用户态回复。
- CLI 文档补充 Phase 7 工作区命令和边界说明。

### Boundaries

- 不接真实模型 API。
- 不做 UI。
- 不抓取平台内容。
- 不自动发布。

## 0.6.0 - 2026-07-04

- 发布公开测试版。
- 增加用户态交流约束，默认隐藏工程细节。
- 增加使用手册和公开测试指南。

## 0.5.0 - 2026-07-04

- 完成 Phase 0 到 Phase 6 MVP。
- 支持数据模型、JSON 存储、CRUD、Prompt Contract、mock 工作流、CLI、Quickstart 和真实样本验证。
