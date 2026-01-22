"""Assets for LLM-powered ticket triage."""

from dagster import AssetExecutionContext, MetadataValue, asset

from defs.resources import LiteLLMResource
from defs.schemas import EvalResult, Ticket, TriageResult, TriageResultWithMetadata


@asset(
    description="Use LiteLLM to classify and triage support tickets",
    compute_kind="llm",
    group_name="ticket_triage",
)
def triage_llm(
    context: AssetExecutionContext,
    litellm: LiteLLMResource,
    tickets_clean: list[Ticket],
) -> list[TriageResultWithMetadata]:
    """
    Classify each ticket using LiteLLM.

    This asset demonstrates:
    - Structured output with Pydantic models
    - Rich metadata capture (tokens, latency, cost)
    - Model escalation on validation failures
    - Per-ticket tagging for observability
    """
    client = litellm.get_client()
    results: list[TriageResultWithMetadata] = []

    context.log.info(f"Triaging {len(tickets_clean)} tickets with model {client.cfg.default_model}")

    for ticket in tickets_clean:
        context.log.info(f"Processing ticket {ticket.id}: {ticket.subject}")

        messages = [
            {
                "role": "user",
                "content": (
                    "You are a support triage AI. Analyze this ticket and classify it.\n\n"
                    f"Ticket ID: {ticket.id}\n"
                    f"Subject: {ticket.subject}\n"
                    f"Body:\n{ticket.body}\n\n"
                    "Classify the ticket category, priority, sentiment, and draft a helpful reply."
                ),
            }
        ]

        triage, meta = client.chat_pydantic(
            messages=messages,
            out_model=TriageResult,
            tags={"asset": "triage_llm", "ticket_id": ticket.id},
        )

        # Model escalation: retry with better model if confidence is low
        if triage.confidence < 0.75 and client.cfg.escalate_models:
            context.log.warning(
                f"Ticket {ticket.id} has low confidence ({triage.confidence:.2f}), "
                f"retrying with escalated model: {client.cfg.escalate_models[0]}"
            )

            triage_retry, meta_retry = client.chat_pydantic(
                messages=messages,
                out_model=TriageResult,
                model=client.cfg.escalate_models[0],
                tags={"asset": "triage_llm", "ticket_id": ticket.id, "escalated": True},
            )

            # Use the retry result if it has better confidence
            if triage_retry.confidence > triage.confidence:
                context.log.info(
                    f"Escalated model improved confidence: {triage.confidence:.2f} → {triage_retry.confidence:.2f}"
                )
                triage, meta = triage_retry, meta_retry
            else:
                context.log.warning(
                    f"Escalated model did not improve confidence ({triage_retry.confidence:.2f}), using original result"
                )

        result = TriageResultWithMetadata(
            ticket_id=ticket.id,
            triage=triage,
            llm_meta=meta,
        )
        results.append(result)

        context.log.info(
            f"Ticket {ticket.id} classified as {triage.category} "
            f"(priority: {triage.priority}, confidence: {triage.confidence:.2f})"
        )

    # Aggregate metadata for the entire batch
    from collections import Counter

    total_tokens = sum(r.llm_meta.get("total_tokens", 0) for r in results)
    prompt_tokens = sum(r.llm_meta.get("prompt_tokens", 0) for r in results)
    completion_tokens = sum(r.llm_meta.get("completion_tokens", 0) for r in results)
    total_cost = sum(r.llm_meta.get("cost_usd", 0) for r in results)

    # Latency metrics
    latencies = [r.llm_meta.get("latency_ms", 0) for r in results]
    latencies_sorted = sorted(latencies)
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    min_latency = min(latencies) if latencies else 0
    max_latency = max(latencies) if latencies else 0
    p95_latency = latencies_sorted[int(len(latencies_sorted) * 0.95)] if latencies_sorted else 0

    # Throughput metrics
    avg_tokens_per_sec = sum(r.llm_meta.get("tokens_per_second", 0) for r in results) / len(results) if results else 0

    # Quality metrics
    avg_confidence = sum(r.triage.confidence for r in results) / len(results) if results else 0
    low_confidence_count = sum(1 for r in results if r.triage.confidence < 0.7)
    high_confidence_count = sum(1 for r in results if r.triage.confidence >= 0.85)

    # Distribution metrics
    categories = Counter(r.triage.category for r in results)
    priorities = Counter(r.triage.priority for r in results)
    sentiments = Counter(r.triage.sentiment for r in results)

    # Model usage
    models_used = Counter(r.llm_meta.get("model") for r in results)

    # Business metrics
    needs_human_count = sum(1 for r in results if r.triage.needs_human)
    pii_count = sum(1 for r in results if r.triage.pii_detected)
    high_priority_count = sum(1 for r in results if r.triage.priority in ["p0", "p1"])

    context.add_output_metadata(
        {
            # Basic metrics
            "num_tickets": len(results),

            # Cost metrics
            "total_cost_usd": MetadataValue.float(round(total_cost, 4)),
            "cost_per_ticket_usd": MetadataValue.float(round(total_cost / len(results), 4) if results else 0),

            # Token metrics
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "avg_tokens_per_ticket": int(total_tokens / len(results)) if results else 0,
            "tokens_per_second": MetadataValue.float(round(avg_tokens_per_sec, 2)),

            # Latency metrics
            "avg_latency_ms": int(avg_latency),
            "min_latency_ms": min_latency,
            "max_latency_ms": max_latency,
            "p95_latency_ms": p95_latency,

            # Quality metrics
            "avg_confidence": MetadataValue.float(round(avg_confidence, 3)),
            "low_confidence_count": low_confidence_count,
            "high_confidence_count": high_confidence_count,

            # Distribution metrics
            "category_distribution": MetadataValue.json(dict(categories)),
            "priority_distribution": MetadataValue.json(dict(priorities)),
            "sentiment_distribution": MetadataValue.json(dict(sentiments)),

            # Model usage
            "models_used": MetadataValue.json(dict(models_used)),

            # Business metrics
            "needs_human_count": needs_human_count,
            "pii_detected_count": pii_count,
            "high_priority_count": high_priority_count,

            # Sample
            "sample_triage": MetadataValue.json(results[0].triage.model_dump() if results else {}),
        }
    )

    return results


@asset(
    description="Evaluate triage quality and apply business rules",
    compute_kind="python",
    group_name="ticket_triage",
)
def triage_eval(
    context: AssetExecutionContext,
    triage_llm: list[TriageResultWithMetadata],
) -> list[EvalResult]:
    """
    Quality gate: evaluate each triage result.

    Reject tickets that:
    - Have low confidence (< 0.65)
    - Need human review
    - Detected PII
    - Have insufficient suggested_reply
    """
    eval_results: list[EvalResult] = []

    for result in triage_llm:
        triage = result.triage
        failures = []

        # Check confidence threshold
        if triage.confidence < 0.65:
            failures.append(f"Low confidence: {triage.confidence:.2f}")

        # Check if human review needed
        if triage.needs_human:
            reason = triage.escalation_reason or "Model marked as needs_human"
            failures.append(f"Human review required: {reason}")

        # Check for PII
        if triage.pii_detected:
            failures.append("PII detected in ticket")

        # Check suggested reply quality
        if not triage.suggested_reply.strip() or len(triage.suggested_reply) < 40:
            failures.append("Suggested reply too short or empty")

        passed = len(failures) == 0
        eval_result = EvalResult(
            ticket_id=result.ticket_id,
            passed=passed,
            failures=failures,
            confidence=triage.confidence,
            needs_human=triage.needs_human,
            pii_detected=triage.pii_detected,
        )
        eval_results.append(eval_result)

        if not passed:
            context.log.warning(f"Ticket {result.ticket_id} FAILED quality gate: {failures}")
        else:
            context.log.info(f"Ticket {result.ticket_id} PASSED quality gate")

    passed_count = sum(1 for e in eval_results if e.passed)
    failed_count = len(eval_results) - passed_count

    context.add_output_metadata(
        {
            "total_evaluated": len(eval_results),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "pass_rate": f"{passed_count / len(eval_results) * 100:.1f}%" if eval_results else "0%",
            "failed_ticket_ids": [e.ticket_id for e in eval_results if not e.passed][:10],
        }
    )

    return eval_results


@asset(
    description="Take actions on approved tickets (create Jira, notify Slack, etc.)",
    compute_kind="python",
    group_name="ticket_triage",
)
def triage_actions(
    context: AssetExecutionContext,
    triage_llm: list[TriageResultWithMetadata],
    triage_eval: list[EvalResult],
) -> dict[str, int]:
    """
    Execute actions on tickets that passed quality gates.

    This is a demo stub. In production, this would:
    - Create Jira tickets for engineering queue
    - Send Slack notifications for P0/P1
    - Auto-reply to customers (if safe)
    - Assign to human agents
    """
    # Build lookup for eval results
    eval_lookup = {e.ticket_id: e for e in triage_eval}

    actions_taken = {
        "jira_created": 0,
        "slack_notified": 0,
        "auto_replied": 0,
        "assigned_human": 0,
        "manual_review_queue": 0,  # NEW: Track failed quality gate tickets
    }

    for result in triage_llm:
        eval_result = eval_lookup.get(result.ticket_id)
        triage = result.triage

        # Handle tickets that FAILED quality gates
        if not eval_result or not eval_result.passed:
            failure_summary = ", ".join(eval_result.failures if eval_result else ["Unknown"])
            context.log.warning(
                f"[ACTION] Ticket {result.ticket_id} FAILED quality gate - routing to manual review queue"
            )
            context.log.info(f"  Failure reasons: {failure_summary}")
            context.log.info(f"  Confidence: {triage.confidence:.2f}")
            context.log.info(
                f"  [ACTION] Create Jira ticket in 'Manual Triage' queue for {result.ticket_id}"
            )
            context.log.info(
                f"  [ACTION] Send Slack notification to #triage-review: "
                f"'{result.ticket_id}' needs manual triage - {failure_summary}"
            )
            actions_taken["manual_review_queue"] += 1
            actions_taken["jira_created"] += 1
            actions_taken["slack_notified"] += 1
            continue

        # Handle tickets that PASSED quality gates
        # Example action logic (stubbed for demo)
        if triage.recommended_queue == "engineering" and triage.priority in ["p0", "p1"]:
            context.log.info(
                f"[ACTION] Create Jira ticket for {result.ticket_id} "
                f"(priority: {triage.priority}, category: {triage.category})"
            )
            actions_taken["jira_created"] += 1

        if triage.priority in ["p0", "p1"]:
            context.log.info(
                f"[ACTION] Send Slack notification for {result.ticket_id} to #{triage.recommended_queue} channel"
            )
            actions_taken["slack_notified"] += 1

        if triage.confidence > 0.85 and not triage.needs_human and triage.sentiment == "calm":
            context.log.info(f"[ACTION] Send auto-reply to customer for {result.ticket_id}")
            actions_taken["auto_replied"] += 1
        else:
            context.log.info(f"[ACTION] Assign {result.ticket_id} to human agent in {triage.recommended_queue} queue")
            actions_taken["assigned_human"] += 1

    context.add_output_metadata(
        {
            "total_actions": sum(actions_taken.values()),
            **{k: v for k, v in actions_taken.items()},
        }
    )

    return actions_taken
