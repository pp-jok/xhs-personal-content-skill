# 老八小红书个人账号内容运营 Skill

这是一个面向单个创作者账号的 Codex Skill MVP。它不是通用文案生成器，而是用本地文件持续沉淀账号档案、对标内容、标签、规则卡片、选题、草稿、发布任务和复盘记录。

当前版本适合找测试者验证核心闭环：录入账号信息，持续添加对标帖子，沉淀个人偏好与规则，再基于这些积累生成选题、草稿和验证报告。

当前版本：`1.0.0`

## 核心价值

- 长期账号记忆：把账号定位、受众、风格、禁用表达和历史反馈保存在本地项目中。
- 对标样本沉淀：把对标账号和帖子拆成可借鉴点、不可借鉴点、风险和规则卡片。
- 可调教偏好：用户可以持续反馈“太 AI”“这个标题可以”“以后不要这样写”，并写入规则。
- 用户态引导：默认用账号运营助手的方式交流，少暴露文件、命令、JSON 和内部流程。
- 本地可控：只处理用户主动提供的单个链接和可见内容，不批量抓取平台，不自动发布，不调用外部模型 API，不依赖复杂数据库。
- 可验证闭环：提供 CLI、模板、样例和真实样本验证报告，便于多人测试和迭代。

## 当前功能

- `CreatorProfile`：创作者账号档案。
- `BenchmarkAccount`：对标账号。
- `BenchmarkPost`：对标帖子。
- `BenchmarkAnalysis`：采集内容拆解结果。
- `ContentInboxItem`：素材收件箱条目。
- `CaptureRecord`：单链接采集记录。
- `CustomTag`：自定义标签。
- `RuleCard`：规则卡片。
- `RuleEvidence`：规则证据。
- `TopicItem`：选题。
- `ContentDraft`：内容草稿。
- `PublishTask`：发布任务。
- `OwnPost`：已发布帖子。
- `ReviewRecord`：复盘记录。
- JSON 文件存储、基础校验、CRUD、测试样例。
- Prompt Contract 与 mock 服务。
- 本地“对标帖子 -> 规则卡片 -> 选题 -> 草稿 -> 发布任务”工作流。
- 真实样本验证命令与人工评价表。
- 工作区 CLI：初始化、账号档案、对标账号、对标帖子、标签、反馈、校验、规则、选题、草稿、发布任务和复盘。
- 单链接素材收件箱：保存用户主动提供的小红书链接，支持去重、采集状态和缺失字段记录。
- 采集内容拆解：把可见内容拆成事实、推断、不确定项、账号适配判断和候选规则引用。
- 提升为对标：运营人员确认后，可把采集内容提升为对标账号和对标帖子草稿。
- 规则生命周期：候选、确认、测试、验证、拒绝、废弃，并保留证据和验证次数。
- 低门槛录入元数据：缺失字段、置信度、来源说明和用户原因。
- 多篇对标帖验证：批量生成规则、选题、草稿和发布任务，并输出规则合并检查。

## 不做事项

- 不做完整 UI。
- 不做平台级爬虫、批量抓取、账号/话题遍历，且不绕过登录、验证码、风控或访问限制。
- 不做自动发布。
- 不接入真实大模型 API。
- 不做自动剪辑、自动生成图片或复杂数据看板。
- 不做多用户系统或商业化后台。
- 不把项目做成通用内容生成器。

## 安装到 Codex

克隆仓库后，把 Skill 目录复制到 Codex 的 skills 目录：

```bash
mkdir -p ~/.codex/skills
cp -R xhs-personal-content-skill ~/.codex/skills/xhs-personal-content-skill
```

重启 Codex 后，在任意新项目中使用触发词：

```text
小红书账号运营，初始化这个项目的账号工作区
```

新项目里的账号数据默认保存在：

```text
.xhs-personal-content-skill/real-sample/
```

## 快速试跑

```bash
cd xhs-personal-content-skill
python3 -m unittest discover -s tests
PYTHONPYCACHEPREFIX=.pycache python3 -m compileall -q app tests
```

运行样例闭环：

```bash
mkdir -p tmp/quickstart-data
python3 -m app.cli.main --data-dir tmp/quickstart-data import-json creator-profiles data/examples/creator-profile.json
python3 -m app.cli.main --data-dir tmp/quickstart-data import-json benchmark-posts data/examples/benchmark-post.json
python3 -m app.cli.main --data-dir tmp/quickstart-data import-json custom-tags data/examples/custom-tag.json
python3 -m app.cli.main --data-dir tmp/quickstart-data run-workflow --creator-id creator-main --benchmark-post-id benchmark-post-001 --planned-publish-time 2026-07-05T20:00:00+08:00 --topic-count 1
```

## 给测试者的入口

- 使用手册：`docs/user-manual.md`
- 测试者指南：`docs/public-test-guide.md`
- 新 Codex 项目安装说明：`docs/install-in-new-codex-project.md`
- CLI 说明：`docs/cli.md`
- 真实样本验证：`docs/05-real-sample-validation.md`
- 数据模型：`docs/data-models.md`
- 版本记录：`CHANGELOG.md`

## 适合怎样测试

最小测试集：

- 1 份真实账号档案。
- 1 到 3 个对标账号。
- 3 到 10 篇对标帖子。
- 可选：1 到 3 个用户主动提供的单个链接，用于验证素材收件箱和缺失字段提示。
- 5 到 20 个自定义标签或偏好反馈。

测试重点不是看一次生成是否惊艳，而是看它能否逐步学会账号偏好，并把对标样本转成可复用规则。

普通测试者不需要理解数据文件、命令或内部模型。只有在明确说“显示技术细节”时，Skill 才应该展示路径、命令和验证输出。
