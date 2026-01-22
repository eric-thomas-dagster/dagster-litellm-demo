"""Asset checks for quality gates and data validation."""

from dagster import AssetCheckResult, asset_check

from defs.schemas import TriageResultWithMetadata


@asset_check(asset="triage_llm", description="Check that all triages have acceptable confidence scores")
def triage_confidence_check(triage_llm: list[TriageResultWithMetadata]) -> AssetCheckResult:
    """
    Validate that triage confidence scores meet minimum threshold.

    This check fails if more than 20% of tickets have low confidence.
    """
    low_confidence_threshold = 0.65
    max_low_confidence_pct = 0.20

    low_confidence_tickets = [
        result.ticket_id
        for result in triage_llm
        if result.triage.confidence < low_confidence_threshold
    ]

    low_confidence_pct = len(low_confidence_tickets) / len(triage_llm) if triage_llm else 0
    passed = low_confidence_pct <= max_low_confidence_pct

    return AssetCheckResult(
        passed=passed,
        description=f"Low confidence rate: {low_confidence_pct:.1%} (threshold: {max_low_confidence_pct:.1%})",
        metadata={
            "low_confidence_count": len(low_confidence_tickets),
            "total_tickets": len(triage_llm),
            "low_confidence_pct": f"{low_confidence_pct:.1%}",
            "failed_ticket_ids": low_confidence_tickets[:10],
        },
    )


@asset_check(asset="triage_llm", description="Check for PII detection rate")
def triage_pii_check(triage_llm: list[TriageResultWithMetadata]) -> AssetCheckResult:
    """
    Monitor PII detection rate.

    This is an informational check - we want to know if PII is detected
    but don't necessarily fail the pipeline.
    """
    pii_tickets = [result.ticket_id for result in triage_llm if result.triage.pii_detected]

    pii_pct = len(pii_tickets) / len(triage_llm) if triage_llm else 0

    # This check always passes but provides visibility
    return AssetCheckResult(
        passed=True,
        description=f"PII detected in {len(pii_tickets)} tickets ({pii_pct:.1%})",
        metadata={
            "pii_count": len(pii_tickets),
            "total_tickets": len(triage_llm),
            "pii_pct": f"{pii_pct:.1%}",
            "pii_ticket_ids": pii_tickets[:10],
        },
    )


@asset_check(asset="triage_llm", description="Check suggested reply quality")
def triage_reply_quality_check(triage_llm: list[TriageResultWithMetadata]) -> AssetCheckResult:
    """
    Validate that suggested replies are substantive.

    Fails if more than 10% of replies are too short or empty.
    """
    min_reply_length = 40
    max_poor_quality_pct = 0.10

    poor_quality_replies = [
        result.ticket_id
        for result in triage_llm
        if not result.triage.suggested_reply.strip() or len(result.triage.suggested_reply) < min_reply_length
    ]

    poor_quality_pct = len(poor_quality_replies) / len(triage_llm) if triage_llm else 0
    passed = poor_quality_pct <= max_poor_quality_pct

    return AssetCheckResult(
        passed=passed,
        description=f"Poor quality reply rate: {poor_quality_pct:.1%} (threshold: {max_poor_quality_pct:.1%})",
        metadata={
            "poor_quality_count": len(poor_quality_replies),
            "total_tickets": len(triage_llm),
            "poor_quality_pct": f"{poor_quality_pct:.1%}",
            "failed_ticket_ids": poor_quality_replies[:10],
        },
    )


@asset_check(asset="triage_llm", description="Check human escalation rate")
def triage_human_escalation_check(triage_llm: list[TriageResultWithMetadata]) -> AssetCheckResult:
    """
    Monitor how many tickets require human escalation.

    This is informational - high escalation might mean the model needs tuning
    or the prompt needs improvement.
    """
    needs_human = [result.ticket_id for result in triage_llm if result.triage.needs_human]

    escalation_pct = len(needs_human) / len(triage_llm) if triage_llm else 0

    # Informational check - always passes
    return AssetCheckResult(
        passed=True,
        description=f"Human escalation rate: {escalation_pct:.1%}",
        metadata={
            "needs_human_count": len(needs_human),
            "total_tickets": len(triage_llm),
            "escalation_pct": f"{escalation_pct:.1%}",
            "escalated_ticket_ids": needs_human[:10],
        },
    )


@asset_check(asset="triage_llm", description="Check token usage and cost")
def triage_token_usage_check(triage_llm: list[TriageResultWithMetadata]) -> AssetCheckResult:
    """
    Monitor token usage to detect anomalies or excessive costs.

    Fails if average tokens per ticket exceeds 2000 (might indicate runaway prompts).
    """
    max_avg_tokens = 2000

    total_tokens = sum(result.llm_meta.get("total_tokens", 0) for result in triage_llm)
    avg_tokens = total_tokens / len(triage_llm) if triage_llm else 0

    passed = avg_tokens <= max_avg_tokens

    # Calculate rough cost estimate (assuming ~$0.50 per 1M tokens for cheap models)
    estimated_cost_usd = (total_tokens / 1_000_000) * 0.50

    return AssetCheckResult(
        passed=passed,
        description=f"Average tokens per ticket: {avg_tokens:.0f} (threshold: {max_avg_tokens})",
        metadata={
            "total_tokens": total_tokens,
            "avg_tokens": int(avg_tokens),
            "estimated_cost_usd": f"${estimated_cost_usd:.4f}",
            "total_tickets": len(triage_llm),
        },
    )


# Export all checks
all_checks = [
    triage_confidence_check,
    triage_pii_check,
    triage_reply_quality_check,
    triage_human_escalation_check,
    triage_token_usage_check,
]

__all__ = ["all_checks"]
