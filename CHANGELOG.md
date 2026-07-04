# Changelog

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
