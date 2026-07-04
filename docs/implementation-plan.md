# Implementation Plan

## Phase 0：项目骨架

- 创建 `docs/`、`data/`、`prompts/`、`workflows/`、`app/`、`tests/`。
- 在 `docs/` 中维护项目定位、阶段计划和支撑能力说明。
- 先保留 `prompts/` 和 `workflows/` 为空目录，后续 Phase 2 再定义结构化协议。

## Phase 1：数据模型与 JSON 存储

- 用标准库 Python 实现 10 个核心模型。
- 每个模型提供字段定义、基础校验、序列化和反序列化能力。
- 用通用 JSON 仓库实现创建、读取、更新、删除和列表读取。
- 用测试覆盖模型校验、序列化、目录映射和 CRUD。
- 用 `data/examples/` 保存每个模型的 JSON 示例。

## Phase 2：Prompt Contract

- 为每个 Prompt 定义目的、输入 JSON、输出 JSON、约束、质量标准和失败处理。
- 输出必须是可解析 JSON，不输出不可解析的长文本。
- 所有生成类协议必须引用账号档案、标签和规则卡片。
- 先实现 mock 服务，不接真实模型 API。
- 当前已完成：6 个协议文件、协议校验器、mock 服务和测试。

## Phase 3：核心工作流

- 添加对标账号和对标帖子。
- 对帖子进行结构化分析。
- 从分析结果提取规则卡片候选。
- 生成选题池。
- 从选题生成内容草稿。
- 从草稿创建发布任务。
- 当前已完成：基于已有账号档案、对标帖子和标签的本地 mock 闭环。

## Phase 4：轻量入口

- 在数据和工作流稳定后，再补充 CLI 或轻量入口。
- 不在第一轮开发 UI。
- 当前已完成：轻量 CLI，支持导入 JSON、列出记录、查看记录和运行本地工作流。

## Phase 5：样例与端到端验证

- 补充测试数据。
- 增加端到端测试。
- 完善使用说明和迁移说明。
- 当前已完成：从空数据目录开始的 quickstart、最小样例闭环和端到端测试。

## Phase 6：真实样本验证

- 收集真实创作者账号档案、对标账号、对标帖子和用户标签。
- 使用 `data/templates/` 中的模板人工录入样本。
- 运行 `validate-real-sample` 本地验证命令。
- 生成 `reports/validation_report.md` 和 `reports/human_review_form.md`。
- 当前已完成：验证说明文档、模板、CLI 入口、报告生成和测试。
