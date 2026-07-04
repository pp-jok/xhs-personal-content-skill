from __future__ import annotations

from typing import Any

from app.models.core import ValidationError, require_dict
from app.services.prompt_contracts import PromptContract


class MockPromptService:
    def __init__(self, contracts: dict[str, PromptContract]) -> None:
        self.contracts = contracts

    def run(self, contract_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        require_dict(payload, "payload")
        if contract_id not in self.contracts:
            raise ValidationError(f"Unknown prompt contract: {contract_id}")

        handlers = {
            "analyze_benchmark_post": self._analyze_benchmark_post,
            "extract_rule_card": self._extract_rule_card,
            "generate_topic_pool": self._generate_topic_pool,
            "generate_content_draft": self._generate_content_draft,
            "generate_publish_task": self._generate_publish_task,
            "review_own_post": self._review_own_post,
        }
        return handlers[contract_id](payload)

    def _analyze_benchmark_post(self, payload: dict[str, Any]) -> dict[str, Any]:
        post = payload.get("benchmark_post", {})
        creator = payload.get("creator_profile", {})
        title = post.get("title", "未命名帖子")
        positioning = creator.get("positioning", "当前账号定位")

        return {
            "ai_analysis": {
                "hook": f"围绕「{title}」提炼具体开头。",
                "structure": "场景、问题、方法、行动提醒",
                "audience_fit": f"需要人工确认是否贴合「{positioning}」。",
                "style_fit": "保持具体、真诚、可执行。",
            },
            "borrowable_points": ["保留清晰场景", "保留步骤化表达"],
            "non_borrowable_points": ["不使用夸大承诺", "不复制原文表达"],
            "rule_card_candidates": [
                {
                    "name": "场景化开头规则",
                    "type": "structure",
                    "summary": "开头先说明具体人群和使用场景。",
                }
            ],
            "warnings": [],
        }

    def _extract_rule_card(self, payload: dict[str, Any]) -> dict[str, Any]:
        post_id = payload.get("benchmark_post_id", "unknown-post")
        analysis = payload.get("analysis_result", {})
        candidates = analysis.get("rule_card_candidates", [])
        first = candidates[0] if candidates else {}

        return {
            "rule_cards": [
                {
                    "name": first.get("name", "场景化表达规则"),
                    "type": first.get("type", "structure"),
                    "source_ids": [post_id],
                    "applicable_scenarios": ["选题拆解", "脚本开头"],
                    "rule_summary": first.get("summary", "先给出具体场景，再展开方法。"),
                    "examples": ["给新手的 3 步执行方法"],
                    "risks": ["避免过度承诺", "避免脱离当前账号定位"],
                    "adaptation_notes": "使用当前账号的真诚表达方式重写。",
                    "tags": [],
                }
            ],
            "warnings": [],
        }

    def _generate_topic_pool(self, payload: dict[str, Any]) -> dict[str, Any]:
        creator = payload.get("creator_profile", {})
        rule_cards = payload.get("rule_cards", [])
        reference_posts = payload.get("reference_posts", [])
        topic_count = max(1, min(int(payload.get("topic_count", 1)), 5))
        first_rule = rule_cards[0] if rule_cards else {}
        first_post = reference_posts[0] if reference_posts else {}
        content_format = (creator.get("content_formats") or ["图文"])[0]
        goal = (creator.get("goals") or ["建立信任"])[0]

        topics = []
        for index in range(topic_count):
            topics.append(
                {
                    "title": f"适合当前账号的可执行选题 {index + 1}",
                    "content_goal": goal,
                    "content_format": content_format,
                    "source_rule_cards": [first_rule.get("id")] if first_rule.get("id") else [],
                    "reference_posts": [first_post.get("id")] if first_post.get("id") else [],
                    "reason": "来自账号定位、规则卡片和参考帖子，适合继续人工筛选。",
                    "tags": first_rule.get("tags", []) if isinstance(first_rule.get("tags", []), list) else [],
                }
            )

        return {"topics": topics, "warnings": []}

    def _generate_content_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        topic = payload.get("topic", {})
        title = topic.get("title", "未命名选题")

        return {
            "draft": {
                "topic_id": topic.get("id", ""),
                "titles": [f"{title}：一个更容易执行的版本"],
                "cover_titles": ["简单执行版"],
                "script": "先说明具体场景，再给出三个可以当天完成的小步骤，最后提醒记录反馈。",
                "shot_suggestions": ["展示问题场景", "展示步骤清单", "展示完成后的记录"],
                "quality_review": {
                    "account_fit": "贴合当前账号的具体、可执行风格。",
                    "risk": "需要人工检查是否有过度承诺。",
                },
                "tags": topic.get("tags", []),
            },
            "warnings": [],
        }

    def _generate_publish_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        creator = payload.get("creator_profile", {})
        draft = payload.get("content_draft", {})

        return {
            "publish_task": {
                "account_id": creator.get("id", ""),
                "draft_id": draft.get("id", ""),
                "planned_publish_time": payload.get("planned_publish_time", ""),
                "content_goal": (creator.get("goals") or ["建立信任"])[0],
                "status": "planned",
                "materials_needed": ["确认标题", "确认封面文案", "检查素材是否齐全"],
                "tags": draft.get("tags", []),
            },
            "warnings": [],
        }

    def _review_own_post(self, payload: dict[str, Any]) -> dict[str, Any]:
        own_post = payload.get("own_post", {})
        related_rule_cards = payload.get("related_rule_cards", [])

        return {
            "review_record": {
                "own_post_id": own_post.get("id", ""),
                "performance_summary": "基于输入指标生成轻量观察，需结合发布时间和内容目标人工判断。",
                "lessons": ["保留表现较好的结构", "检查弱指标对应的表达位置"],
                "next_actions": ["补充同主题选题", "更新相关规则卡片"],
                "rule_updates": [
                    {
                        "rule_card_id": related_rule_cards[0].get("id", ""),
                        "suggestion": "补充本次发布后的适用场景和风险提醒。",
                    }
                ]
                if related_rule_cards
                else [],
            },
            "warnings": [],
        }
