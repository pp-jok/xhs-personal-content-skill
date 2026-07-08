from __future__ import annotations

from app.models.core import BenchmarkAnalysis, RuleCard, RuleEvidence


def build_rule_and_evidence_from_analysis(
    analysis: BenchmarkAnalysis,
    candidate_id: str,
) -> tuple[RuleCard, RuleEvidence]:
    if candidate_id not in analysis.candidate_rule_ids:
        raise ValueError(f"Candidate rule not found in analysis: {candidate_id}")

    title = str(analysis.observable_facts.get("title") or "").strip()
    body = str(analysis.observable_facts.get("body") or "").strip()
    observable_fact = title or body
    if not observable_fact:
        raise ValueError("Analysis does not contain observable facts for rule evidence")

    inference = str(analysis.title_analysis.get("inference") or analysis.structure_analysis.get("inference") or "").strip()
    if not inference:
        inference = "基于可见内容形成的候选规则，需要人工确认。"

    rule_id = f"rule-from-{candidate_id}"
    evidence_id = f"evidence-from-{candidate_id}"
    rule = RuleCard(
        id=rule_id,
        name=f"候选规则：{candidate_id}",
        type="title",
        source_ids=[analysis.benchmark_post_id or analysis.capture_id],
        applicable_scenarios=[analysis.analysis_template],
        rule_summary=inference,
        examples=[observable_fact],
        risks=list(analysis.non_transferable_elements),
        adaptation_notes="候选规则，需要运营人员确认后再稳定使用。",
        tags=["candidate"],
        status="candidate",
        strength="weak",
        applicable_content_types=[content_type]
        if (content_type := str(analysis.observable_facts.get("content_type") or "").strip())
        else [],
        source_type="benchmark_analysis",
        source_note=analysis.id,
        created_from="create-rule-from-analysis",
        confidence=analysis.confidence,
        created_by="codex",
    )
    evidence = RuleEvidence(
        id=evidence_id,
        rule_id=rule.id,
        source_type="benchmark_analysis",
        source_id=analysis.id,
        source_fragment="title" if title else "body",
        evidence_type="content_structure",
        observable_fact=observable_fact,
        inference=inference,
        confidence=analysis.confidence,
        source_note=analysis.id,
        created_from="create-rule-from-analysis",
    )
    return rule, evidence


def check_rule_relations(rule_cards: list[RuleCard]) -> dict[str, list[list[str]]]:
    duplicates: list[list[str]] = []
    context_differences: list[list[str]] = []
    conflicts: list[list[str]] = []

    for index, first in enumerate(rule_cards):
        for second in rule_cards[index + 1 :]:
            pair = [first.id, second.id]
            same_summary = normalize_text(first.rule_summary) == normalize_text(second.rule_summary)
            same_type = first.type == second.type
            same_context = bool(set(first.applicable_scenarios) & set(second.applicable_scenarios))

            if same_summary:
                duplicates.append(pair)
                if set(first.applicable_scenarios) != set(second.applicable_scenarios):
                    context_differences.append(pair)
                continue

            if same_type and same_context:
                conflicts.append(pair)

    return {
        "duplicates": duplicates,
        "context_differences": context_differences,
        "conflicts": conflicts,
    }


def normalize_text(value: str) -> str:
    return "".join(value.split()).lower()
