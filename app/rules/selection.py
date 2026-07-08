from __future__ import annotations

from app.models.core import RuleCard


ACTIVE_RULE_STATUSES = {"approved", "testing", "validated"}


def select_active_rule_cards(
    rules: list[RuleCard],
    *,
    allow_candidate_ids: list[str] | None = None,
) -> list[RuleCard]:
    allowed_candidates = set(allow_candidate_ids or [])
    return [
        rule
        for rule in rules
        if rule.status in ACTIVE_RULE_STATUSES or (rule.status == "candidate" and rule.id in allowed_candidates)
    ]
