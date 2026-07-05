# Data Models

## 通用规则

- 每个模型都有 `id`、`created_at`、`updated_at`。
- 每个模型都支持低门槛录入元数据：`missing_fields`、`confidence`、`source_type`、`source_note`、`user_reason`、`created_from`。
- 每条记录存为一个 JSON 文件。
- 标签字段统一保存标签 `id` 列表。
- 时间字段使用可读字符串，第一版只做非空校验，后续再收紧格式。
- `metrics`、`ai_analysis`、`quality_review` 等字段使用对象结构，便于后续扩展。

## 低门槛录入元数据

真实用户经常只提供部分信息。第一版不应为了通过校验编造内容，而应先保存可用信息，再标记缺口和来源。

通用元数据字段：

- `missing_fields`：仍需补充的字段名列表。
- `confidence`：当前记录可信度，范围 0 到 1。
- `source_type`：来源类型，例如 `user_input`、`screenshot`、`manual_template`、`user_feedback`。
- `source_note`：来源补充说明。
- `user_reason`：用户给出的选择、喜欢或不喜欢原因。
- `created_from`：创建来源，例如 `add-feedback`、`manual-intake`、`validate-real-sample`。

原则：

- 能保存就先保存。
- 不确定就标记不确定。
- 不要为了通过校验编造字段。

## CreatorProfile

用途：记录创作者主账号档案。

字段：`id`、`name`、`platform`、`positioning`、`target_audience`、`content_style`、`forbidden_expressions`、`goals`、`content_formats`、`publish_frequency`、`notes`。

基础校验：账号名称、平台、定位、发布频率不能为空；列表字段必须是字符串列表。

## BenchmarkAccount

用途：记录对标账号及账号级学习摘要。

字段：`id`、`name`、`url`、`niche`、`reason_to_follow`、`learnable_points`、`non_learnable_points`、`tags`、`summary`。

基础校验：名称、领域、关注原因和摘要不能为空；标签必须是标签 `id` 列表。

## BenchmarkPost

用途：记录单篇对标帖子、分析结果和规则卡片候选。

字段：`id`、`account_id`、`title`、`url`、`content_type`、`cover_text`、`raw_content`、`metrics`、`tags`、`ai_analysis`、`borrowable_points`、`non_borrowable_points`、`rule_card_candidates`。

基础校验：所属账号、标题、内容类型、原始内容不能为空；分析结果和指标必须是对象；规则卡片候选必须是对象列表。

## ContentInboxItem

用途：记录用户主动提供的单个小红书链接，在采集或分析前先进入素材收件箱。

字段：`id`、`source_url`、`source_platform`、`status`、`capture_status`、`content_type`、`user_intent`、`user_reason`、`requested_focus`、`captured_at`、`missing_fields`、`warnings`、`confidence`。

基础校验：链接不能为空；平台第一版固定为 `xiaohongshu`；`status` 必须是 `inbox`、`capturing`、`captured`、`analyzed`、`promoted_to_benchmark`、`rejected`、`archived` 之一；`capture_status` 必须是 `pending`、`success`、`partial`、`failed` 之一。

说明：同一链接重复提交时应更新原记录，不应生成无意义重复素材。

## CaptureRecord

用途：记录单个链接当前可见内容的标准化采集结果。

字段：`id`、`inbox_item_id`、`source_url`、`capture_method`、`capture_status`、`captured_at`、`title`、`body`、`content_type`、`author`、`metrics`、`images`、`video`、`comments`、`available_fields`、`missing_fields`、`warnings`、`raw_snapshot_path`。

基础校验：所属收件箱条目和链接不能为空；采集方式必须是 `manual` 或 `browser_authorized`；采集状态必须是 `pending`、`success`、`partial`、`failed` 之一；互动数据必须是对象，缺失值用 `null`，不能用 `0` 伪造。

说明：采集不到完整内容时必须记录缺失字段和 warning，不允许补造标题、正文、指标或评论。

## BenchmarkAnalysis

用途：记录采集内容的结构化拆解结果，为是否提升为对标帖、候选规则和衍生选题提供依据。

字段：`id`、`benchmark_post_id`、`capture_id`、`analysis_template`、`observable_facts`、`topic_analysis`、`title_analysis`、`cover_analysis`、`structure_analysis`、`visual_analysis`、`audio_analysis`、`comment_analysis`、`engagement_analysis`、`account_fit`、`transferable_elements`、`non_transferable_elements`、`candidate_rule_ids`、`derived_topic_ids`、`uncertainties`、`confidence`。

基础校验：采集记录不能为空；分析模板必须是 `video_tutorial`、`video_personal_story`、`video_review`、`image_carousel_tutorial`、`image_carousel_experience`、`case_study`、`listicle` 之一；事实、分析和账号适配字段必须是对象；可迁移点、不可迁移点、候选规则、不确定项必须是字符串列表。

说明：`observable_facts` 只保存采集记录中的可见事实；各分析字段中的 `inference` 才保存推断。公开互动数据只能作为表现参考，不能解释为确定原因。

## CustomTag

用途：定义可绑定到多个对象的自定义标签。

字段：`id`、`name`、`type`、`description`、`scope`、`weight`。

基础校验：标签名称和描述不能为空；`type` 必须是 `preference`、`usage`、`goal`、`risk`、`source`、`custom` 之一；`scope` 必须来自允许绑定范围；`weight` 为 1 到 5 的整数。

允许绑定范围：`benchmark_account`、`benchmark_post`、`rule_card`、`topic_item`、`content_draft`、`publish_task`、`own_post`。

## RuleCard

用途：沉淀从对标内容和历史内容中提炼出的可复用规则。

字段：`id`、`name`、`type`、`source_ids`、`applicable_scenarios`、`rule_summary`、`examples`、`risks`、`adaptation_notes`、`tags`、`status`、`strength`、`validation_count`、`success_count`、`failure_count`、`last_validated_at`、`applicable_content_types`、`applicable_audiences`、`conflicts_with`、`supersedes`、`deprecated_reason`。

基础校验：规则名称、摘要和适配建议不能为空；来源、场景、示例、风险和标签必须是字符串列表；状态必须是 `candidate`、`approved`、`testing`、`validated`、`rejected`、`deprecated` 之一；强度必须是 `weak`、`medium`、`strong` 之一；验证次数不能为负数。

说明：旧规则默认视为 `approved`，避免破坏旧工作区。生成草稿时应优先参考 `validated` 或 `strong` 规则。

## RuleEvidence

用途：记录规则的证据来源，让每条规则能追溯到可见事实和对应推断。

字段：`id`、`rule_id`、`source_type`、`source_id`、`source_fragment`、`evidence_type`、`observable_fact`、`inference`、`confidence`。

基础校验：规则、来源、来源片段、证据类型、可见事实和推断不能为空；来源类型必须是 `benchmark_post`、`benchmark_analysis`、`user_feedback`、`own_post`、`review_record` 之一。

说明：`observable_fact` 只保存真实可见内容，`inference` 保存由 Codex 或运营人员做出的判断。

## TopicItem

用途：记录选题池中的单个选题。

字段：`id`、`title`、`content_goal`、`content_format`、`source_rule_cards`、`reference_posts`、`reason`、`status`、`tags`。

基础校验：标题、目标、形式和理由不能为空；状态必须是 `idea`、`draft`、`reviewing`、`ready`、`archived` 之一。

## ContentDraft

用途：记录从选题生成的标题、封面文案、逐字稿和简单分镜。

字段：`id`、`topic_id`、`titles`、`cover_titles`、`script`、`shot_suggestions`、`status`、`quality_review`、`tags`。

基础校验：所属选题和脚本不能为空；标题、封面文案、分镜建议和标签必须是字符串列表；质量检查必须是对象。

## ContentQualityReview

用途：记录草稿或发布前后的人工质量评价，用于判断 Skill 是否真的越来越懂当前账号。

字段：`id`、`draft_id`、`review_type`、`account_fit_score`、`publishability_score`、`title_score`、`cover_score`、`structure_score`、`tone_score`、`revision_count`、`major_rewrite_required`、`issues`、`accepted_rules`、`rejected_rules`、`reviewer_notes`。

基础校验：所属草稿不能为空；`review_type` 必须是 `pre_publish`、`post_publish`、`revision` 之一；各项评分必须是 0 到 5 的整数；修改次数不能为负数；`issues` 必须是对象列表；规则引用必须是字符串列表。

说明：它不评价“生成了多少”，而评价“是否少改、是否像这个账号、是否可发布”。`issues` 建议记录问题区域，例如 `title`、`cover`、`script`、`tone`，以及后续动作，例如 `rewrite`、`keep`、`avoid`。

## PublishTask

用途：把草稿转为发布任务，并为未来多账号扩展保留 `account_id`。

字段：`id`、`account_id`、`draft_id`、`planned_publish_time`、`content_goal`、`status`、`materials_needed`、`result_metrics`、`review_summary`、`tags`。

基础校验：账号、草稿、计划时间和内容目标不能为空；状态必须是 `planned`、`preparing`、`ready`、`published`、`cancelled` 之一。

## OwnPost

用途：记录已发布帖子及后续复盘关联。

字段：`id`、`account_id`、`title`、`url`、`content_type`、`published_at`、`metrics`、`tags`、`source_topic_id`、`review_record_id`。

基础校验：账号、标题、内容类型、发布时间和来源选题不能为空；指标必须是对象。

## ReviewRecord

用途：记录已发布帖子的复盘结果、经验和规则更新建议。

字段：`id`、`own_post_id`、`performance_summary`、`lessons`、`next_actions`、`rule_updates`。

基础校验：已发布帖子和表现摘要不能为空；经验和后续动作必须是字符串列表；规则更新必须是对象列表。
