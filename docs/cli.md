# CLI

## 目标

Phase 4 提供一个轻量命令行入口，用于手动导入 JSON、查看本地记录和运行本地工作流。

Phase 7 增加面向 Codex 操作流程的工作区命令。Codex 负责理解用户输入和生成内容，CLI 负责稳定写入、合并、校验和报告。

Phase 8 增加素材收件箱与单链接采集记录。CLI 只处理用户主动提供的单个链接和用户可见内容，不做批量抓取、平台级搜索、自动监控或绕过访问限制。

Phase 12 增加用户授权 Chrome 单链接采集。无 `--manual-file` 时，`capture-xhs-link` 会通过 Playwright CDP 连接用户主动启动的专用 Chrome，读取单个链接当前可见内容。

Phase 11 增加质量评价和质量周报。它用于记录人工判断、修改成本和规则命中情况，不用生成数量冒充质量提升。

MVP PR-1 增加最小来源追踪、用户决策和对象版本快照。候选规则等事项可以先进入待确认状态，用户确认后再影响长期规则。

CLI 只读写本地 JSON 文件，不调用真实模型 API，不自动发布。

CLI 不替代 Codex 做高质量生成。`run-workflow` 和 `validate-real-sample` 中的生成链路仍主要用于本地流程验证。

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

## 查看来源追踪

```bash
python3 -m app.cli.main show-provenance \
  --workspace .xhs-personal-content-skill/real-sample \
  --target-type rule_card \
  --target-id rule-card-001
```

来源记录会区分：

- `actor`：谁产生，例如 `user`、`codex`、`system`。
- `artifact_nature`：内容性质，例如 `fact`、`inference`、`generated`、`decision`。

不要把 `codex + inference` 当作 `user + fact`。

## 创建和处理用户决策

创建待决策事项：

```bash
python3 -m app.cli.main create-decision \
  --workspace .xhs-personal-content-skill/real-sample \
  --target-type rule_card \
  --target-id rule-card-001 \
  --question "是否确认这条候选规则？" \
  --option confirm \
  --option reject \
  --option-outcome confirm=confirmed \
  --option-outcome reject=rejected \
  --recommendation confirm \
  --recommendation-reason "证据清晰，但仍需要你确认是否适合账号。" \
  --impact "确认后进入长期规则；拒绝后不参与后续生成。"
```

查看待决策事项：

```bash
python3 -m app.cli.main list-decisions \
  --workspace .xhs-personal-content-skill/real-sample \
  --status pending
```

确认或拒绝：

```bash
python3 -m app.cli.main resolve-decision \
  --workspace .xhs-personal-content-skill/real-sample \
  --decision-id decision-xxxx \
  --selected-option confirm \
  --user-note "这条适合我的账号"
```

第一版只对 `rule_card` 做确定性状态更新：`confirm` 会把候选规则更新为 `approved`，`reject` 会更新为 `rejected`。

`--option` 是用户看到的显示文本，`--option-outcome` 是系统状态结果。中文或自定义选项必须显式映射：

```bash
python3 -m app.cli.main create-decision \
  --workspace .xhs-personal-content-skill/real-sample \
  --target-type rule_card \
  --target-id rule-card-001 \
  --question "是否确认这条候选规则？" \
  --option "确认使用" \
  --option "暂不使用" \
  --option-outcome "确认使用=confirmed" \
  --option-outcome "暂不使用=rejected" \
  --recommendation "确认使用" \
  --recommendation-reason "这条规则有证据，但需要你确认。" \
  --impact "确认后进入长期规则；拒绝后不参与后续生成。"
```

旧英文 `confirm/reject` 选项仍兼容，但新建自定义选项不要依赖显示文本推断结果。

## 查看对象版本

```bash
python3 -m app.cli.main show-object-versions \
  --workspace .xhs-personal-content-skill/real-sample \
  --collection rule-cards \
  --record-id rule-card-001
```

当前只为 `creator-profiles`、`rule-cards` 和 `content-drafts` 保存更新前快照。快照内部的 `target_object_type` 使用统一业务类型，例如 `creator_profile`、`rule_card`、`content_draft`。
`show-object-versions` 只接受这三个版本化集合；其他集合不会在运行时进入无意义查询。

## 查看用户态上下文

```bash
python3 -m app.cli.main show-user-context \
  --workspace .xhs-personal-content-skill/real-sample \
  --collection rule-cards \
  --record-id rule-card-001
```

输出按用户可理解区块组织，例如：

- `【已有资料】`
- `【规则约束】`
- `【客观数据】`
- `【Codex 判断】`
- `【Codex 生成】`
- `【需要你决定】`
- `【已由你决定】`
- `【信息不足】`

`【已由你决定】` 只在存在 `resolved_by=user` 的已解决决策，或明确的 user decision provenance 时展示。`created_by=codex` 只表示决策请求由 Codex 创建，不能作为用户确认依据。

## 初始化账号工作区

```bash
python3 -m app.cli.main init-workspace --workspace .xhs-personal-content-skill/real-sample
```

该命令会创建本地工作区目录、模型集合目录和报告目录，并返回缺失的必需样本。

## 写入或更新账号档案

```bash
python3 -m app.cli.main upsert-profile \
  --workspace .xhs-personal-content-skill/real-sample \
  --file /path/to/creator_profile.json
```

写入结果：

- 更新工作区单文件账号档案。
- 同步更新集合目录中的账号记录。

## 添加对标账号

```bash
python3 -m app.cli.main add-benchmark-account \
  --workspace .xhs-personal-content-skill/real-sample \
  --file /path/to/benchmark_account.json
```

输入文件可以是一个 JSON 对象，也可以是对象数组。相同 `id` 会更新，不会重复追加。

## 添加对标帖子

```bash
python3 -m app.cli.main add-benchmark-post \
  --workspace .xhs-personal-content-skill/real-sample \
  --file /path/to/benchmark_post.json
```

输入文件可以是一个 JSON 对象，也可以是对象数组。命令会校验字段并同步写入集合目录。

## 添加自定义标签

```bash
python3 -m app.cli.main add-custom-tags \
  --workspace .xhs-personal-content-skill/real-sample \
  --file /path/to/custom_tags.json
```

输入文件可以是一个 JSON 对象，也可以是对象数组。相同 `id` 会更新，不会重复追加。

## 记录用户反馈

```bash
python3 -m app.cli.main add-feedback \
  --workspace .xhs-personal-content-skill/real-sample \
  --file /path/to/validation_feedback.json
```

该命令会把新的 `issues` 追加到现有反馈中，适合记录“标题太 AI”“封面可以”等用户偏好。

反馈是否能直接沉淀为长期规则，必须由结构化字段决定：

- `feedback_nature=explicit_user_rule` 且 `user_confirmed=true`：保存为用户已决定的长期规则。
- `feedback_nature=inferred_preference` 或 `candidate_rule`：保存为候选规则，并创建待用户决定事项。
- `feedback_nature=content_specific_feedback`：只作为当前内容反馈，不自动提升为长期规则。
- `feedback_nature=uncertain` 或缺失：采用安全默认，不自动 approved。

显式用户长期规则会额外保存一条 user decision provenance，便于审计这条规则为什么可以直接进入 `approved`。

## 生成规则使用范围

正式生成默认只使用 active rules：

- `approved`
- `testing`
- `validated`

以下规则不会进入 `generate-topics`、`generate-draft` 或 `review-own-post` 的 prompt 上下文：

- `candidate`
- `rejected`
- `deprecated`

当前 CLI 暂未提供试用 candidate 的显式参数。需要试用候选规则时，应先让用户通过决策确认，或在后续实验模式中单独实现。

## 校验工作区

```bash
python3 -m app.cli.main validate-workspace --workspace .xhs-personal-content-skill/real-sample
```

输出包含：

- 是否满足真实样本验证的最低输入要求。
- 缺失的必需样本。
- 对标账号、对标帖子、标签和反馈问题数量。

## 添加素材收件箱链接

```bash
python3 -m app.cli.main add-inbox-item \
  --workspace .xhs-personal-content-skill/real-sample \
  --url "https://www.xiaohongshu.com/explore/xxxx" \
  --user-intent "学习选题和视频结构" \
  --user-reason "开头很吸引人" \
  --focus title \
  --focus structure
```

该命令会保存用户主动提供的单个链接。同一链接重复提交时会更新原记录，并返回 `deduplicated: true`。

## 采集单个链接可见内容

使用用户授权 Chrome 采集时，先启动专用 Chrome：

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.xhs-personal-content-skill/chrome-profile"
```

首次使用时，用户自行在该专用 Chrome 中登录小红书。

采集单个收件箱链接：

```bash
python3 -m app.cli.main capture-xhs-link \
  --workspace .xhs-personal-content-skill/real-sample \
  --inbox-item-id inbox-xxxx \
  --cdp-url http://127.0.0.1:9222
```

该命令不会绕过登录、验证码、风控或访问限制。采集失败时会生成 `failed` 或 `partial` 采集记录，并保存诊断信息。

命令结果会额外返回 `outcome`，供 CLI、Skill 对话层和后续分析复用。它把原始采集状态解释为稳定结构：

- `status_category`：`success`、`partial` 或 `failed`。
- `available_content`：已获取内容的普通用户说法。
- `missing_content`：缺失内容的普通用户说法。
- `limitations`：缺失内容会影响什么。
- `recommended_action`：当前最小下一步动作。
- `user_summary`：可直接用于普通对话的安全摘要。
- `technical_details`：隔离的调试信息，普通用户摘要不读取。

普通用户摘要不会展示 CDP、Playwright、Python 异常、本地路径、token、签名媒体 URL 或追踪查询参数。

使用人工复制或截图转写内容时，保留为降级路径：

```bash
python3 -m app.cli.main capture-xhs-link \
  --workspace .xhs-personal-content-skill/real-sample \
  --inbox-item-id inbox-xxxx \
  --manual-file /path/to/manual-capture.json
```

`manual-capture.json` 可以包含：

```json
{
  "title": "页面可见标题",
  "body": "页面可见正文",
  "content_type": "image",
  "author": {
    "name": "页面可见账号名"
  },
  "metrics": {
    "likes": null,
    "collects": null,
    "comments": null,
    "shares": null
  },
  "images": [],
  "video": {},
  "comments": []
}
```

缺失指标必须写 `null`，不要写 `0`。

浏览器采集会标记：

```text
capture_method=browser_authorized
```

手动导入会标记：

```text
capture_method=manual
```

浏览器采集会尝试保存：

- 页面 HTML 快照。
- 采集诊断。
- 当前可见标题、正文、作者、发布时间、互动数据、图片、视频页面媒体信息和最多 30 条可见评论。

## 查看采集结果

```bash
python3 -m app.cli.main show-capture-result \
  --workspace .xhs-personal-content-skill/real-sample \
  --capture-id capture-from-inbox-xxxx
```

输出包含标题、正文、作者、互动数据、图片、视频、评论、已获得字段、缺失字段和 warnings。

## 分析采集内容

```bash
python3 -m app.cli.main analyze-captured-post \
  --workspace .xhs-personal-content-skill/real-sample \
  --capture-id capture-from-inbox-xxxx
```

该命令会生成结构化拆解结果：

- 图文内容默认使用 `image_carousel_tutorial`。
- 视频内容默认使用 `video_tutorial`。
- 可见信息进入 `observable_facts`。
- 推断信息进入各分析字段的 `inference`。
- 缺失字段进入 `uncertainties`。
- 面向普通用户的证据优先说明进入 `analysis_outcome`，其中包含：
  - `status_category`：分析证据充分性，取值为 `complete`、`partial` 或 `insufficient`。
  - `observed_facts`：只来自当前采集记录的可见事实。
  - `analysis_judgments`：带证据和置信度的 Codex 判断。
  - `information_gaps`：普通用户语言的信息缺口。
  - `dimension_limitations`：缺失信息影响的分析维度。
  - `decision_readiness`：当前证据是否足够进入“是否值得对标”的人工判断。
  - `user_summary`：可直接给用户看的分层摘要。
- 公开互动数据只作为表现参考，不能解释为确定原因。

分析边界：

- 只有图片路径、链接、数量或替代文本时，只能确认图片结构，不能判断封面文案、构图、人物、产品、环境或色彩。
- 只有视频结构或媒体信息时，只能确认视频存在，不能判断前几秒、镜头、字幕、音乐、语音或剪辑节奏。
- 只有评论数量时，不能推断评论观点；只有评论正文时，才做有限需求线索判断。
- `candidate_rule_ids` 仍保留在机器返回中，但不会进入 `user_summary`，也不会被描述为已确认规则。
- PR-3A 不输出账号适配结论；账号适配判断留到后续阶段。

本阶段不做 OCR、音频转写、关键帧抽取或真实多媒体处理。

## 评估与当前账号的适配情况

在帖子完成 evidence-first 分析后，可以单独评估它与一个明确账号档案的适配关系：

```bash
python3 -m app.cli.main assess-account-fit \
  --workspace .xhs-personal-content-skill/real-sample \
  --analysis-id analysis-from-capture-xxxx \
  --creator-id creator-main
```

该命令只读取已保存的帖子分析、关联采集内容和指定账号档案，并更新原 `BenchmarkAnalysis` 的账号适配结果。它会说明已验证的元素可如何借鉴、哪些需要改造、哪些不建议直接使用，以及哪些资料仍不足。

它不会自动修改账号档案、创建或修改规则、提升为对标内容、生成选题或生成草稿。结果只用于帮助用户决定是否把这篇内容作为参考，不代表可以照搬、可以直接发布或内容一定表现良好。

## 提升为对标内容

```bash
python3 -m app.cli.main promote-to-benchmark \
  --workspace .xhs-personal-content-skill/real-sample \
  --inbox-item-id inbox-xxxx
```

该命令用于运营人员确认后，把已采集和拆解的素材提升为对标账号草稿和对标帖子草稿。它不会自动判断任意链接都是强对标；生成结果仍需要人工确认和修订。

## 基于证据提出候选规则

当一篇内容已经完成 evidence-first 分析和同一账号档案的适配评估后，上层调用方可以提供最多 3 条结构化提案：

```bash
python3 -m app.cli.main propose-candidate-rules \
  --workspace .xhs-personal-content-skill/real-sample \
  --analysis-id analysis-from-capture-xxxx \
  --creator-id creator-main \
  --proposals-file candidate_proposals.json
```

`candidate_proposals.json` 由 Codex 或其他上层调用方生成。本地服务不生成规则文本，只验证：

- 每条提案是否使用已保存的帖子证据和账号适配判断；
- 是否与账号档案版本一致；
- 是否与现有规则构成精确重复；
- 是否违反明确的禁用表达或内容形式边界。

通过验证的规则会以待确认状态保存，并保留帖子证据和分析、账号档案两条来源记录。它们不会自动生效、不参与正式生成，也不会更新旧的 `candidate_rule_ids` 占位字段。

第一版不使用互动数据作为规则依据，不支持语义去重或完整冲突检测；近似或语义冲突仍需人工确认。旧 `generate-rule-cards` 仍是 mock/流程验证入口，不是此路径的一部分。

## 兼容：从分析结果创建候选规则

```bash
python3 -m app.cli.main create-rule-from-analysis \
  --workspace .xhs-personal-content-skill/real-sample \
  --analysis-id analysis-from-capture-xxxx \
  --candidate-id candidate-rule-from-capture-xxxx-1
```

该命令会同时创建：

- 一张 `candidate` 状态的规则卡。
- 一条规则证据，记录可见事实和推断。

## 规则生命周期

确认规则：

```bash
python3 -m app.cli.main approve-rule \
  --workspace .xhs-personal-content-skill/real-sample \
  --rule-id rule-from-candidate-rule-from-capture-xxxx-1
```

进入测试：

```bash
python3 -m app.cli.main mark-rule-testing \
  --workspace .xhs-personal-content-skill/real-sample \
  --rule-id rule-from-candidate-rule-from-capture-xxxx-1
```

记录验证结果：

```bash
python3 -m app.cli.main record-rule-result \
  --workspace .xhs-personal-content-skill/real-sample \
  --rule-id rule-from-candidate-rule-from-capture-xxxx-1 \
  --result success
```

拒绝规则：

```bash
python3 -m app.cli.main reject-rule \
  --workspace .xhs-personal-content-skill/real-sample \
  --rule-id rule-from-candidate-rule-from-capture-xxxx-1 \
  --reason "不适合当前账号"
```

废弃规则：

```bash
python3 -m app.cli.main deprecate-rule \
  --workspace .xhs-personal-content-skill/real-sample \
  --rule-id rule-from-candidate-rule-from-capture-xxxx-1 \
  --reason "被更具体的规则替代" \
  --superseded-by rule-new
```

检查重复和冲突：

```bash
python3 -m app.cli.main check-rule-relations \
  --workspace .xhs-personal-content-skill/real-sample
```

该命令会区分重复规则、适用场景不同的规则和需要人工解释的冲突规则，不会自动删除任何规则。

## 生成规则卡片

```bash
python3 -m app.cli.main generate-rule-cards \
  --workspace .xhs-personal-content-skill/real-sample \
  --creator-id creator-main \
  --benchmark-post-id benchmark-post-001
```

该命令使用本地 mock 链路分析一篇对标帖并落盘规则卡。它用于结构化验证，不代表最终内容质量。

## 生成选题

```bash
python3 -m app.cli.main generate-topics \
  --workspace .xhs-personal-content-skill/real-sample \
  --creator-id creator-main \
  --benchmark-post-id benchmark-post-001 \
  --topic-count 5
```

该命令会读取账号档案、标签、规则卡和指定对标帖，生成结构化选题记录。

## 生成草稿

```bash
python3 -m app.cli.main generate-draft \
  --workspace .xhs-personal-content-skill/real-sample \
  --topic-id topic-from-benchmark-post-001-1
```

该命令会生成标题、封面文案、脚本和简单分镜结构，适合用于验证落盘流程。高质量草稿仍应由 Codex 会话读取上下文后生成。

## 创建发布任务

```bash
python3 -m app.cli.main create-publish-task \
  --workspace .xhs-personal-content-skill/real-sample \
  --draft-id draft-from-topic-from-benchmark-post-001-1 \
  --planned-publish-time 2026-07-05T20:00:00+08:00
```

该命令只创建本地发布任务，不会自动发布。

## 复盘已发布内容

```bash
python3 -m app.cli.main review-own-post \
  --workspace .xhs-personal-content-skill/real-sample \
  --own-post-id own-post-001
```

该命令会生成本地复盘记录，并把复盘记录关联回已发布内容。

## 添加草稿质量评价

```bash
python3 -m app.cli.main add-quality-review \
  --workspace .xhs-personal-content-skill/real-sample \
  --file /path/to/content_quality_review.json
```

评价文件用于记录草稿是否适合账号、是否可发布、标题和脚本是否需要重写，以及哪些规则被接受或否定。写入后，对应草稿会同步保存最近一次评价摘要。

## 生成质量周报

```bash
python3 -m app.cli.main generate-quality-report \
  --workspace .xhs-personal-content-skill/real-sample \
  --period weekly
```

报告会输出到工作区的报告目录，包含：

- 首轮通过率。
- 平均修改次数。
- 大改率。
- 账号适配分和可发布分。
- 标题重写率和脚本重写率。
- 规则命中率和规则验证成功率。
- 本周期有效规则、表现差规则、被重复否定的模式、修改成本变化和下一轮样本建议。

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

Phase 7 后，真实样本验证会处理多篇对标帖，并在报告中补充规则合并检查：

- 重复规则
- 冲突规则
- 低置信规则

## 可用 collection

- `creator-profiles`
- `benchmark-accounts`
- `benchmark-posts`
- `benchmark-analyses`
- `content-inbox`
- `capture-records`
- `custom-tags`
- `rule-cards`
- `rule-evidence`
- `topic-pool`
- `content-drafts`
- `content-quality-reviews`
- `publish-tasks`
- `own-posts`
- `review-records`
