# xhs-personal-content-skill 后续优化开发规格 v1.0

## 1. 项目目标

将当前 `xhs-personal-content-skill` 从“本地账号运营工作流 MVP”升级为：

> 面向会使用 Codex、懂小红书运营的专业用户，用于持续提高帖子质量的长期运营 Agent。

核心目标不是一次性生成爆款内容，而是通过长期积累：

- 账号档案
- 对标内容
- 用户偏好
- 规则卡
- 发布结果
- 复盘记录

不断降低运营人员修改成本，提高内容的账号贴合度、可发布率和稳定性。

---

## 2. 核心产品闭环

```text
指定链接 / 截图 / 文案
        ↓
素材收件箱
        ↓
内容采集与结构化
        ↓
多模态拆解
        ↓
账号适配判断
        ↓
候选规则
        ↓
运营人员确认
        ↓
选题与草稿生成
        ↓
发布任务
        ↓
发布结果与复盘
        ↓
规则验证、强化、降级或废弃
```

---

## 3. 当前版本判断

当前 0.7.0 已具备：

- 账号档案、对标账号、对标帖子、标签、规则卡、选题、草稿、发布任务、复盘记录
- 项目本地 JSON / Markdown 存储
- 初始化、录入、反馈、校验、生成、复盘等 CLI
- Codex 负责最终内容生成，Mock 服务负责结构和流程验证
- 多篇对标帖验证
- `missing_fields`、`confidence`、来源说明等元数据

后续不要继续横向堆功能，重点建设以下三项能力：

1. 指定链接内容输入
2. 规则生命周期与证据体系
3. 持续质量提升验证

---

# 4. 产品边界

## 4.1 必须支持

- 用户主动提供单个小红书链接
- 采集该链接当前可见内容
- 支持图文帖和视频帖
- 提取标题、正文、图片、视频、公开互动数据、当前可见评论
- 对获取失败和缺失字段明确标记
- 结合当前账号档案、偏好、规则和历史复盘进行分析
- 将对标内容转化为候选规则和衍生选题
- 记录规则的来源、证据、适用场景、置信度和验证状态
- 发布后根据真实结果更新规则

## 4.2 明确不做

- 不做平台级爬虫
- 不批量遍历账号或话题
- 不自动搜索全站爆款
- 不绕过登录、验证码、风控或访问限制
- 不自动发布
- 不做多用户商业后台
- 不接第三方大模型 API
- 不把公开点赞、收藏、评论解释为确定的爆款原因

---

# 5. 总体架构

```text
Codex
├── SKILL.md
│   ├── 触发规则
│   ├── 用户交互
│   ├── 文件读取策略
│   ├── 工具调用策略
│   └── 输出规范
│
├── Local Capture Layer
│   ├── 单链接采集
│   ├── 页面内容提取
│   ├── 图片下载
│   ├── 视频保存
│   ├── 当前可见互动数据
│   └── 当前可见评论
│
├── Media Analysis Layer
│   ├── 视频元数据
│   ├── 关键帧
│   ├── 音频转写
│   ├── 字幕 / OCR
│   ├── 图片序列分析
│   └── 评论洞察
│
├── Local Knowledge Layer
│   ├── 账号档案
│   ├── 素材收件箱
│   ├── 对标内容
│   ├── 内容拆解
│   ├── 规则证据
│   ├── 规则生命周期
│   ├── 选题 / 草稿
│   └── 发布 / 复盘
│
└── CLI / MCP
    ├── 稳定读写
    ├── 校验
    ├── 媒体处理
    └── 结构化返回
```

长期建议使用本地 MCP 暴露能力；第一阶段可以先用 CLI 实现。

---

# 6. 第一阶段：素材收件箱与指定链接采集

## 6.1 新增对象：ContentInboxItem

建议字段：

```json
{
  "id": "",
  "source_url": "",
  "source_platform": "xiaohongshu",
  "status": "inbox",
  "capture_status": "pending",
  "content_type": "unknown",
  "user_intent": "",
  "user_reason": "",
  "requested_focus": [],
  "captured_at": null,
  "missing_fields": [],
  "warnings": [],
  "confidence": 0.0,
  "created_at": "",
  "updated_at": ""
}
```

状态：

```text
inbox
capturing
captured
analyzed
promoted_to_benchmark
rejected
archived
```

## 6.2 新增对象：CaptureRecord

建议字段：

```json
{
  "id": "",
  "inbox_item_id": "",
  "source_url": "",
  "capture_method": "browser_authorized",
  "capture_status": "partial",
  "captured_at": "",
  "title": "",
  "body": "",
  "content_type": "video",
  "author": {},
  "metrics": {
    "likes": null,
    "collects": null,
    "comments": null,
    "shares": null
  },
  "images": [],
  "video": {},
  "comments": [],
  "available_fields": [],
  "missing_fields": [],
  "warnings": [],
  "raw_snapshot_path": ""
}
```

## 6.3 新增 CLI

```bash
python3 -m app.cli add-inbox-item \
  --workspace <workspace> \
  --url <url> \
  --user-intent "学习选题和视频结构"

python3 -m app.cli capture-xhs-link \
  --workspace <workspace> \
  --inbox-item-id <id>

python3 -m app.cli show-capture-result \
  --workspace <workspace> \
  --capture-id <id>
```

## 6.4 采集结果必须支持三种状态

```text
success
partial
failed
```

禁止：

- 采集不到时补造字段
- 将缺失数据填成 0
- 将估算值当真实值
- 页面受限时继续尝试绕过

## 6.5 验收标准

- 可以保存用户提供的单个链接
- 可以输出标准化采集结果
- 缺失字段明确记录
- 失败原因可读
- 不影响原有手动截图 / 文案录入方式
- 同一链接重复提交时可识别和更新，不生成无意义重复记录

---

# 7. 第二阶段：多模态拆解

## 7.1 新增对象：BenchmarkAnalysis

建议字段：

```json
{
  "id": "",
  "benchmark_post_id": "",
  "capture_id": "",
  "analysis_template": "video_tutorial",
  "observable_facts": {},
  "topic_analysis": {},
  "title_analysis": {},
  "cover_analysis": {},
  "structure_analysis": {},
  "visual_analysis": {},
  "audio_analysis": {},
  "comment_analysis": {},
  "engagement_analysis": {},
  "account_fit": {},
  "transferable_elements": [],
  "non_transferable_elements": [],
  "candidate_rule_ids": [],
  "derived_topic_ids": [],
  "uncertainties": [],
  "confidence": 0.0
}
```

## 7.2 分析模板

至少支持：

```text
video_tutorial
video_personal_story
video_review
image_carousel_tutorial
image_carousel_experience
case_study
listicle
```

先判断内容类型，再选择模板。

## 7.3 标准拆解维度

### 选题层

- 目标人群
- 核心痛点
- 内容承诺
- 信息差
- 争议性
- 收藏价值
- 评论诱因

### 标题 / 封面层

- 明确对象
- 结果感
- 时间成本
- 工具组合
- 情绪词
- 认知冲突
- 风险：是否夸张或过度承诺

### 视频层

- 前 1 秒视觉钩子
- 前 3 秒话术钩子
- 核心价值出现时间
- 镜头变化密度
- 字幕密度
- 口播结构
- 示例 / 证明
- 行动引导

### 图文层

- 首图点击理由
- 图片序列功能
- 信息层级
- 单图信息密度
- 收藏理由
- 最后一页互动设计

### 评论层

- 真实需求
- 高频疑问
- 异议
- 商业意向
- 无效评论
- 可衍生选题

## 7.4 新增 CLI

```bash
python3 -m app.cli analyze-captured-post \
  --workspace <workspace> \
  --capture-id <id>

python3 -m app.cli promote-to-benchmark \
  --workspace <workspace> \
  --inbox-item-id <id>
```

## 7.5 验收标准

- 图文和视频使用不同分析模板
- 所有推断与事实分离
- 公开互动数据只作为公开表现参考
- 每条候选规则必须关联证据
- 每个分析结果必须包含不确定项

---

# 8. 第三阶段：规则证据与生命周期

## 8.1 当前问题

当前规则卡主要是静态记录，缺少：

- 规则证据
- 状态
- 验证次数
- 成功 / 失败记录
- 场景边界
- 冲突处理
- 废弃机制

## 8.2 新增对象：RuleEvidence

建议字段：

```json
{
  "id": "",
  "rule_id": "",
  "source_type": "benchmark_post",
  "source_id": "",
  "source_fragment": "",
  "evidence_type": "content_structure",
  "observable_fact": "",
  "inference": "",
  "confidence": 0.0,
  "created_at": ""
}
```

## 8.3 扩展 RuleCard

新增：

```text
status
strength
validation_count
success_count
failure_count
last_validated_at
applicable_content_types
applicable_audiences
conflicts_with
supersedes
deprecated_reason
```

状态：

```text
candidate
approved
testing
validated
rejected
deprecated
```

强度：

```text
weak
medium
strong
```

## 8.4 规则升级逻辑

```text
外部对标产生
→ candidate

运营人员确认
→ approved

用于草稿或发布
→ testing

多次发布结果支持
→ validated

结果不支持
→ rejected

后续被更优规则替代
→ deprecated
```

## 8.5 规则冲突判断

不要再使用“同类型存在不同摘要 = 冲突”的简单规则。

改为：

1. 先判断是否语义重复
2. 再判断是否适用场景不同
3. 再判断是否可以合并
4. 最后才标记为冲突
5. 冲突必须交给 Codex 输出解释，不能自动删除

## 8.6 验收标准

- 所有规则可追溯到来源
- 规则可被确认、测试、验证、拒绝和废弃
- 重复规则可合并
- 冲突规则给出解释
- 生成草稿时优先使用 validated / strong 规则

---

# 9. 第四阶段：持续质量提升机制

## 9.1 新增对象：ContentQualityReview

建议字段：

```json
{
  "id": "",
  "draft_id": "",
  "review_type": "pre_publish",
  "account_fit_score": 0,
  "publishability_score": 0,
  "title_score": 0,
  "cover_score": 0,
  "structure_score": 0,
  "tone_score": 0,
  "revision_count": 0,
  "major_rewrite_required": false,
  "issues": [],
  "accepted_rules": [],
  "rejected_rules": [],
  "reviewer_notes": ""
}
```

## 9.2 核心指标

必须能统计：

```text
一次通过率
平均修改轮次
大改率
账号贴合度
可发布率
标题重写率
脚本重写率
规则命中率
规则验证成功率
```

## 9.3 周期性报告

新增：

```bash
python3 -m app.cli generate-quality-report \
  --workspace <workspace> \
  --period weekly
```

报告必须回答：

- 本周新增了哪些有效规则
- 哪些规则表现差
- 哪些内容类型最适合当前账号
- 哪些标题 / 封面模式被重复否定
- 修改成本是否下降
- 下一周需要补什么样本

## 9.4 验收标准

- 能比较第 1 周、第 2 周、第 4 周的质量趋势
- 能证明 Skill 是否降低修改成本
- 能指出造成质量下降的规则或样本
- 不能只报告生成数量

---

# 10. SKILL.md 改造要求

## 10.1 修改 Hard Boundaries

替换原来的绝对禁止采集：

```text
Do not perform bulk crawling, platform-wide search, automated account monitoring,
or bypass access controls.

The skill may invoke an approved local capture tool for a single user-provided
public link, limited to content visible in the user's authorized environment.
```

## 10.2 新增触发流程

### 指定链接分析

触发：

```text
分析这个小红书链接
把这个链接加入素材库
分析这个帖子是否值得对标
```

执行：

```text
1. 创建 ContentInboxItem
2. 调用 capture-xhs-link
3. 检查 capture_status
4. 读取账号档案、已有规则、历史反馈
5. 执行多模态拆解
6. 输出事实、推断、不确定项
7. 判断账号适配度
8. 生成候选规则
9. 等待运营人员确认是否提升为正式对标
```

## 10.3 用户态输出格式

```text
已获取到什么
缺失了什么
这篇内容最值得学习什么
哪些部分不适合当前账号
形成了哪些候选规则
下一步建议确认什么
```

## 10.4 技术细节默认隐藏

正常用户不看到：

- 文件路径
- JSON 名
- CLI 命令
- 模型名
- 抓取实现
- 媒体处理实现

只有明确要求技术细节时显示。

---

# 11. 文件与模块建议

```text
app/
├── capture/
│   ├── xhs_capture.py
│   ├── capture_result.py
│   └── capture_errors.py
├── media/
│   ├── video_metadata.py
│   ├── keyframes.py
│   ├── audio_transcription.py
│   ├── image_analysis.py
│   └── comment_parser.py
├── analysis/
│   ├── benchmark_analyzer.py
│   ├── analysis_templates.py
│   ├── account_fit.py
│   └── rule_candidate_builder.py
├── rules/
│   ├── lifecycle.py
│   ├── deduplication.py
│   ├── conflict_detection.py
│   └── validation.py
├── quality/
│   ├── content_review.py
│   ├── metrics.py
│   └── reports.py
└── cli/
    └── main.py
```

---

# 12. 数据迁移要求

- 不破坏当前 0.7.0 工作区
- 新字段必须提供默认值
- 旧 RuleCard 自动迁移为 `approved`
- 没有证据的旧规则标记为低置信或 `legacy`
- 旧 BenchmarkPost 仍可继续使用
- 新旧 CLI 至少保持一个版本兼容

---

# 13. 测试要求

## 13.1 单元测试

覆盖：

- 收件箱状态流转
- CaptureRecord 部分成功
- 缺失字段
- 链接重复
- 规则证据
- 规则生命周期
- 重复规则合并
- 场景不同但不冲突
- 规则废弃
- 质量指标计算

## 13.2 集成测试

场景：

```text
链接输入
→ 采集部分成功
→ 分析
→ 提升为对标
→ 候选规则
→ 运营人员确认
→ 生成草稿
→ 发布复盘
→ 规则更新
```

## 13.3 回归测试

必须保证：

```bash
python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=.pycache python3 -m compileall app tests
```

全部通过。

---

# 14. 开发顺序

## Phase 8：素材收件箱

- ContentInboxItem
- CaptureRecord
- add-inbox-item
- capture-xhs-link
- 去重
- 失败 / 部分成功

## Phase 9：多模态拆解

- BenchmarkAnalysis
- 视频 / 图文模板
- 评论洞察
- 事实与推断分离
- promote-to-benchmark

## Phase 10：规则生命周期

- RuleEvidence
- RuleCard 状态与强度
- 去重
- 合并
- 冲突
- 验证和废弃

## Phase 11：质量提升验证

- ContentQualityReview
- 修改成本
- 一次通过率
- 周报
- 趋势分析

每完成一个 Phase：

1. 更新 CHANGELOG
2. 更新 README
3. 更新 SKILL.md
4. 更新 docs
5. 增加测试
6. 提交验证结果

---

# 15. 不允许的实现方式

- 不允许直接把采集逻辑塞进 SKILL.md
- 不允许让 Codex 猜页面字段
- 不允许采集失败时生成伪数据
- 不允许新增功能但不增加测试
- 不允许将 Mock 输出作为最终用户内容
- 不允许规则只增不减
- 不允许把公开点赞数直接定义为爆款原因
- 不允许一次性重构整个项目而无阶段验收
- 不允许引入 UI 或商业化后台

---

# 16. 完成定义

本轮开发完成后，用户应能够：

```text
1. 给 Codex 一个小红书链接
2. Skill 自动加入素材收件箱
3. 获取当前可见内容
4. 对图文或视频进行结构化拆解
5. 判断对当前账号的借鉴价值
6. 形成有证据的候选规则
7. 由运营人员确认规则
8. 使用高置信规则生成选题和草稿
9. 发布后根据结果验证或淘汰规则
10. 在周报中看到内容质量和修改成本是否持续改善
```

产品最终不是“自动拆爆款工具”，而是：

> 将外部内容持续转化为当前账号可验证、可复用、可迭代运营能力的长期 Agent。

---

# 17. 给 Codex 的执行提示词

请读取仓库全部内容后执行本开发规格。

要求：

1. 先检查当前仓库结构、版本、已有模型、CLI、测试和文档。
2. 不要立即写代码，先输出：
   - 当前架构理解
   - 与本规格的差距
   - Phase 8 到 Phase 11 的实施方案
   - 需要修改和新增的文件
   - 数据迁移方案
   - 测试方案
3. 方案确认后，从 Phase 8 开始逐阶段实施。
4. 每个 Phase 必须：
   - 完成代码
   - 完成测试
   - 更新 README、SKILL.md、CHANGELOG 和相关 docs
   - 运行完整测试和 compileall
   - 汇报修改文件、测试结果和剩余风险
5. 保持以下边界：
   - Codex 自带模型负责最终分析和生成
   - Python / CLI / MCP 负责稳定采集、读写、校验和媒体处理
   - 不接第三方大模型 API
   - 不做批量爬虫
   - 不绕过访问控制
   - 不自动发布
6. 不允许一次性完成全部 Phase。每个 Phase 单独完成、验证和提交。
7. 发现规格中有冲突时，先基于产品目标提出最小修改，不得自行扩大产品范围。
8. 所有结论必须以当前仓库代码为依据，不得假设尚不存在的能力已经实现。


