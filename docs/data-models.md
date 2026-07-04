# Data Models

## 通用规则

- 每个模型都有 `id`、`created_at`、`updated_at`。
- 每条记录存为一个 JSON 文件。
- 标签字段统一保存标签 `id` 列表。
- 时间字段使用可读字符串，第一版只做非空校验，后续再收紧格式。
- `metrics`、`ai_analysis`、`quality_review` 等字段使用对象结构，便于后续扩展。

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

## CustomTag

用途：定义可绑定到多个对象的自定义标签。

字段：`id`、`name`、`type`、`description`、`scope`、`weight`。

基础校验：标签名称和描述不能为空；`type` 必须是 `preference`、`usage`、`goal`、`risk`、`source`、`custom` 之一；`scope` 必须来自允许绑定范围；`weight` 为 1 到 5 的整数。

允许绑定范围：`benchmark_account`、`benchmark_post`、`rule_card`、`topic_item`、`content_draft`、`publish_task`、`own_post`。

## RuleCard

用途：沉淀从对标内容和历史内容中提炼出的可复用规则。

字段：`id`、`name`、`type`、`source_ids`、`applicable_scenarios`、`rule_summary`、`examples`、`risks`、`adaptation_notes`、`tags`。

基础校验：规则名称、摘要和适配建议不能为空；来源、场景、示例、风险和标签必须是字符串列表。

## TopicItem

用途：记录选题池中的单个选题。

字段：`id`、`title`、`content_goal`、`content_format`、`source_rule_cards`、`reference_posts`、`reason`、`status`、`tags`。

基础校验：标题、目标、形式和理由不能为空；状态必须是 `idea`、`draft`、`reviewing`、`ready`、`archived` 之一。

## ContentDraft

用途：记录从选题生成的标题、封面文案、逐字稿和简单分镜。

字段：`id`、`topic_id`、`titles`、`cover_titles`、`script`、`shot_suggestions`、`status`、`quality_review`、`tags`。

基础校验：所属选题和脚本不能为空；标题、封面文案、分镜建议和标签必须是字符串列表；质量检查必须是对象。

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
