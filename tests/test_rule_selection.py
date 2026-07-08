import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.models.core import RuleCard  # noqa: E402
from app.rules.selection import select_active_rule_cards  # noqa: E402


class RuleSelectionTests(unittest.TestCase):
    def test_select_active_rule_cards_defaults_to_confirmed_lifecycle_states(self) -> None:
        rules = [
            self._rule("rule-candidate", "candidate"),
            self._rule("rule-approved", "approved"),
            self._rule("rule-testing", "testing"),
            self._rule("rule-validated", "validated"),
            self._rule("rule-rejected", "rejected"),
            self._rule("rule-deprecated", "deprecated"),
        ]

        selected = select_active_rule_cards(rules)

        self.assertEqual([rule.id for rule in selected], ["rule-approved", "rule-testing", "rule-validated"])

    def test_select_active_rule_cards_only_allows_explicit_candidate_ids(self) -> None:
        rules = [
            self._rule("rule-candidate-a", "candidate"),
            self._rule("rule-candidate-b", "candidate"),
            self._rule("rule-approved", "approved"),
        ]

        selected = select_active_rule_cards(rules, allow_candidate_ids=["rule-candidate-b"])

        self.assertEqual([rule.id for rule in selected], ["rule-candidate-b", "rule-approved"])

    def _rule(self, rule_id: str, status: str) -> RuleCard:
        return RuleCard(
            id=rule_id,
            name=rule_id,
            type="title",
            source_ids=["benchmark-post-001"],
            applicable_scenarios=["标题"],
            rule_summary=f"{rule_id} summary",
            examples=["例子"],
            risks=["风险"],
            adaptation_notes="适合账号。",
            status=status,
        )


if __name__ == "__main__":
    unittest.main()
