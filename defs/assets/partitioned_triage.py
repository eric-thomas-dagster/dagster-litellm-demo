"""Example: Partitioned ticket triage with production patterns.

This demonstrates:
1. Daily partitioned assets (process tickets by day)
2. Router with multi-provider fallbacks (handle outages)
3. Model escalation on low confidence
4. Actionable outputs (Jira, Slack, assignment)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from dagster import (
    AssetExecutionContext,
    DailyPartitionsDefinition,
    MetadataValue,
    asset,
)

from defs.resources import LiteLLMResource
from defs.schemas import EvalResult, Ticket, TriageResult, TriageResultWithMetadata

# Daily partitions for production use
# Process tickets day-by-day for better performance and backfills
# Start date matches historical data generation (120 days back from today)
daily_partitions = DailyPartitionsDefinition(start_date="2025-09-15")


@asset(
    description="Load tickets partitioned by day (for production scale)",
    compute_kind="python",
    partitions_def=daily_partitions,
    group_name="partitioned_triage",
)
def tickets_partitioned(context: AssetExecutionContext) -> list[dict[str, Any]]:
    """
    Load tickets for a specific day.

    Uses tickets_large.json (large dataset) which can handle hundreds or thousands
    of tickets efficiently since partitioned assets process one day at a time.

    In production:
    - Query Zendesk/Jira API with date filter
    - Read from warehouse partition (e.g., S3://tickets/2025-01-12/)
    - Process millions of tickets day-by-day
    - Backfill historical dates as needed
    """
    partition_date = context.partition_key  # e.g., "2025-01-12"
    context.log.info(f"Loading tickets for {partition_date}")

    # Demo: Load sample data and filter by date (large dataset for partitioned assets)
    sample_file = Path(__file__).parent.parent.parent / "sample_data" / "tickets_large.json"

    if sample_file.exists():
        with open(sample_file) as f:
            all_tickets = json.load(f)

        # Filter tickets for this partition date
        # In production, you'd query the data source directly with date filter
        filtered_tickets = [
            t
            for t in all_tickets
            if t.get("created_at", "").startswith(partition_date)
        ]
    else:
        # Demo data for this partition
        filtered_tickets = [
            {
                "id": f"T-{partition_date}-001",
                "subject": "Login issue",
                "body": f"Can't login on {partition_date}",
                "customer_name": "Demo Customer",
                "customer_email": "demo@example.com",
                "created_at": f"{partition_date}T10:00:00Z",
                "source": "zendesk",
            }
        ]

    context.add_output_metadata(
        {
            "partition_date": partition_date,
            "num_tickets": len(filtered_tickets),
            "sample": MetadataValue.json(filtered_tickets[0] if filtered_tickets else {}),
        }
    )

    return filtered_tickets


@asset(
    description="Triage with multi-provider fallbacks and escalation",
    compute_kind="llm",
    partitions_def=daily_partitions,
    group_name="partitioned_triage",
)
def triage_with_fallbacks(
    context: AssetExecutionContext,
    litellm: LiteLLMResource,
    tickets_partitioned: list[dict[str, Any]],
) -> list[TriageResultWithMetadata]:
    """
    Triage tickets with production resilience patterns:

    1. **Multi-provider fallbacks**: If OpenAI is down, automatically
       switches to Anthropic/Azure/etc. Configure with:
       ```python
       LiteLLMResource(
           enable_router=True,
           router_model_list=[
               {"model_name": "gpt-4o-mini", "litellm_params": {"model": "gpt-4o-mini"}},
               {"model_name": "claude-haiku", "litellm_params": {"model": "claude-3-5-haiku-20241022"}},
               {"model_name": "azure-gpt4o", "litellm_params": {"model": "azure/gpt-4o-mini"}},
           ],
           router_fallback_models=["claude-haiku", "azure-gpt4o"],
       )
       ```

    2. **Model escalation on low confidence**: Tries cheap model first,
       automatically escalates to better model if validation fails:
       ```python
       LiteLLMResource(
           default_model="gpt-4o-mini",
           escalate_models=["gpt-4o", "claude-3-5-sonnet-20241022"],
       )
       ```

    3. **Automatic retries**: Exponential backoff on transient failures
    """
    client = litellm.get_client()
    results: list[TriageResultWithMetadata] = []

    context.log.info(
        f"Triaging {len(tickets_partitioned)} tickets for partition {context.partition_key}"
    )

    # Early return if no tickets - don't waste API calls!
    if not tickets_partitioned:
        context.log.info(f"No tickets for partition {context.partition_key}, skipping API calls")
        context.add_output_metadata(
            {
                "partition": context.partition_key,
                "num_tickets": 0,
                "total_tokens": 0,
                "avg_confidence": "N/A",
                "low_confidence_count": 0,
                "escalation_rate": "N/A",
            }
        )
        return results

    # Show current configuration
    if client.cfg.escalate_models:
        context.log.info(
            f"Model escalation enabled: {client.cfg.default_model} → {client.cfg.escalate_models}"
        )

    for raw_ticket in tickets_partitioned:
        # Clean ticket data
        ticket = Ticket(
            id=raw_ticket["id"],
            subject=raw_ticket.get("subject", "").strip(),
            body=raw_ticket.get("body", "").strip(),
            customer_name=raw_ticket.get("customer_name"),
            customer_email=raw_ticket.get("customer_email"),
            created_at=raw_ticket.get("created_at"),
            source=raw_ticket.get("source"),
        )

        context.log.info(f"Processing ticket {ticket.id}")

        # Triage with LiteLLM (handles fallbacks, retries, escalation automatically)
        messages = [
            {
                "role": "user",
                "content": (
                    "You are a support triage AI. Analyze this ticket and classify it.\n\n"
                    f"Ticket ID: {ticket.id}\n"
                    f"Subject: {ticket.subject}\n"
                    f"Body:\n{ticket.body}\n\n"
                    "Classify category, priority, sentiment. Draft a helpful reply.\n"
                    "If uncertain or unsafe to auto-respond, set needs_human=true."
                ),
            }
        ]

        # This call automatically handles:
        # - Provider fallbacks (if router enabled)
        # - Model escalation (if escalate_models configured)
        # - Retries with backoff
        # - Validation against TriageResult schema
        triage, meta = client.chat_pydantic(
            messages=messages,
            out_model=TriageResult,
            tags={
                "asset": "triage_with_fallbacks",
                "partition": context.partition_key,
                "ticket_id": ticket.id,
            },
        )

        # Check if model was escalated due to low confidence
        model_used = meta.get("model")
        if model_used and model_used != client.cfg.default_model:
            context.log.info(
                f"Ticket {ticket.id} escalated from {client.cfg.default_model} → {model_used}"
            )

        result = TriageResultWithMetadata(
            ticket_id=ticket.id,
            triage=triage,
            llm_meta=meta,
        )
        results.append(result)

        context.log.info(
            f"Ticket {ticket.id}: {triage.category} / {triage.priority} "
            f"(confidence: {triage.confidence:.2f}, needs_human: {triage.needs_human})"
        )

    # Aggregate metrics
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
    p99_latency = latencies_sorted[int(len(latencies_sorted) * 0.99)] if latencies_sorted else 0

    # Throughput metrics
    avg_tokens_per_sec = sum(r.llm_meta.get("tokens_per_second", 0) for r in results) / len(results) if results else 0

    # Quality metrics
    avg_confidence = sum(r.triage.confidence for r in results) / len(results) if results else 0
    confidence_scores = [r.triage.confidence for r in results]
    low_confidence_count = sum(1 for c in confidence_scores if c < 0.7)
    high_confidence_count = sum(1 for c in confidence_scores if c >= 0.85)

    # Distribution metrics
    categories = Counter(r.triage.category for r in results)
    priorities = Counter(r.triage.priority for r in results)
    sentiments = Counter(r.triage.sentiment for r in results)
    queues = Counter(r.triage.recommended_queue for r in results)

    # Model usage
    models_used = Counter(r.llm_meta.get("model") for r in results)

    # Cache metrics
    cache_hits = sum(1 for r in results if r.llm_meta.get("cache_hit", False))
    cache_hit_rate = cache_hits / len(results) if results else 0

    # Business metrics
    needs_human_count = sum(1 for r in results if r.triage.needs_human)
    pii_count = sum(1 for r in results if r.triage.pii_detected)
    high_priority_count = sum(1 for r in results if r.triage.priority in ["p0", "p1"])

    context.add_output_metadata(
        {
            # Basic metrics
            "partition": context.partition_key,
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
            "p99_latency_ms": p99_latency,

            # Quality metrics
            "avg_confidence": MetadataValue.float(round(avg_confidence, 3)),
            "low_confidence_count": low_confidence_count,
            "high_confidence_count": high_confidence_count,
            "escalation_rate": f"{low_confidence_count / len(results) * 100:.1f}%" if results else "0%",

            # Distribution metrics
            "category_distribution": MetadataValue.json(dict(categories)),
            "priority_distribution": MetadataValue.json(dict(priorities)),
            "sentiment_distribution": MetadataValue.json(dict(sentiments)),
            "queue_distribution": MetadataValue.json(dict(queues)),

            # Model usage
            "models_used": MetadataValue.json(dict(models_used)),

            # Cache metrics
            "cache_hits": cache_hits,
            "cache_hit_rate": f"{cache_hit_rate * 100:.1f}%",

            # Business metrics
            "needs_human_count": needs_human_count,
            "pii_detected_count": pii_count,
            "high_priority_count": high_priority_count,
        }
    )

    return results


@asset(
    description="Take production actions: Jira, Slack, auto-reply, assignment",
    compute_kind="python",
    partitions_def=daily_partitions,
    group_name="partitioned_triage",
)
def actions_production(
    context: AssetExecutionContext,
    triage_with_fallbacks: list[TriageResultWithMetadata],
) -> dict[str, Any]:
    """
    Execute production actions on triage results.

    Actions based on triage results:
    - **P0/P1 + Engineering**: Create Jira ticket, notify Slack #eng-oncall
    - **High confidence (>0.85) + Calm sentiment**: Auto-reply to customer
    - **Low confidence (<0.7)**: Escalate to human agent
    - **PII detected**: Route to security team
    - **needs_human=True**: Assign to appropriate queue

    To implement for real:
    1. Install: `pip install jira slack-sdk`
    2. Add resources in definitions.py:
       ```python
       from jira import JIRA
       from slack_sdk import WebClient

       "jira": JIRA(server="https://yourcompany.atlassian.net", token=EnvVar("JIRA_TOKEN")),
       "slack": WebClient(token=EnvVar("SLACK_BOT_TOKEN")),
       ```
    3. Use in this asset:
       ```python
       def actions_production(context, triage_with_fallbacks, jira: JIRA, slack: WebClient):
           # Create Jira ticket
           issue = jira.create_issue(
               project="SUP",
               summary=f"[{triage.priority.upper()}] {ticket.subject}",
               description=triage.customer_impact,
               issuetype={"name": "Bug" if triage.category == "bug" else "Task"},
               priority={"name": "Highest" if triage.priority == "p0" else "High"},
           )

           # Send Slack notification
           slack.chat_postMessage(
               channel="#eng-oncall",
               text=f":rotating_light: P0 ticket created: {issue.key}",
               blocks=[...],
           )
       ```
    """
    actions = {
        "jira_tickets": [],
        "slack_notifications": [],
        "auto_replies": [],
        "human_assignments": [],
        "security_escalations": [],
        "manual_review_queue": [],  # NEW: Track tickets needing manual triage
    }

    # Early return if no triage results
    if not triage_with_fallbacks:
        context.log.info(f"No triage results for partition {context.partition_key}, skipping actions")
        context.add_output_metadata(
            {
                "partition": context.partition_key,
                "total_actions": 0,
                "jira_created": 0,
                "slack_sent": 0,
                "auto_replied": 0,
                "human_assigned": 0,
                "security_escalated": 0,
                "manual_review": 0,
            }
        )
        return actions

    for result in triage_with_fallbacks:
        triage = result.triage
        ticket_id = result.ticket_id

        # Check if ticket failed quality gates (even after escalation)
        # Must match the thresholds in triage_eval asset
        failed_quality_gate = (
            triage.confidence < 0.65  # Very low confidence (stricter than 0.75 escalation threshold)
            or triage.needs_human  # Model explicitly marked as needing human
            or triage.pii_detected  # PII detected - needs security review
            or (not triage.suggested_reply.strip() or len(triage.suggested_reply) < 40)  # Poor reply quality
        )

        # Handle tickets that FAILED quality gates - route to manual review
        if failed_quality_gate:
            reasons = []
            if triage.confidence < 0.65:
                reasons.append(f"Very low confidence: {triage.confidence:.2f}")
            if not triage.suggested_reply.strip() or len(triage.suggested_reply) < 40:
                reasons.append("Inadequate suggested reply")
            if triage.needs_human:
                escalation_reason = triage.escalation_reason or "Model marked as needs_human"
                reasons.append(f"Needs human: {escalation_reason}")
            if triage.pii_detected:
                reasons.append("PII detected")

            failure_summary = ", ".join(reasons)
            manual_review = {
                "ticket_id": ticket_id,
                "reasons": reasons,
                "confidence": triage.confidence,
                "category": triage.category,
                "priority": triage.priority,
            }
            actions["manual_review_queue"].append(manual_review)

            context.log.warning(
                f"[MANUAL REVIEW] Ticket {ticket_id} FAILED quality gate - routing to manual triage"
            )
            context.log.info(f"  Failure reasons: {failure_summary}")
            context.log.info(f"  Confidence: {triage.confidence:.2f}")
            context.log.info(
                f"  [JIRA] Create ticket in 'Manual Triage' queue for {ticket_id}"
            )
            context.log.info(
                f"  [SLACK] Notify #triage-review: '{ticket_id}' needs manual triage - {failure_summary}"
            )
            continue  # Skip normal action processing

        # Action 1: Create Jira for engineering P0/P1
        if triage.recommended_queue == "engineering" and triage.priority in ["p0", "p1"]:
            jira_ticket = {
                "ticket_id": ticket_id,
                "jira_key": f"ENG-{hash(ticket_id) % 10000}",  # Demo stub
                "priority": triage.priority.upper(),
                "summary": f"[{triage.priority.upper()}] Support escalation",
                "assignee": "oncall-engineer",
            }
            actions["jira_tickets"].append(jira_ticket)
            context.log.info(
                f"[JIRA] Created {jira_ticket['jira_key']} for {ticket_id} "
                f"(priority: {triage.priority}, category: {triage.category})"
            )

        # Action 2: Slack notifications for urgent tickets
        if triage.priority in ["p0", "p1"]:
            slack_msg = {
                "ticket_id": ticket_id,
                "channel": f"#{triage.recommended_queue}-oncall",
                "priority": triage.priority,
                "summary": triage.summary,
            }
            actions["slack_notifications"].append(slack_msg)
            context.log.info(
                f"[SLACK] Notified {slack_msg['channel']} about {ticket_id} "
                f"({triage.priority} {triage.category})"
            )

        # Action 3: Auto-reply for high confidence, non-sensitive tickets
        if (
            triage.confidence > 0.85
            and not triage.needs_human
            and not triage.pii_detected
            and triage.sentiment == "calm"
        ):
            auto_reply = {
                "ticket_id": ticket_id,
                "reply_text": triage.suggested_reply,
                "confidence": triage.confidence,
            }
            actions["auto_replies"].append(auto_reply)
            context.log.info(
                f"[AUTO-REPLY] Sent response to {ticket_id} (confidence: {triage.confidence:.2f})"
            )

        # Action 4: Security escalation for PII
        if triage.pii_detected:
            security_escalation = {
                "ticket_id": ticket_id,
                "reason": "PII detected in ticket body",
                "assigned_to": "security-team",
            }
            actions["security_escalations"].append(security_escalation)
            context.log.warning(f"[SECURITY] Escalated {ticket_id} due to PII detection")

        # Action 5: Human assignment for everything else
        if triage.needs_human or triage.confidence < 0.7:
            assignment = {
                "ticket_id": ticket_id,
                "queue": triage.recommended_queue,
                "reason": triage.escalation_reason or "Low confidence or needs human review",
                "priority": triage.priority,
            }
            actions["human_assignments"].append(assignment)
            context.log.info(
                f"[ASSIGN] Ticket {ticket_id} → {triage.recommended_queue} queue "
                f"(reason: {assignment['reason']})"
            )

    # Summary metrics
    total_actions = sum(len(v) for v in actions.values())

    context.add_output_metadata(
        {
            "partition": context.partition_key,
            "total_actions": total_actions,
            "jira_created": len(actions["jira_tickets"]),
            "slack_sent": len(actions["slack_notifications"]),
            "auto_replied": len(actions["auto_replies"]),
            "human_assigned": len(actions["human_assignments"]),
            "security_escalated": len(actions["security_escalations"]),
            "manual_review": len(actions["manual_review_queue"]),  # NEW: Track manual review tickets
            "sample_jira": MetadataValue.json(
                actions["jira_tickets"][0] if actions["jira_tickets"] else {}
            ),
            "manual_review_tickets": MetadataValue.json(
                actions["manual_review_queue"] if actions["manual_review_queue"] else []
            ),
        }
    )

    return actions


__all__ = ["tickets_partitioned", "triage_with_fallbacks", "actions_production"]
