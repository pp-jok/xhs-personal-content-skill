# PR-5 开发整体计划：Flexible Mechanism Candidate Intake and Knowledge Asset Layer

## 0. 文档目的

本文件用于指导 Codex 后续按 PR 分阶段开发 `xhs-personal-content-skill` 的 PR-5 系列能力。

当前项目已经完成了：

```text
采集 / 外部拆解
→ 证据优先分析
→ 账号适配
→ 候选规则
→ 用户决策
→ GenerationContext
→ 选题
→ 草稿
→ 聚焦修订
```

PR-5 的目标不是继续增加生成能力，也不是直接实现 OCR、视频转写或关键帧工具，而是增加一个新的知识抽象层：

```text
External Analysis / BenchmarkAnalysis / Partial Input
→ ContentMechanism
→ Candidate Rule / Content Asset
```

核心目标：

```text
把外部拆解结果或不完整输入，安全地沉淀为候选内容机制；
再由机制谨慎转成候选规则和内容资产；
不让单篇案例、不完整证据或候选机制污染正式生成链路。
```

---

## 1. 当前核心问题

当前 Skill 已经可以把一篇对标内容拆成：

```text
客观数据
→ 小八判断
→ 可迁移点
→ 不能学的点
→ 候选规则
```

这个结构适合人看，但仍然存在三个问题：

1. 它更像“分析报告”，还不是稳定的知识资产。
2. 候选规则可能仍然从单篇案例直接得出，存在规则污染风险。
3. 外部输入不一定完整，可能只有标题、正文、截图 OCR、视频转写、封面图、评论截图或用户口述偏好。

因此 PR-5 必须解决：

```text
输入不完整是常态，不是异常。
```

正确设计不是：

```text
完整外部拆解结果 → ContentMechanism
```

而是：

```text
任意质量的外部输入
→ Input Normalization
→ Evidence / Gaps / Limitations
→ Mechanism Candidate 或 No Mechanism
```

---

## 2. PR-5 总体架构

### 2.1 分层定义

```text
Rule = 硬约束 / 账号执行规则 / 会影响正式生成
Mechanism = 软知识 / 内容机制 / 策略参考
Asset = 生成素材 / 模板来源
```

三者不能混用。

### 2.2 主链路

```text
External Analysis / BenchmarkAnalysis / Partial Input
        ↓
MechanismInputDigest
        ↓
ContentMechanism(candidate)
        ↓
+ CreatorProfile + ExistingRules
        ↓
Candidate RuleCard
        ↓
DecisionRequest
        ↓
Approved RuleCard
```

内容资产支线：

```text
ContentMechanism(active)
        ↓
ContentAsset
```

### 2.3 关键边界

PR-5A/B/C 阶段必须保持以下边界：

```text
ContentMechanism 默认不进入 GenerationContext。
ContentAsset 默认不进入 GenerationContext。
candidate mechanism 只用于分析展示和后续人工判断。
active mechanism 也不等于 RuleCard。
ContentAsset 只是模板素材，不是生成硬约束。
从 Mechanism 生成的 RuleCard 必须是 candidate。
candidate RuleCard 仍然必须经过 DecisionRequest 用户确认。
```

明确禁止：

```text
ContentMechanism → GenerationContext
ContentAsset → GenerationContext
candidate mechanism → TopicItem
candidate mechanism → ContentDraft
ContentMechanism → approved RuleCard
ContentAsset → active RuleCard
```

---

## 3. 输入不完整的处理原则

### 3.1 输入类型可能不一致

PR-5A 必须适配以下输入现实：

```text
只有标题和正文
只有截图 OCR
只有视频逐字稿
只有封面图
只有用户口述喜欢原因
只有评论区截图
有完整拆解但缺评论
有视频分析但没有平台互动数据
格式一样但很多字段为空
格式完全不一样
```

### 3.2 不要求输入完整，只要求可被规范化

PR-5A 不应强制要求完整拆解文件。它应要求输入能被整理成以下核心结构：

```text
observed_facts
inferences
user_stated_preferences
missing_information
limitations
source_coverage
```

### 3.3 MechanismInputDigest

PR-5A 第一版可以不落库，但服务层应有类似 `MechanismInputDigest` 的概念。

建议结构：

```json
{
  "observed_facts": [
    "标题包含 Codex、Obsidian、10min、爆款工作流",
    "封面文字包含 10min 自动拆爆款库"
  ],
  "inferences": [
    "内容把工具组合包装成具体内容运营结果"
  ],
  "user_stated_preferences": [],
  "missing_information": [
    "未获取评论区",
    "未获取完整视频关键帧"
  ],
  "limitations": [
    "不能确认用户真实评论需求",
    "不能确认完整剪辑节奏"
  ],
  "source_coverage": {
    "title": "present",
    "body": "present",
    "cover": "present",
    "video_transcript": "partial",
    "video_frames": "missing",
    "comments": "missing"
  }
}
```

### 3.4 允许“不生成机制”

PR-5A 不应每次强行生成 ContentMechanism。

机制创建结果应允许：

```text
created
limited_created
not_enough_evidence
invalid_input
```

例如输入只有：

```text
这个标题挺好，适合学
```

不应强行生成机制。应输出：

```text
信息不足，暂不生成内容机制。
还需要至少补充：标题、正文/封面、用户想学的点，或一段可见内容。
```

### 3.5 confidence 分级

`confidence` 不应只是主观判断，应与证据覆盖度相关。

建议：

```text
high：
有多个来源支撑，例如标题 + 封面 + 正文 + 视频/图片证据 + 评论或用户理由。

medium：
有标题/正文/封面/逐字稿等主要证据，但缺评论或部分媒体证据。

low：
只有单一来源，例如只有标题、只有用户描述、只有截图 OCR。
```

---

## 4. PR-5A：Flexible Mechanism Candidate Intake

### 4.1 目标

新增 ContentMechanism，并允许从不同完整度的外部分析结果或手工整理文件中保存候选内容机制。

准确目标：

```text
接收不同完整度的外部分析结果，
保留证据、推断、缺口和限制，
只在证据足够时保存候选机制，
信息不足时拒绝生成机制。
```

新链路：

```text
External Analysis / BenchmarkAnalysis / Partial Input
→ MechanismInputDigest
→ ContentMechanism(candidate)
```

### 4.1.1 PR-5A Stage B 收敛决策

当前实现以本小节为准，覆盖下方早期草案中的字段和命令示例差异：

```text
1. 第一版不持久化 MechanismInputDigest，只在 service 内部规范化输入。
2. 使用 source_refs，不使用 source_benchmark_ids。
3. source_refs 是轻量来源引用：source_type + source_id。
4. source_type 允许 benchmark_post、benchmark_analysis、capture_record、external_analysis、user_input。
5. 不校验 source_id 是否真实存在，避免把外部整理材料误判为不可导入。
6. 模型保存 confidence_level，同时用 BaseModel.confidence 保存对应数值。
7. import-mechanism 只能创建 candidate 机制；active / deprecated 只属于模型生命周期能力。
8. created / limited_created / not_enough_evidence / invalid_input 是导入结果状态，不是 ContentMechanism.status。
9. ContentMechanism 不进入 GenerationContext，不影响 generate-topics / generate-draft / revise-draft。
10. PR-5A 不生成 RuleCard、RuleEvidence、DecisionRequest、TopicItem、ContentDraft、PublishTask 或 ContentAsset。
```

### 4.2 新增模型：ContentMechanism

新增 `ContentMechanism`。

建议字段：

```text
id
name
description
source_refs
evidence_summary
problem
solution
pattern
applicable_scope
limitations
confidence_level
confidence
status
created_at
created_by
version
```

字段说明：

```text
name：
机制名称，例如“复杂工具结果化表达”。

description：
普通语言描述这个机制。

source_refs：
来自哪些 BenchmarkPost / BenchmarkAnalysis / CaptureRecord / external_analysis / user_input。可为空，但为空时 machine_summary 和 user_summary 必须说明来源绑定缺失。

evidence_summary：
支撑这个机制的证据摘要。必须是 dict，建议包含 observed_facts / inferences / limitations。

problem：
这个机制解决的内容表达问题。可为空，但为空时 summary 应说明机制问题尚未完整定义。

solution：
它如何解决问题。可为空，但为空时 summary 应说明解决方式尚未完整定义。

pattern：
可复用模式，例如“工具组合 → 时间门槛 → 结果承诺 → 流程证据 → 资产沉淀”。建议为 list[str]。

applicable_scope：
适用范围，例如“AI工具内容、效率工具内容、教程型内容”。建议为 list[str]。

limitations：
限制和风险，例如“不适合纯技术教程；不能夸大时间和效果”。必须为 list[str]。

confidence_level：
low / medium / high。保存时同步为 BaseModel.confidence 数值：low=0.4，medium=0.6，high=0.8。

status：
candidate / active / deprecated。
```

### 4.3 状态定义

```text
candidate：
候选机制。只用于展示和后续人工判断，不用于生成。

active：
已确认可作为知识资产继续使用，但仍不等于 RuleCard，不自动进入 GenerationContext。

deprecated：
废弃机制。保留记录，不再用于后续机制转规则或机制转资产。
```

### 4.4 最小可接受输入

不要求所有字段都有。

最小可接受输入示例：

```json
{
  "name": "复杂工具结果化表达",
  "description": "把复杂工具能力翻译成用户能理解的结果。",
  "evidence_summary": {
    "observed_facts": ["标题包含 Codex + Obsidian + 爆款工作流"],
    "inferences": ["工具被包装成内容运营结果"],
    "limitations": ["缺少评论区证据"]
  },
  "confidence_level": "low",
  "status": "candidate"
}
```

### 4.5 完整输入示例

```json
{
  "id": "mechanism-complex-tool-result-framing",
  "name": "复杂工具结果化表达",
  "description": "把复杂 AI 工具或工作流先翻译成用户能感知的内容运营结果，而不是先讲工具功能。",
  "source_refs": [
    {"source_type": "benchmark_post", "source_id": "benchmark-post-xxx"}
  ],
  "evidence_summary": {
    "observed_facts": [
      "标题包含 Codex、Obsidian、10min 和爆款工作流",
      "封面突出 10min 自动拆爆款库",
      "视频展示流程图和拆解结果表格"
    ],
    "inferences": [
      "内容不是单纯工具介绍，而是把工具包装成内容生产结果"
    ],
    "limitations": [
      "未获取完整评论区，不能确认用户真实评论需求"
    ]
  },
  "problem": "复杂工具内容容易让用户只看到工具名，看不到和自己任务的关系。",
  "solution": "先表达用户能获得的结果，再解释工具如何实现。",
  "pattern": [
    "工具组合",
    "时间门槛",
    "结果承诺",
    "流程证据",
    "资产沉淀"
  ],
  "applicable_scope": [
    "AI工具内容",
    "效率工具内容",
    "工作流教程",
    "内容运营方法"
  ],
  "limitations": [
    "不适合纯技术教程",
    "不能夸大时间承诺",
    "必须有可见流程证据"
  ],
  "confidence_level": "medium",
  "confidence": 0.6,
  "status": "candidate"
}
```

### 4.6 新增 CLI

第一版建议新增：

```bash
python3 -m app.cli import-mechanism \
  --workspace .xhs-personal-content-skill/real-sample \
  --file mechanism_candidate.json
```

行为：

```text
读取机制候选 JSON。
规范化缺失字段。
校验 evidence_summary。
校验 confidence/status。
证据不足时失败且不写入。
成功时保存 ContentMechanism。
只写 ContentMechanism 集合。
返回 user_summary 和 machine_summary。
```

### 4.7 CLI 返回结构

成功返回建议：

```json
{
  "mechanism_id": "mechanism-xxx",
  "status_category": "limited_created",
  "mechanism_status": "candidate",
  "confidence_level": "medium",
  "missing_information": [
    "缺少评论区证据",
    "缺少完整视频关键帧"
  ],
  "limitations": [
    "不能确认用户真实需求",
    "不能确认视频画面节奏"
  ],
  "user_summary": "已保存 1 个候选内容机制，但证据还不完整。它目前只作为分析资产，不会进入正式生成。",
  "machine_summary": {
    "mechanism_id": "mechanism-xxx",
    "status_category": "limited_created",
    "mechanism_status": "candidate",
    "confidence_level": "medium",
    "confidence": 0.6,
    "source_refs": [
      {"source_type": "benchmark_post", "source_id": "benchmark-post-xxx"}
    ]
  }
}
```

失败返回建议：

```json
{
  "ok": false,
  "error": "信息不足，暂不生成内容机制。至少需要 observed_facts 或明确用户提供的事实依据。"
}
```

### 4.8 PR-5A 不做事项

明确不做：

```text
不自动从长文中抽机制。
不生成 RuleCard。
不生成 RuleEvidence。
不生成 DecisionRequest。
不生成 TopicItem。
不生成 ContentDraft。
不进入 GenerationContext。
不接 OCR / 视频转写工具。
不做多案例归纳。
不修改现有 rule proposal 主链路。
```

### 4.9 测试要求

新增测试：

```text
1. ContentMechanism 可以 from_dict / to_dict / validate。
2. candidate / active / deprecated 状态合法。
3. confidence 只允许 low / medium / high。
4. evidence_summary 必须是 dict。
5. evidence_summary 为空时失败。
6. observed_facts 为空但只有 inferences 时失败或返回 low-confidence warning；具体策略必须在测试中固定。
7. source_refs 必须是来源引用列表；缺失时可创建但 summary 要提示来源绑定缺失。
8. pattern 缺失可创建，但 user_summary 说明机制模式不完整。
9. import-mechanism 成功时只写 ContentMechanism。
10. import-mechanism 失败路径不写任何对象。
11. 不生成 RuleCard / TopicItem / ContentDraft / PublishTask。
12. ContentMechanism 模型支持 candidate / active / deprecated，但 PR-5A 的 import-mechanism 只允许创建 candidate；输入 active 或 deprecated 时返回 invalid_input。active / deprecated 只能通过未来单独的生命周期治理能力产生。
13. user_summary 不暴露本地路径、内部 enum、JSON 细节。
14. machine_summary 保留 mechanism_id、status_category、mechanism_status、confidence_level、confidence、source_refs。
```

### 4.10 PR-5A 验收标准

PR-5A 合格条件：

```text
1. ContentMechanism 能保存。
2. candidate / active / deprecated 状态明确。
3. confidence 明确。
4. evidence_summary 保留事实、推断、限制。
5. 输入可以不完整，但必须标明 missing / limitations。
6. 证据不足时拒绝创建机制。
7. import-mechanism 只写 ContentMechanism。
8. 不影响 show-generation-context。
9. 不影响 generate-topics。
10. 不影响 generate-draft。
11. 不影响 revise-draft。
12. 文档明确 Mechanism / Rule / Asset 区别。
```

---

## 5. PR-5B：Mechanism → Candidate Rule

### 5.1 目标

从 ContentMechanism 生成 Candidate RuleCard。

新链路：

```text
ContentMechanism
+ CreatorProfile
+ Existing RuleCards
→ candidate RuleCard
```

### 5.2 核心价值

避免：

```text
单篇 BenchmarkAnalysis → 直接污染 RuleCard
```

改为：

```text
BenchmarkAnalysis / External Analysis
→ ContentMechanism
→ 账号适配后的 Candidate RuleCard
→ 用户确认
→ approved RuleCard
```

### 5.3 新增 CLI

建议新增：

```bash
python3 -m app.cli propose-rule-from-mechanism \
  --workspace .xhs-personal-content-skill/real-sample \
  --mechanism-id mechanism-xxxx \
  --creator-id creator-main \
  --file mechanism-rule-proposal.json
```

PR-5B Stage B 收敛决策：该命令接收外部/Codex 整理出的结构化规则提案文件，本地 service 只负责治理、证据校验、重复检查和候选对象落盘，不负责自动编写规则语义。

### 5.4 输入

```text
ContentMechanism
CreatorProfile
Existing RuleCards
RuleEvidence
ProvenanceRecord
结构化 mechanism rule proposal
```

### 5.5 输出

```text
candidate RuleCard
RuleEvidence
ProvenanceRecord
user_summary
machine_summary
```

PR-5B 不自动创建 DecisionRequest。成功后用户仍需通过现有 `create-rule-decision` 和 `resolve-decision` 流程确认或拒绝候选规则。

### 5.6 规则生成原则

候选规则必须包含：

```text
1. 规则内容
2. 适用范围
3. 不适用范围
4. 证据摘要
5. 账号适配理由
6. 与已有规则关系
7. 风险和限制
```

### 5.7 必须保持的治理边界

```text
生成的 RuleCard.status 必须是 candidate。
candidate RuleCard 不进入生成。
用户必须通过 DecisionRequest 确认后，规则才能 approved。
```

机制不能被当作用户确认。

```text
Mechanism evidence ≠ user decision evidence
```

### 5.8 PR-5B 不做事项

```text
不自动批准规则。
不自动进入 GenerationContext。
不自动创建 DecisionRequest。
不生成 TopicItem。
不生成 ContentDraft。
不修改 active rules。
不废弃旧规则。
不做复杂语义去重。
不允许 candidate mechanism 直接进入正式生成。
```

### 5.9 测试要求

新增测试：

```text
1. active/candidate mechanism 可以生成 candidate RuleCard。
2. deprecated mechanism 不能生成 RuleCard。
3. 生成的 RuleCard status 必须是 candidate。
4. 生成 RuleCard 时创建 RuleEvidence。
5. 生成 RuleCard 时创建 ProvenanceRecord。
6. 不修改 ContentMechanism。
7. 不修改已有 RuleCard。
8. 不生成 TopicItem / ContentDraft / PublishTask。
9. 与已有精确重复规则时失败或明确提示。
10. user_summary 不暴露内部路径、JSON、enum。
11. machine_summary 保留 mechanism_id、rule_id、profile_id、source evidence。
12. 创建的 RuleEvidence 必须标明来源是 mechanism-derived，不得伪装成 user fact。
13. 若 mechanism confidence 为 low，user_summary 必须提醒证据有限。
```

---

## 6. PR-5C：Mechanism → ContentAsset

### 6.1 目标

从 ContentMechanism 生成可复用内容资产。

新链路：

```text
ContentMechanism(candidate 或 active)
+ CreatorProfile
+ 外部结构化 asset proposal
→ ContentAsset(candidate)
```

内容资产不是规则，不是生成硬约束，只是可复用素材和模板。

PR-5C Stage B 收敛决策：

```text
1. candidate 和 active ContentMechanism 都可以作为资产来源。
2. deprecated ContentMechanism 必须拒绝。
3. 新建 ContentAsset 状态始终为 candidate。
4. PR-5C 不实现 activate-mechanism、deprecate-mechanism、activate-content-asset、deprecate-content-asset 或 create-asset-decision。
5. PR-5C 不接入 GenerationContext；candidate 和 active ContentAsset 都不会自动影响 generate-topics、generate-draft 或 revise-draft。
6. 本地 service 只负责治理、证据校验、重复检查和候选对象落盘，不负责自动创作资产内容。
7. 资产提案由外部/Codex 整理为结构化 JSON。
8. 第一版只支持结构化文本资产，不支持媒体文件、远程 URL、OCR、视频解析、完整文章成稿、固定发布文案或批量导入。
```

### 6.2 新增模型

新增 `ContentAsset`。

建议字段：

```text
id
status
asset_type
name
description
template
variables
applicable_scope
exclusions
usage_notes
limitations
examples
creator_profile_id
source_mechanism_ids
selected_observed_facts
account_fit_reason
confidence_level
confidence
created_at
created_by
version
```

### 6.3 asset_type

第一版固定支持：

```text
title_pattern
cover_structure
opening_template
body_structure
cta_template
comparison_framework
case_framework
image_text_structure
topic_framework
```

### 6.4 status

```text
candidate
active
deprecated
```

### 6.5 新增 CLI

建议新增：

```bash
python3 -m app.cli propose-asset-from-mechanism \
  --workspace .xhs-personal-content-skill/real-sample \
  --mechanism-id mechanism-xxxx \
  --creator-id creator-main \
  --file data/templates/mechanism-asset-proposal.template.json
```

### 6.6 PR-5C 不做事项

```text
ContentAsset 不进入 GenerationContext。
ContentAsset 不等于 RuleCard。
ContentAsset 不自动影响 generate-topics。
ContentAsset 不自动影响 generate-draft。
ContentAsset 不覆盖 active rules。
ContentAsset 不自动发布。
不做复杂资产库 UI。
不做多案例归纳。
不做资产激活。
不做资产决策。
不做媒体资产。
不做批量导入。
```

### 6.7 测试要求

新增测试：

```text
1. ContentAsset 可以 from_dict / to_dict / validate。
2. asset_type 必须属于允许列表。
3. status 必须属于 candidate / active / deprecated。
4. deprecated mechanism 不能生成资产。
5. candidate mechanism 可以生成 candidate asset。
6. active mechanism 可以生成 candidate ContentAsset。
7. 生成资产不修改 RuleCard / TopicItem / ContentDraft。
8. user_summary 隐藏内部路径和 JSON。
9. machine_summary 保留 asset_id、mechanism_id、asset_type。
10. 资产必须带 applicable_scope 和 limitations。
```

---

## 6A. PR-5C.1：ContentAsset Lifecycle

### 6A.1 目标

在 PR-5C 和 PR-5D 之间增加最小资产生命周期：

```text
ContentAsset(candidate)
→ 用户显式激活
→ ContentAsset(active)

ContentAsset(candidate 或 active)
→ 用户显式废弃
→ ContentAsset(deprecated)
```

PR-5C.1 只改变资产治理状态，不接入生成链路。

### 6A.2 状态转换

合法转换：

```text
candidate → active
candidate → deprecated
active → deprecated
```

禁止重复同状态操作、反向转换、deprecated 重新激活，以及任何通用 `set status` 入口。

### 6A.3 CLI

新增：

```bash
python3 -m app.cli activate-content-asset \
  --workspace .xhs-personal-content-skill/real-sample \
  --asset-id asset-xxxx \
  --expected-version 1 \
  --actor user
```

```bash
python3 -m app.cli deprecate-content-asset \
  --workspace .xhs-personal-content-skill/real-sample \
  --asset-id asset-xxxx \
  --expected-version 2 \
  --actor user
```

两个命令都必须使用 optimistic version check。版本不匹配时失败且零写入。

### 6A.4 PR-5C.1 不做事项

```text
不连接 GenerationContext。
不影响 generate-topics。
不影响 generate-draft。
不影响 revise-draft。
不消费模板变量。
不创建 DecisionRequest。
不创建 ProvenanceRecord。
不修改 ContentAssetEvidence。
不修改 ContentMechanism。
不修改 RuleCard。
不做自动资产选择。
不做批量生命周期操作。
```

### 6A.5 与 PR-5D 的关系

PR-5D 只能显式引用 active ContentAsset。candidate asset 不进入生成；deprecated asset 不允许作为后续显式生成引用。

---

## 7. 暂缓阶段

### 7.1 PR-5D：Controlled Context

目标：显式选择 Mechanism / ContentAsset 进入 GenerationContext。

暂缓原因：会影响 PR-4B/C/D 的生成链路，需要大量回归测试。

以后如做，必须显式参数控制：

```text
--reference-mechanism-id
--reference-asset-id
```

禁止默认读取全部 active mechanisms / assets。

### 7.2 PR-5E：Multi-Benchmark Learning

目标：多个 BenchmarkAnalysis / ContentMechanism → 共同机制候选。

暂缓原因：当前样本不足。至少等有：

```text
5-10 个 BenchmarkAnalysis
5-10 个 ContentMechanism
若干用户确认/拒绝记录
```

再做。

### 7.3 PR-5F：Mechanism Validation Loop

目标：Mechanism / Asset / Rule → QualityReview / ReviewRecord → 保留、修正或废弃。

暂缓原因：归因复杂，容易把草稿质量、选题质量、机制质量混在一起。

---

## 8. 推荐开发顺序

### 第一批：只做 PR-5A

目标：

```text
先让系统能保存 ContentMechanism candidate，并安全处理不完整输入。
```

不接 Rule，不接 Asset，不接 GenerationContext。

### 第二批：PR-5B

目标：

```text
让机制可以转成 candidate RuleCard。
```

仍然必须走用户确认。

### 第三批：PR-5C

目标：

```text
让机制可以沉淀成可复用 ContentAsset。
```

仍然不进入生成。

---

## 9. 每个 PR 的 Codex 执行方式

每个 PR 都按以下固定流程：

```text
Stage A：Read-only audit
Stage B：Implementation
Stage B Review：代码审计和修复
Create PR
Stage C：PR read-only audit
Final fix if needed
Merge
Post-merge verification
```

任何 PR 都不要一次性让 Codex 自己“设计 + 实现 + 合并”。

每个提示词必须包含：

```text
1. 当前 PR 名称
2. 当前 Stage
3. 允许修改的范围
4. 禁止事项
5. 必跑测试
6. 输出报告格式
7. 不得 merge，除非明确要求
```

---

## 10. PR-5A Codex Prompt 草案

后续正式执行时，应按 Stage A / Stage B 分开提示。这里先给整体草案。

```text
You are working on repo pp-jok/xhs-personal-content-skill.

Task: PR-5A — Flexible Mechanism Candidate Intake.

Goal:
Add a minimal ContentMechanism model and CLI import path so external analysis results or partially structured mechanism summaries can be saved as candidate content mechanisms.

Core idea:
Input may be incomplete. Do not assume every external analysis has full title/body/cover/video/comments. The system must preserve observed facts, inferences, missing information, limitations, source coverage, and confidence. If evidence is insufficient, it must refuse to create a mechanism and write nothing.

Critical boundaries:
- Do not connect ContentMechanism to GenerationContext.
- Do not generate RuleCard.
- Do not generate RuleEvidence.
- Do not generate DecisionRequest.
- Do not generate TopicItem.
- Do not generate ContentDraft.
- Do not call OCR/video/transcription tools.
- Do not modify existing generation behavior.
- Do not change candidate rule decision behavior.
- Do not auto-approve anything.

Model:
Add ContentMechanism with fields:
id
name
description
source_refs
evidence_summary
problem
solution
pattern
applicable_scope
limitations
confidence_level
confidence
status
created_at
created_by
version

Allowed status:
candidate
active
deprecated

Allowed confidence_level:
low
medium
high

Evidence:
evidence_summary must be a dict. It should support:
observed_facts
inferences
user_stated_preferences
missing_information
limitations
source_coverage

At minimum, there must be at least one observed fact or explicit user-stated factual preference. Do not allow mechanism creation from pure inference with no factual basis.

CLI:
Add command:
import-mechanism
with:
--workspace required
--file required

The input file contains one ContentMechanism-like JSON object.
The command normalizes optional fields, validates evidence, and saves it if evidence is sufficient.
It returns:
mechanism_id
status
confidence
created
missing_information
limitations
user_summary
machine_summary

Persistence:
Save to a new collection for content mechanisms.
Do not modify any existing collection except creating/upserting ContentMechanism.

Docs:
Update docs/cli.md and SKILL.md to explain:
- Mechanism is soft knowledge, not Rule.
- Mechanism does not enter GenerationContext.
- candidate mechanism is for analysis/display only.
- active mechanism is still not a hard generation rule.
- RuleCard remains the hard executable rule layer.
- Inputs may be incomplete; missing evidence must be preserved.

Tests:
Add tests for:
- model validation
- allowed statuses
- allowed confidence
- invalid evidence_summary
- empty evidence_summary fails
- pure inference without observed facts fails or is rejected
- partial input with missing comments succeeds with limitations
- CLI success writes only ContentMechanism
- CLI failure no-write
- no RuleCard/TopicItem/ContentDraft/PublishTask side effects
- user_summary hides paths/internal enum/JSON
- machine_summary keeps IDs/status/confidence/source ids

Run:
python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=.pycache python3 -m compileall -q app tests

Do not commit until tests pass.
Report changed files, test results, and side effects.
```

---

## 11. PR-5A 验收清单

PR-5A 合格条件：

```text
1. ContentMechanism 能保存。
2. candidate / active / deprecated 状态明确。
3. confidence 明确。
4. evidence_summary 保留事实、推断、限制。
5. 输入可以不完整，但必须标明 missing / limitations。
6. 纯推断且无事实依据时拒绝创建。
7. import-mechanism 只写 ContentMechanism。
8. 不影响 show-generation-context。
9. 不影响 generate-topics。
10. 不影响 generate-draft。
11. 不影响 revise-draft。
12. 文档明确 Mechanism / Rule / Asset 区别。
```

---

## 12. 成功标准

PR-5A/B/C 完成后，系统应从：

```text
内容分析 → 候选规则
```

升级为：

```text
内容分析 / 外部拆解 / 不完整输入
→ 内容机制
→ 候选规则 / 内容资产
```

但仍然不改变正式生成链路。

当前批次成功不要求生成质量立刻提升，只要求：

```text
1. 外部分析能被稳定转成机制。
2. 机制能带着证据、缺口和限制保存。
3. 机制能受控转为候选规则。
4. 机制能受控转为内容资产。
5. 机制和资产不会污染 GenerationContext。
```

---

## 13. 最终判断

当前最值得做的是：

```text
PR-5A → PR-5B → PR-5C
```

暂不做：

```text
PR-5D / PR-5E / PR-5F
```

PR-5A 的关键不是“接收完整拆解”，而是：

```text
Flexible Mechanism Candidate Intake
```

它必须从第一天就支持不完整输入、缺失信息、低置信度、拒绝生成和不污染生成链路。
