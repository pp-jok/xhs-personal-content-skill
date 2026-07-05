# xhs-personal-content-skill 能力实装开发方案 v1.2–v1.5

## 0. 文档目的

本方案用于继续开发 `pp-jok/xhs-personal-content-skill`。

当前仓库版本为 1.1.0，已经具备较完整的工程骨架：

- 素材收件箱
- 采集记录
- 对标内容分析结构
- 规则证据和生命周期
- 内容质量评价
- 质量报告
- Codex Skill 工作流
- 本地 JSON / Markdown 存储
- CLI 和测试

但以下能力尚未真正实现：

1. 指定链接的真实内容获取
2. 视频、图片、音频的真实预处理
3. 基于 Codex 的深度内容拆解
4. 结合账号上下文的适配分析
5. 多类型候选规则生成
6. 规则语义去重、合并和冲突裁决
7. 按真实时间周期计算质量趋势

本轮开发的目标不是继续增加数据模型，而是让已有功能名副其实。

---

# 1. 最终产品目标

用户在 Codex 中输入：

```text
分析这个小红书链接，重点看选题、前三秒和脚本结构：
<URL>
```

系统应完成：

```text
保存链接
→ 在用户授权的浏览器环境中读取当前可见内容
→ 保存标题、正文、媒体、互动数据和可见评论
→ 处理图片、视频、字幕、口播和关键帧
→ 读取当前账号档案、偏好、规则和历史评价
→ 由 Codex 完成深度拆解和账号适配判断
→ 生成有证据的候选规则
→ 用户确认后进入规则生命周期
→ 后续草稿生成使用高置信规则
→ 发布和人工评价后更新规则
→ 按周期判断质量和修改成本是否改善
```

产品定位：

> 将外部内容、运营人员判断和真实发布反馈，持续转化为当前账号可验证、可复用、可迭代运营能力的长期 Agent。

---

# 2. 核心开发原则

## 2.1 模型、接口和真实能力必须分离

以下内容不能混为一谈：

```text
存在 CaptureRecord
≠ 已实现链接采集

存在 BenchmarkAnalysis
≠ 已实现多模态分析

存在 weekly 参数
≠ 已实现周趋势报告

存在 conflicts 字段
≠ 已实现规则语义冲突判断
```

每个功能必须通过行为级验收测试，而不是只检查类、字段、CLI 或文件是否存在。

## 2.2 Codex 与 Python 的职责

### Codex 负责

- 理解内容
- 视频、图片和文案的语义分析
- 账号适配判断
- 可迁移和不可迁移因素判断
- 生成候选规则
- 规则语义去重、合并和冲突解释
- 内容生成
- 复盘推理

### Python / CLI / MCP 负责

- 浏览器采集
- 文件保存
- 媒体元数据提取
- 视频关键帧抽取
- 音频轨道提取
- 本地转写工具调用
- OCR 工具调用
- 输入组装
- JSON Schema 校验
- 确定性状态流转
- 持久化
- 时间过滤
- 统计计算

### 明确禁止

- 不允许 Python 使用少量关键词和固定文案作为正式内容分析
- 不允许 Mock 分析器作为正常 Skill 工作流默认实现
- 不允许用手动 JSON 导入冒充真实链接采集
- 不允许用全部历史数据累计统计冒充周报或月报
- 不允许使用字符串相等和规则类型相同冒充完整语义冲突判断

---

# 3. 版本与阶段规划

```text
v1.2：真实单链接采集
v1.3：真实媒体预处理与 Codex 分析协议
v1.4：账号适配、候选规则和语义关系裁决
v1.5：真实周期质量趋势与端到端验证
```

每个版本独立开发、测试、提交。

不得一次性实现全部版本。

---

# 4. v1.2：真实单链接采集

## 4.1 目标

给定一个用户当前在 Chrome 中可以正常访问的小红书链接，工具应自动读取当前页面可见内容。

手动 JSON 继续保留，但只能作为：

- 页面读取失败后的降级方式
- 测试夹具
- 用户主动导入已有资料的方式

不能作为 `capture-xhs-link` 的主要实现。

## 4.2 固定技术路线

第一版采用：

> Chrome DevTools Protocol（CDP）连接用户主动启动的 Chrome 调试实例。

不直接复用用户日常 Chrome 进程，不读取用户默认 Profile。

用户通过明确命令启动一个专用调试浏览器目录：

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.xhs-personal-content-skill/chrome-profile"
```

首次使用时用户自行登录小红书。

采集器连接：

```text
http://127.0.0.1:9222
```

建议使用 Playwright 的 `connect_over_cdp`。

依赖必须写入项目依赖文件和安装文档。

## 4.3 安全与边界

必须遵守：

- 只处理用户明确提交的单个链接
- 不遍历推荐流
- 不搜索平台
- 不自动打开其他帖子
- 不无限滚动评论
- 不绕过验证码
- 不绕过登录限制
- 不伪造 Cookie
- 不读取与当前页面无关的浏览器数据
- 默认最多读取当前已加载或最多前 30 条可见评论
- 采集失败立即返回可读原因
- 不将带鉴权参数的媒体 URL 展示给用户

## 4.4 新增模块

```text
app/capture/browser/
├── cdp_client.py
├── chrome_session.py
├── xhs_page_reader.py
├── xhs_dom_extractors.py
├── url_normalizer.py
└── capture_diagnostics.py
```

## 4.5 `capture-xhs-link` 新行为

```bash
python3 -m app.cli.main capture-xhs-link \
  --workspace <workspace> \
  --inbox-item-id <id> \
  --cdp-url http://127.0.0.1:9222
```

行为：

1. 读取收件箱条目
2. 规范化短链或完整链接
3. 连接用户授权 Chrome
4. 找到当前已打开页面，或在专用浏览器中新开该 URL
5. 等待页面主要内容加载
6. 提取当前可见内容
7. 保存原始页面快照
8. 保存图片和视频资源引用或本地文件
9. 建立 `CaptureRecord`
10. 更新 `ContentInboxItem`
11. 输出采集诊断

## 4.6 必须提取的字段

至少尝试获取：

```text
source_url
canonical_url
title
body
content_type
author.name
published_at
metrics.likes
metrics.collects
metrics.comments
metrics.shares
images
video
comments
raw_snapshot_path
```

无法获取时使用 `null` 或空集合，并写入 `missing_fields`。

禁止将缺失指标填为 `0`。

## 4.7 媒体处理边界

v1.2 只要求：

- 识别图片列表
- 保存用户当前可见图片
- 识别视频元素
- 保存视频页面引用或当前可获得的视频文件
- 记录视频下载是否成功
- 记录媒体来源和采集时间

v1.2 不要求完成视频语义分析。

## 4.8 采集诊断

新增：

```json
{
  "page_reachable": true,
  "login_required": false,
  "captcha_detected": false,
  "dom_version": "xhs-web-2026-07",
  "selectors_succeeded": [],
  "selectors_failed": [],
  "media_download_status": "partial",
  "comment_limit": 30
}
```

## 4.9 v1.2 强制验收场景

### 场景 A：可访问图文帖

必须输出：

- 非空标题或正文至少一项
- `content_type=image` 或 `mixed`
- 至少一张图片
- 采集状态不能是 `failed`
- 原始快照存在

### 场景 B：可访问视频帖

必须输出：

- 非空标题或正文至少一项
- `content_type=video` 或 `mixed`
- `video` 字段包含页面媒体信息
- 采集状态不能是 `failed`

### 场景 C：登录受限

必须输出：

- `capture_status=failed` 或 `partial`
- 明确 `login_required`
- 不尝试绕过
- 不生成伪内容

### 场景 D：页面结构变化

必须输出：

- 诊断信息
- 失败 selector
- 原始快照
- 不得静默返回空成功

### 场景 E：手动文件

`--manual-file` 可以继续工作，但结果必须标记：

```text
capture_method=manual
```

真实浏览器采集必须标记：

```text
capture_method=browser_authorized
```

## 4.10 v1.2 完成定义

以下条件全部满足才允许发布 v1.2：

- 有真实 CDP 浏览器采集实现
- 有至少一个本地录制页面 fixture 或 HTML fixture
- 有图文帖、视频帖、失败页测试
- `capture-xhs-link` 无 `--manual-file` 时不再直接固定失败
- README 明确启动专用 Chrome 的步骤
- CHANGELOG 不得声称突破访问控制
- 手动导入被明确标记为降级方式

---

# 5. v1.3：真实媒体预处理与 Codex 分析协议

## 5.1 目标

将采集到的图片和视频转换成 Codex 可稳定理解的本地分析包。

Python 不负责最终语义结论，只负责生成可靠输入。

## 5.2 新增对象：MediaAnalysisBundle

```json
{
  "id": "",
  "capture_id": "",
  "media_type": "video",
  "source_files": [],
  "video_metadata": {},
  "keyframes": [],
  "audio_path": null,
  "transcript": [],
  "ocr_results": [],
  "image_sequence": [],
  "processing_status": "success",
  "missing_components": [],
  "warnings": [],
  "created_at": ""
}
```

## 5.3 视频预处理

必须实现：

- 视频时长、尺寸、帧率
- 音频轨道提取
- 固定间隔取帧
- 镜头切换附近关键帧
- 前 1 秒、3 秒、5 秒关键帧
- 关键帧时间戳
- 视频处理失败诊断

推荐使用：

- `ffmpeg`
- `ffprobe`

## 5.4 音频转写

允许：

1. 本地系统已有 Whisper CLI
2. 本地开源转写工具
3. 用户提供字幕或转写文本

不允许：

- 接第三方在线大模型 API
- 没有转写结果时虚构口播内容

输出包含：

```text
start_time
end_time
text
confidence
source
```

## 5.5 OCR

用于：

- 封面文字
- 视频字幕
- 图片中的流程和清单

结果保留：

```text
file
frame_time
text
confidence
bounding_box
```

OCR 低置信结果不得作为确定事实。

## 5.6 图片序列

每张图片记录：

```text
position
local_path
dimensions
ocr_text
caption_or_alt
```

## 5.7 新增 CLI

```bash
python3 -m app.cli.main prepare-media-analysis \
  --workspace <workspace> \
  --capture-id <id>

python3 -m app.cli.main export-analysis-context \
  --workspace <workspace> \
  --capture-id <id> \
  --output <context.json>
```

## 5.8 Codex 分析协议

新增：

```text
prompts/contracts/benchmark-analysis.schema.json
prompts/contracts/benchmark-analysis-instructions.md
```

Codex 最终输出必须包含：

```text
observable_facts
inferences
uncertainties
topic_analysis
title_analysis
cover_analysis
structure_analysis
visual_analysis
audio_analysis
comment_analysis
engagement_analysis
account_fit
transferable_elements
non_transferable_elements
candidate_rules
derived_topics
```

## 5.9 正常工作流

```text
采集器生成 CaptureRecord
→ 媒体预处理生成 MediaAnalysisBundle
→ CLI 导出分析上下文
→ Codex读取上下文和账号资料
→ Codex生成 BenchmarkAnalysis JSON
→ CLI校验并保存
```

## 5.10 禁止的实现

不得继续将以下逻辑作为正式分析：

```python
if "如何" in title:
    inference = "标题有结果感"
```

可以保留 `MockBenchmarkAnalyzer`，但必须：

- 位于 tests 或明确 mock 模块
- 只用于测试结构
- 正常 SKILL.md 流程不得调用
- README 不得把 mock 输出称为真实分析

## 5.11 v1.3 强制验收

### 视频输入

必须生成：

- 前 1 秒关键帧
- 前 3 秒关键帧
- 至少 3 张带时间戳关键帧
- 视频元数据
- 音频状态
- 转写或明确缺失原因
- OCR 或明确缺失原因

### 图文输入

必须生成：

- 图片顺序
- 每张图片本地路径
- OCR 结果或明确缺失原因
- 首图标识

### Codex 分析

完整媒体包与缺失媒体包的分析必须体现差异：

- 完整包引用视觉或音频事实
- 缺失包降低置信度
- 不得编造口播、字幕或画面事实

---

# 6. v1.4：账号适配、候选规则和语义关系裁决

## 6.1 目标

同一篇外部内容对不同账号必须产生不同适配判断。

## 6.2 新增对象：AnalysisContext

```json
{
  "creator_profile": {},
  "active_rules": [],
  "rejected_rules": [],
  "preference_tags": [],
  "recent_quality_reviews": [],
  "recent_review_records": [],
  "related_benchmark_posts": [],
  "current_capture": {},
  "media_analysis_bundle": {}
}
```

## 6.3 分析接口

不得继续使用：

```python
analyze_capture(capture)
```

改为构建上下文：

```python
build_analysis_context(
    capture_id,
    creator_id,
    workspace
)
```

CLI：

```bash
python3 -m app.cli.main build-analysis-context \
  --workspace <workspace> \
  --capture-id <id> \
  --creator-id <creator-id>
```

## 6.4 账号适配输出

必须输出：

```text
fit_score
fit_reasons
risk_reasons
transferable_elements
non_transferable_elements
required_adaptations
violated_rules
supported_rules
missing_account_context
```

## 6.5 候选规则要求

每篇内容允许生成 0–5 条候选规则。

规则类型至少支持：

```text
topic
title
cover
opening
structure
script
visual
comment
operation
risk
```

每条规则包含：

```text
rule_type
rule_summary
source_fragment
observable_fact
inference
applicable_scenarios
applicable_content_types
applicable_audiences
risks
adaptation_notes
confidence
```

没有具体证据时不得生成规则。

## 6.6 规则状态流

```text
Codex生成候选
→ candidate
→ 用户确认
→ approved
→ 被草稿使用
→ testing
→ 发布或质量评价
→ validated / rejected
→ 被更好规则替代
→ deprecated
```

不得自动把外部规则升级为 `validated`。

## 6.7 规则关系处理

### Python：候选召回

依据：

- 相同类型
- 重叠场景
- 相同标签
- 文本相似度
- 相同人群
- 相同内容形式

### Codex：语义裁决

关系：

```text
duplicate
mergeable
complementary
context_specific
conflicting
unrelated
```

### Python：校验和保存

Python 不做最终语义裁决。

## 6.8 新增对象：RuleRelationDecision

```json
{
  "id": "",
  "rule_a_id": "",
  "rule_b_id": "",
  "relation": "complementary",
  "reason": "",
  "recommended_action": "keep_both",
  "merged_rule_candidate": null,
  "confidence": 0.0,
  "decided_by": "codex",
  "created_at": ""
}
```

## 6.9 v1.4 强制验收

### 两个不同账号

账号 A：专业、克制、禁止夸张承诺。  
账号 B：强情绪、追求增长、允许强结果表达。

对同一篇强承诺内容分析，必须出现：

- 不同 fit_score
- 不同风险判断
- 不同可迁移元素
- 不同改造建议

### 已有强规则

账号存在“禁止保证、必爆、一定成功”等规则时，对含“保证爆款”的帖子：

- 必须识别冲突
- 加入不可迁移项
- 给出降级表达建议

### 多候选规则

有明显标题、封面、开头、结构特征的视频，必须生成多于一条不同类型规则。

### 互补规则

“标题明确目标人群”和“标题明确结果收益”不得判为冲突，应判为 `complementary`。

### 真正冲突

“标题避免数字”和“清单类标题必须使用具体数字”在相同场景下应判为 `conflicting`，并解释边界。

---

# 7. v1.5：真实周期质量趋势

## 7.1 目标

报告必须回答：

- 本周是否比上周好
- 修改成本是否下降
- 哪些规则提高了通过率
- 哪些规则持续失败
- 样本是否足以支持结论

## 7.2 扩展 ContentQualityReview

新增：

```text
reviewed_at
draft_version
previous_review_id
rules_used
content_type
reviewer_id_or_source
```

## 7.3 CLI

```bash
python3 -m app.cli.main generate-quality-report \
  --workspace <workspace> \
  --period weekly \
  --period-start 2026-07-06 \
  --creator-id creator-main
```

支持：

```text
weekly
monthly
custom
```

## 7.4 时间过滤

必须按 `reviewed_at` 或可信时间字段过滤。

报告同时计算：

```text
current_period
previous_period
delta
sample_size
```

## 7.5 样本不足

当：

```text
review_count < 5
```

必须输出：

> 样本不足，只展示观察值，不判断稳定趋势。

## 7.6 规则效果关联

至少支持：

```text
draft.rules_used
quality_review.accepted_rules
quality_review.rejected_rules
```

统计：

- 规则使用次数
- 接受次数
- 拒绝次数
- 平均账号适配分
- 平均可发布分
- 大改率
- 规则验证成功率

## 7.7 报告输出

必须包括：

```text
当前周期指标
上一周期指标
变化值
样本量
已验证规则
表现差规则
反复出现的问题
修改成本变化
内容形式差异
下一周期建议
不确定性说明
```

## 7.8 v1.5 强制验收

### 时间过滤

10 条评价中，5 条当前周、5 条上一周，当前周 `review_count` 必须为 5。

### 趋势变化

上一周平均修改 3 次，本周 1 次，必须显示：

```text
average_revision_count_delta = -2
```

### 样本不足

本周只有 2 条评价，必须明确样本不足。

### 规则效果

某规则使用 5 次，接受 4 次、拒绝 1 次，报告必须展示对应统计。

---

# 8. 端到端验收

完成 v1.5 后必须演示：

```text
1. 初始化账号工作区
2. 写入账号档案
3. 启动专用 Chrome 并打开指定链接
4. capture-xhs-link 自动读取页面
5. prepare-media-analysis 生成媒体包
6. build-analysis-context 读取账号上下文
7. Codex 生成 BenchmarkAnalysis
8. 生成 2–5 条候选规则
9. 用户确认一条
10. 使用规则生成草稿
11. 记录质量评价
12. 记录规则测试结果
13. 生成当前周期和上一周期对比报告
```

端到端报告保存：

```text
reports/e2e_capability_validation.md
```

必须区分：

```text
真实实现
降级实现
Mock
尚未实现
```

---

# 9. 文档命名规范

不得使用模糊能力名称。

仅支持人工导入时，不写：

```text
支持单链接采集
```

应写：

```text
支持单链接素材收件箱和用户可见内容手动导入
```

只有真实浏览器采集成功后才能写：

```text
支持在用户授权 Chrome 环境中读取单个指定链接的当前可见内容
```

仅有分析字段时，不写：

```text
支持多模态分析
```

应写：

```text
支持多模态分析结果的数据结构
```

关键帧、转写、OCR 和 Codex 分析接通后，才能写：

```text
支持图片序列、视频关键帧、字幕/口播和评论的多模态拆解
```

---

# 10. 测试策略

测试必须验证行为和内容差异，不得只验证类、字段或 CLI 存在。

测试类型：

- 单元测试：URL、字段提取、媒体处理、时间过滤、状态流转、Schema
- Fixture 集成测试：本地 HTML、图片、短视频和评论
- 浏览器集成测试：标记为 `@browser_integration`
- Codex 人工验收测试：固定输入和关键断言

---

# 11. 数据迁移

- 保持 1.1.0 数据可读取
- 新字段提供默认值
- 老 CaptureRecord 标记 `legacy_manual_capture`
- 老 BenchmarkAnalysis 标记 `legacy_template_analysis`
- 老质量报告不用于周期趋势
- 不自动删除旧数据
- 提供迁移命令和 dry-run

```bash
python3 -m app.cli.main migrate-workspace \
  --workspace <workspace> \
  --from-version 1.1.0 \
  --to-version 1.5.0 \
  --dry-run
```

---

# 12. 每个版本交付要求

每个版本必须完成：

1. 代码
2. 单元测试
3. Fixture 集成测试
4. 文档
5. CHANGELOG
6. 数据迁移说明
7. 能力状态说明
8. 完整测试结果
9. 已知风险
10. 未完成事项

不得只更新 README 和版本号。

---

# 13. 给 Codex 的执行指令

请在 `pp-jok/xhs-personal-content-skill` 当前 `main` 分支代码基础上执行本方案。

## 执行规则

1. 先完整读取 README、CHANGELOG、SKILL.md、docs、app 和 tests。
2. 核实当前 1.1.0 的真实能力，不以 README 名称代替代码事实。
3. 不要立即写代码。
4. 第一轮只输出：
   - 当前能力审计
   - v1.2 差距
   - 固定技术方案
   - 依赖变化
   - 文件清单
   - 迁移影响
   - 测试计划
   - 风险和降级路径
5. 未确认 v1.2 方案前，不进入 v1.3。
6. 每个版本单独完成，禁止一次性开发 v1.2–v1.5。
7. 每个版本完成后运行：
   ```bash
   python3 -m unittest discover -s tests -v
   PYTHONPYCACHEPREFIX=.pycache python3 -m compileall app tests
   ```
8. 新增 Playwright、ffmpeg 或本地转写依赖时，必须检查、记录安装步骤和降级路径。
9. 不接第三方模型 API。
10. 不做平台级抓取、批量抓取、自动监控或绕过访问限制。
11. 不自动发布。
12. 不增加 UI 或商业化后台。
13. 不得用以下替代实现通过验收：
   - 手动 JSON 代替真实浏览器采集
   - 固定关键词代替 Codex 分析
   - 固定模板代替账号适配判断
   - 字符串相等代替语义关系裁决
   - 全量累计统计代替周期趋势
14. 环境无法完成真实浏览器集成时：
   - 不得标记为已完成
   - 先完成接口、fixture 和诊断
   - CHANGELOG 标记为 partially implemented
15. README 必须准确标注：
   - 已实现
   - 降级可用
   - 仅测试
   - 尚未实现

## 第一轮任务

现在只执行以下任务，不写代码：

> 审计当前 1.1.0 的真实能力，并输出 v1.2“用户授权 Chrome 单链接采集”的详细实施计划。

输出必须包括：

1. 当前 `capture-xhs-link` 的真实行为
2. 手动导入与真实浏览器采集的差异
3. CDP + Playwright 实施设计
4. URL 规范化和短链处理
5. 页面字段提取策略
6. 媒体保存策略
7. 评论读取上限
8. 登录、验证码和页面变化诊断
9. 新增和修改文件列表
10. Fixture 测试设计
11. 浏览器集成测试设计
12. v1.2 逐条验收映射
13. 已知风险
14. 降级路径
15. 本阶段不做事项

第一轮不得：

- 修改代码
- 修改版本号
- 更新 README
- 安装依赖
- 创建提交
- 开始 v1.3
