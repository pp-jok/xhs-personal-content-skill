# Skill Plan

## 已检查到的支撑能力

- `docx`：用于读取当前需求文档。
- `skill-installer`：用于检查和安装本地技能。
- `brainstorming`：适合需求澄清和设计阶段。
- `writing-plans`：适合把确认后的需求拆成可执行计划。
- `verification-before-completion`：适合完成阶段前运行测试和校验。
- `test-driven-development`：已安装到本机，当前会话重启后可直接作为测试优先的支撑流程。
- `systematic-debugging`：已安装到本机，后续排查测试或数据问题时使用。
- `using-superpowers`：已安装到本机，当前会话重启后可作为工作流纪律入口。

## 本阶段启用方式

当前会话已经可以使用文档读取、计划拆分和完成前校验相关能力。新安装的部分能力需要重启本地会话后才会出现在自动触发列表中。

本阶段采用项目内文档模拟以下支撑能力：

- Repository Understanding：通过 `docs/README.md` 和目录结构约束项目边界。
- Product Specification：通过 `docs/implementation-plan.md` 固化阶段范围。
- Data Modeling：通过 `app/models/core.py`、`docs/data-models.md` 和 JSON 示例定义模型协议。
- Prompt Contract：暂不实现，Phase 2 再写入 `prompts/`。
- Workflow Orchestration：暂不实现，Phase 3 再写入 `workflows/` 和 `app/workflows/`。
- Testing / QA：通过标准库测试覆盖模型和 JSON 仓库行为。

## 未启用项及原因

- 前端设计相关能力：第一轮禁止开发 UI。
- 部署相关能力：第一轮不发布服务。
- 浏览器自动化相关能力：第一轮没有可视化页面和浏览器流程。
- 外部服务集成相关能力：第一轮不接入抓取、发布或真实模型 API。
