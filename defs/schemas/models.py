"""Pydantic schemas for ticket triage pipeline."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Ticket(BaseModel):
    """Input ticket schema."""

    id: str
    subject: str
    body: str
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    created_at: Optional[str] = None
    source: Optional[str] = None  # e.g., "zendesk", "intercom", "jira"


class TriageResult(BaseModel):
    """
    Structured output from LLM triage classification.

    This schema defines what we expect the model to return when
    analyzing a support ticket.
    """

    category: Literal["bug", "how_to", "billing", "access", "feature_request", "other"] = Field(
        description="Primary category of the ticket"
    )
    priority: Literal["p0", "p1", "p2", "p3"] = Field(
        description="Priority level: p0=critical/outage, p1=high, p2=medium, p3=low"
    )
    sentiment: Literal["calm", "frustrated", "angry"] = Field(
        description="Customer sentiment based on tone and language"
    )
    needs_human: bool = Field(
        description="True if unsafe/uncertain or requires human judgement"
    )
    summary: str = Field(
        description="One-sentence summary of the ticket"
    )
    customer_impact: str = Field(
        description="Brief description of how this issue affects the customer"
    )
    recommended_queue: Literal["support", "engineering", "sales", "security"] = Field(
        description="Which team should handle this ticket"
    )
    suggested_reply: str = Field(
        description="Draft reply to send to the customer (be helpful and empathetic)"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Model's confidence in this classification (0.0 to 1.0)",
    )
    pii_detected: bool = Field(
        default=False,
        description="True if PII (passwords, SSN, credit cards) detected in ticket",
    )
    escalation_reason: Optional[str] = Field(
        default=None,
        description="If needs_human=True, explain why escalation is needed",
    )


class TriageResultWithMetadata(BaseModel):
    """Triage result with LLM metadata attached."""

    ticket_id: str
    triage: TriageResult
    llm_meta: dict  # Contains: model, latency_ms, tokens, etc.


class EvalResult(BaseModel):
    """Quality evaluation result for a triage."""

    ticket_id: str
    passed: bool
    failures: list[str] = Field(
        default_factory=list,
        description="List of failure reasons if check failed",
    )
    confidence: float
    needs_human: bool
    pii_detected: bool


__all__ = [
    "Ticket",
    "TriageResult",
    "TriageResultWithMetadata",
    "EvalResult",
]
