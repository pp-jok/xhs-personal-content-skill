# Benchmark To Publish Workflow

## Purpose

Run the local MVP loop from one benchmark post to one publish task.

## Steps

1. Load creator profile, benchmark post, and custom tags from JSON storage.
2. Run `analyze_benchmark_post`.
3. Update the benchmark post with structured analysis.
4. Run `extract_rule_card`.
5. Save rule cards.
6. Run `generate_topic_pool`.
7. Save topic items.
8. Run `generate_content_draft`.
9. Save content draft.
10. Run `generate_publish_task`.
11. Save publish task.

## Storage

- Rule cards: `data/rule-cards/`
- Topics: `data/topic-pool/`
- Drafts: `data/content-drafts/`
- Publish tasks: `data/publish-tasks/`

## Current Limits

- Uses mock prompt service only.
- Does not call external services.
- Does not publish content.
- Does not create UI.
