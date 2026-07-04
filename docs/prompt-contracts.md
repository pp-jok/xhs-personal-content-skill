# Prompt Contracts

## 目标

Phase 2 定义结构化 Prompt Contract 和 mock 服务，为后续工作流提供稳定输入输出协议。

本阶段不接真实模型 API，不输出不可解析的长文本，不做自动抓取或自动发布。

## 协议清单

- `analyze_benchmark_post`：分析单篇对标帖子，输出结构化分析、可借鉴点、不可借鉴点和规则卡片候选。
- `extract_rule_card`：从帖子分析结果中提取可复用规则卡片。
- `generate_topic_pool`：基于账号档案、标签和规则卡片生成选题池。
- `generate_content_draft`：基于选题生成标题、封面文案、视频逐字稿和简单分镜。
- `generate_publish_task`：把内容草稿转化为发布任务。
- `review_own_post`：基于已发布帖子和表现数据生成轻量复盘记录。

## 每个协议必须包含

- `id`：协议标识。
- `purpose`：协议目的。
- `input_schema`：输入 JSON 结构。
- `output_schema`：输出 JSON 结构。
- `constraints`：硬约束。
- `quality_standards`：质量标准。
- `failure_handling`：失败处理规则。

## Mock 服务边界

`MockPromptService` 只返回确定性的结构化 JSON，用于测试协议和后续工作流编排。

它不会：

- 调用真实模型 API。
- 自动采集外部内容。
- 自动发布内容。
- 根据外部平台状态做判断。
- 替代人工审核。

## Phase 3 入口计划

下一阶段在 `app/workflows/` 中编排以下流程：

1. 读取账号档案、标签、对标账号和对标帖子。
2. 调用 `analyze_benchmark_post` mock 输出分析结果。
3. 调用 `extract_rule_card` mock 输出规则卡片。
4. 调用 `generate_topic_pool` mock 输出选题。
5. 调用 `generate_content_draft` mock 输出草稿。
6. 调用 `generate_publish_task` mock 输出发布任务。
7. 使用 JSON 仓库写入对应数据目录。
