"""Assets for loading and cleaning ticket data."""

import json
from pathlib import Path
from typing import Any

from dagster import AssetExecutionContext, MetadataValue, asset

from defs.schemas import Ticket


@asset(
    description="Load raw ticket data from sample JSON file",
    compute_kind="python",
    group_name="ticket_triage",
)
def tickets_raw(context: AssetExecutionContext) -> list[dict[str, Any]]:
    """
    Load raw tickets from sample data file.

    Uses tickets_small.json (small dataset) to avoid using too many tokens
    in the non-partitioned pipeline that processes all tickets at once.

    In production, this would:
    - Query Zendesk/Jira/Intercom API
    - Read from a database or data warehouse
    - Be partitioned by date/customer
    """
    # Load from sample data directory (small dataset for non-partitioned assets)
    sample_file = Path(__file__).parent.parent.parent / "sample_data" / "tickets_small.json"

    if not sample_file.exists():
        # Return demo data if file doesn't exist yet
        demo_tickets = [
            {
                "id": "T-001",
                "subject": "Can't login to my account",
                "body": "Hi, I've been trying to login for the past hour but keep getting 'invalid credentials' error. I'm certain my password is correct. This is urgent as I need to submit a report by EOD.",
                "customer_name": "Alice Johnson",
                "customer_email": "alice@example.com",
                "created_at": "2025-01-12T10:00:00Z",
                "source": "zendesk",
            },
            {
                "id": "T-002",
                "subject": "Feature request: Dark mode",
                "body": "Would love to see a dark mode option in the app. My eyes hurt after using it for extended periods.",
                "customer_name": "Bob Smith",
                "customer_email": "bob@example.com",
                "created_at": "2025-01-12T11:30:00Z",
                "source": "intercom",
            },
            {
                "id": "T-003",
                "subject": "URGENT: Production database is down!!!",
                "body": "Our entire production database cluster is unresponsive. All customer requests are failing. This is a P0 incident affecting all users. Need immediate help!",
                "customer_name": "Charlie Davis",
                "customer_email": "charlie@enterprise.com",
                "created_at": "2025-01-12T12:00:00Z",
                "source": "jira",
            },
        ]
        context.log.info("Sample data file not found, using demo tickets")
        context.add_output_metadata(
            {
                "num_tickets": len(demo_tickets),
                "source": "demo_data",
                "sample": MetadataValue.json(demo_tickets[0]),
            }
        )
        return demo_tickets

    with open(sample_file) as f:
        tickets = json.load(f)

    context.add_output_metadata(
        {
            "num_tickets": len(tickets),
            "source": str(sample_file),
            "sample": MetadataValue.json(tickets[0] if tickets else {}),
        }
    )

    return tickets


@asset(
    description="Clean and normalize ticket data",
    compute_kind="python",
    group_name="ticket_triage",
)
def tickets_clean(context: AssetExecutionContext, tickets_raw: list[dict[str, Any]]) -> list[Ticket]:
    """
    Clean and normalize raw ticket data.

    In production, this would:
    - Truncate very long bodies
    - Strip email signatures
    - Normalize field names across sources
    - Filter out spam/test tickets
    """
    cleaned_tickets = []

    for raw in tickets_raw:
        # Basic cleaning: truncate body to 2000 chars, strip whitespace
        body = raw.get("body", "").strip()
        if len(body) > 2000:
            body = body[:2000] + "... [truncated]"

        ticket = Ticket(
            id=raw["id"],
            subject=raw.get("subject", "").strip(),
            body=body,
            customer_name=raw.get("customer_name"),
            customer_email=raw.get("customer_email"),
            created_at=raw.get("created_at"),
            source=raw.get("source"),
        )
        cleaned_tickets.append(ticket)

    context.add_output_metadata(
        {
            "num_tickets": len(cleaned_tickets),
            "avg_body_length": sum(len(t.body) for t in cleaned_tickets) / len(cleaned_tickets)
            if cleaned_tickets
            else 0,
        }
    )

    return cleaned_tickets
