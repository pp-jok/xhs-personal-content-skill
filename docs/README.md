# 小红书个人账号内容运营 Skill

## 项目定位

本项目面向单个小红书创作者，帮助其长期沉淀账号档案、对标内容、标签、规则卡片、选题、草稿、发布任务和复盘记录。

第一版的重点不是一次性生成文案，而是建立可成长、可迁移、可测试的数据基础，让后续的分析、规则提炼和内容生成都围绕同一个创作者账号持续改进。

## MVP 范围

当前本地 MVP 已完成 Phase 0 到 Phase 6：

- Phase 0：建立项目骨架、文档目录、数据目录和测试目录。
- Phase 1：实现核心数据模型、JSON 文件存储、基础校验、基础 CRUD 和测试样例。
- Phase 2：实现 Prompt Contract 和 mock 服务。
- Phase 3：实现本地“对标帖子到发布任务”工作流闭环。
- Phase 4：实现轻量 CLI。
- Phase 5：提供 Quickstart、端到端样例和测试。
- Phase 6：提供真实样本验证说明、模板、CLI 入口、验证报告和人工评价表。

## 核心数据对象

- `CreatorProfile`：创作者账号档案。
- `BenchmarkAccount`：对标账号。
- `BenchmarkPost`：对标帖子。
- `CustomTag`：自定义标签。
- `RuleCard`：规则卡片。
- `TopicItem`：选题。
- `ContentDraft`：内容草稿。
- `PublishTask`：发布任务。
- `OwnPost`：已发布帖子。
- `ReviewRecord`：复盘记录。

## 不做事项

- 不做通用内容生成器。
- 不引入无关外部竞品或品牌名称。
- 不开发完整 UI。
- 不接入真实小红书自动抓取。
- 不接入自动发布。
- 不接入真实大模型 API。
- 不做自动剪辑、自动生成图片或复杂数据看板。
- 不引入复杂数据库。

## 存储策略

第一版使用 JSON / Markdown 文件存储。每类模型独立存放在 `data/` 下的对应目录中，每条记录一个 JSON 文件，文件名使用记录 `id`。

这种设计便于人工检查、版本管理、测试夹具维护和后续迁移。

## 运行测试

在项目目录执行：

```bash
python3 -m unittest discover -s tests -v
```

## Phase 2：Prompt Contract

Prompt Contract 说明见 `docs/prompt-contracts.md`。协议文件位于 `prompts/`，mock 服务位于 `app/services/mock_prompt_service.py`。

## Phase 3：本地工作流

工作流说明见 `docs/workflows.md`。当前已实现从单篇对标帖子到发布任务的本地 mock 闭环。

## Phase 4：轻量 CLI

CLI 说明见 `docs/cli.md`。当前支持导入 JSON、列出记录、查看记录和运行本地工作流。

## Phase 5：端到端样例

从空数据目录开始的完整试运行说明见 `docs/quickstart.md`。该流程使用 `data/examples/` 中的最小样例数据，运行本地 mock 工作流，并生成规则卡片、选题、草稿和发布任务。

## Phase 6：真实样本验证

真实样本验证说明见 `docs/05-real-sample-validation.md`。模板位于 `data/templates/`，命令会在 `data/real-sample/reports/` 下生成验证报告和人工评价表。

## 新 Codex 项目中使用

安装到 Codex 后，在新项目中使用方式见 `docs/install-in-new-codex-project.md`。核心原则是：Skill 引擎在全局安装目录，账号数据保存在新项目本地工作区。

## 公开测试资料

- 仓库首页说明见根目录 `README.md`。
- 测试者操作手册见 `docs/user-manual.md`。
- 公开测试指南见 `docs/public-test-guide.md`。
