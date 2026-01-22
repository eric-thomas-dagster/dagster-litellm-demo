"""Dagster Definitions for LiteLLM + Dagster Demo: Ticket Triage Pipeline."""

import dagster as dg
from dagster import (
    AssetSelection,
    ScheduleDefinition,
    define_asset_job,
    build_schedule_from_partitioned_job,
)

from defs.assets import checks, enhanced_examples, partitioned_triage, tickets, triage
from defs.resources import LiteLLMResource

# Define resources using Dagster EnvVar
litellm_resource = LiteLLMResource(
    default_model=dg.EnvVar("LITELLM_DEFAULT_MODEL").get_value("gpt-4o-mini"),
    timeout_s=60.0,
    max_retries=3,
    initial_backoff_s=1.0,
    max_backoff_s=10.0,
    # Optional: escalate to better models on validation failures
    # Example: ["gpt-4o-mini", "gpt-4o"] or ["claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"]
    escalate_models=[
        m.strip()
        for m in dg.EnvVar("LITELLM_ESCALATE_MODELS").get_value("").split(",")
        if m.strip()
    ],
    # Optional: if using LiteLLM proxy
    api_base=dg.EnvVar("LITELLM_API_BASE").get_value(None),
    api_key=dg.EnvVar("LITELLM_API_KEY").get_value(None),
)

# Load all assets and checks from modules
all_assets = dg.load_assets_from_modules(
    [tickets, triage, partitioned_triage, enhanced_examples]
)
all_checks = dg.load_asset_checks_from_modules([checks])

# ===== Jobs =====

# Job 1: Standard ticket triage pipeline (all tickets at once)
standard_triage_job = define_asset_job(
    name="standard_triage_pipeline",
    selection=AssetSelection.groups("ticket_triage"),
    description="Run the standard ticket triage pipeline (processes all tickets at once)",
)

# Job 2: Partitioned ticket triage pipeline (daily partitions)
partitioned_triage_job = define_asset_job(
    name="partitioned_triage_pipeline",
    selection=AssetSelection.groups("partitioned_triage"),
    description="Run the partitioned ticket triage pipeline (processes one day at a time)",
    partitions_def=partitioned_triage.daily_partitions,
)

# Job 3: Examples showcase (optional)
examples_job = define_asset_job(
    name="examples_showcase",
    selection=AssetSelection.groups("examples"),
    description="Run all LiteLLM feature examples",
)

# ===== Schedules =====

# Daily schedule for partitioned pipeline
# Runs every day at 9am to process yesterday's tickets
daily_triage_schedule = build_schedule_from_partitioned_job(
    partitioned_triage_job,
    hour_of_day=9,
    minute_of_hour=0,
    name="daily_triage_schedule",
    description="Runs daily at 9am to process yesterday's tickets",
)

# Weekly schedule for full pipeline run (optional)
weekly_full_run_schedule = ScheduleDefinition(
    name="weekly_full_triage",
    job=standard_triage_job,
    cron_schedule="0 10 * * 1",  # Every Monday at 10am
    description="Runs the full triage pipeline weekly on Monday at 10am",
)

# Create the Definitions object
defs = dg.Definitions(
    assets=all_assets,
    asset_checks=all_checks,
    jobs=[
        standard_triage_job,
        partitioned_triage_job,
        examples_job,
    ],
    schedules=[
        daily_triage_schedule,
        weekly_full_run_schedule,
    ],
    resources={
        "litellm": litellm_resource,
    },
)
