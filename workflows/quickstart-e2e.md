# Quickstart End-to-End Flow

## Minimum Inputs

- `CreatorProfile`: `creator-main`
- `BenchmarkPost`: `benchmark-post-001`
- `CustomTag`: `tag-usage-topic`

## Commands

1. Import the creator profile.
2. Import the benchmark post.
3. Import the custom tag.
4. Run `BenchmarkToPublishWorkflow` through the CLI.
5. Inspect generated rule cards, topics, drafts, and publish tasks.

## Expected Outputs

- `rule-card-from-benchmark-post-001-1`
- `topic-from-benchmark-post-001-1`
- `draft-from-benchmark-post-001-1`
- `publish-task-from-benchmark-post-001-1`

## Boundaries

This flow uses local files and the mock prompt service only.
