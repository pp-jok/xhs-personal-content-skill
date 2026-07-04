# Phase 6：真实样本验证

## 目标

Phase 6 用真实人工样本验证本地 MVP 是否真正围绕单个创作者账号工作，而不是只在样例数据上跑通。

本阶段只做本地验证：人工收集样本、人工录入 JSON、运行本地 mock 工作流、生成验证报告和人工评价表。仍然不做 UI、真实平台抓取、自动发布、真实模型 API、复杂数据看板、多用户系统或商业化后台。

## 需要收集的真实样本

最小样本集：

- 1 份创作者账号档案。
- 1 到 3 个对标账号。
- 3 到 10 篇对标帖子。
- 5 到 20 个用户自定义标签。
- 可选：1 到 5 篇自己已发布帖子。
- 可选：一份未来一周发布计划。
- 可选：一份人工验证反馈。

建议优先收集少量但真实的样本。样本越贴近当前账号定位，验证结论越有价值。

## 如何录入样本

复制 `data/templates/` 下的模板到一个工作目录，例如 `data/real-sample/`：

- `creator_profile.template.json` 复制为 `creator_profile.json`
- `benchmark_account.template.json` 复制为 `benchmark_account.json`
- `benchmark_post.template.json` 复制为 `benchmark_post.json`
- `custom_tags.template.json` 复制为 `custom_tags.json`
- `own_post.template.json` 复制为 `own_post.json`
- `weekly_publish_plan.template.json` 复制为 `weekly_publish_plan.json`
- `validation_feedback.template.json` 复制为 `validation_feedback.json`

其中 `creator_profile.json`、`benchmark_post.json`、`custom_tags.json` 是运行验证流程的必需文件。其他文件会被读取并计入报告，但不会触发外部服务。

## 如何运行完整工作流

在项目目录执行：

```bash
python3 -m app.cli.main validate-real-sample --workspace data/real-sample
```

命令会按顺序执行：

1. 读取创作者账号档案。
2. 读取对标账号。
3. 读取对标帖子。
4. 读取用户标签。
5. 分析对标帖子。
6. 生成规则卡片。
7. 生成选题池。
8. 从选题生成内容草稿。
9. 创建发布任务。
10. 输出验证报告。

## 如何判断输出是否有效

先看 `data/real-sample/reports/validation_report.md`：

- 输入样本数量是否正确。
- 每一步是否成功。
- 规则卡片、选题、草稿、发布任务是否生成。
- 是否有 warnings 或缺失输入。

再看生成的 JSON 文件：

- `data/real-sample/rule-cards/`
- `data/real-sample/topic-pool/`
- `data/real-sample/content-drafts/`
- `data/real-sample/publish-tasks/`

有效输出应满足：

- 规则卡片能追溯到真实对标帖子。
- 选题贴合创作者账号定位。
- 草稿能被人工修改后使用。
- 发布任务材料清单明确。

## 需要人工评价的结果

请填写 `data/real-sample/reports/human_review_form.md`。重点评价：

- 选题是否适合账号。
- 标题是否可用。
- 封面标题是否可用。
- 视频逐字稿是否能录。
- 是否符合账号风格。
- 是否不像 AI。
- 是否有结果感。
- 是否接地气。
- 是否比通用内容生成更贴合个人账号。
- 是否愿意连续使用 2 周。

## 进入下一轮迭代的问题

以下问题应进入下一轮迭代：

- 样本字段不够表达真实账号情况。
- 标签难以覆盖真实使用偏好。
- 规则卡片太泛，不能指导后续生成。
- 选题不贴合账号定位或目标用户。
- 标题、封面文案、脚本需要大改才可用。
- 输出不像当前创作者本人会写的内容。
- 验证报告缺少决策所需信息。
- CLI 操作步骤仍然过多或容易出错。
