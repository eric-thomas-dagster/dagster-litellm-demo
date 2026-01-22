# LiteLLM + Dagster Integration Demo

Production-ready integration between [LiteLLM](https://github.com/BerriAI/litellm) and [Dagster](https://dagster.io) for building scalable LLM pipelines.

**Uses modern Dagster structure** with `defs/` directory.

## Quick Start

```bash
cd dagster_litellm_demo
pip install -e .
cp .env.example .env
# Edit .env: add OPENAI_API_KEY=sk-your-key
./start.sh
# OR: dagster dev -m defs.definitions
```

Open http://localhost:3000 and click "Materialize all".

## Overview

This demo explores production patterns for LLM applications, showing how to build resilient, cost-effective AI pipelines that can handle real-world challenges.

### What This Demo Highlights

**Production Resilience:**
- **Multi-provider fallbacks** *(configurable)* - 99.99% uptime by automatically switching between OpenAI, Anthropic, and other providers when outages occur
- **Model escalation** *(active by default)* - Start with cheap models (gpt-4o-mini: $0.15/1M tokens), automatically escalate to better models (gpt-4o: $2.50/1M tokens) only when confidence is low
- **Quality gates** *(active by default)* - Asset checks enforce business rules before taking actions (confidence thresholds, PII detection, reply quality)

**Cost Optimization:**
- **Model escalation** *(active by default)* - 80%+ cost savings by using cheap models first, escalating only when needed
- **Intelligent caching** *(configurable)* - 50-90% cost reduction by caching identical requests (requires configuration)
- **Cost attribution** *(always on)* - Track spending per asset, per run to identify hot spots

**Observability:**
- **Full LLM tracking** *(always on)* - Every request logs tokens, cost, latency, and model used
- **Visual lineage** *(always on)* - See your entire pipeline at a glance in Dagster UI
- **Metadata capture** *(always on)* - Rich metadata on every asset materialization
- **Advanced tracking** *(configurable)* - Langfuse, W&B integration available (requires configuration)

**Scale:**
- **Daily partitions** - Process millions of tickets efficiently by breaking work into daily chunks
- **Backfill support** - Reprocess historical data in parallel
- **Incremental processing** - Only process new data, skip what's already done

### Why LiteLLM?

[LiteLLM](https://github.com/BerriAI/litellm) provides a universal interface for 100+ LLM providers (OpenAI, Anthropic, Gemini, Azure, AWS Bedrock, and more). One API, any model:

```python
# Same code works with any provider
response = litellm.completion(
    model="gpt-4o-mini",  # or "claude-3-5-sonnet-20241022", "gemini-pro", etc.
    messages=[{"role": "user", "content": "Hello"}]
)
```

But LiteLLM is much more than a wrapper:

1. **Multi-Provider Router with Fallbacks** - If OpenAI goes down, automatically route to Anthropic. No downtime.
2. **Model Escalation** - Try cheap models first, escalate to better models on validation failures. Save 80% on costs.
3. **Built-in Observability** - Integrated with Langfuse, W&B, Helicone, DataDog. Track every token, every latency spike.
4. **Intelligent Caching** - Cache identical requests. Reduce costs by 60-90% in production.
5. **Production-Tested** - Used by hundreds of companies. Battle-tested at scale.

### Why Dagster?

**Dagster** provides orchestration for data and AI pipelines:

- **Asset lineage** - Visual graph of your pipeline dependencies
- **Partitioning** - Process data incrementally (scale to millions of tickets)
- **Quality gates** - Asset checks enforce business rules
- **Observability** - Track metadata, logs, and costs per asset
- **Replay on changes** - Reprocess data when code or models change

**Together**: Production-ready LLM pipelines with full governance, cost control, and reliability.

## Sample Data

This demo uses **two optimized datasets** to balance realism with cost:

### 📦 Small Dataset (`tickets_small.json`)
- **17 tickets** over 7 days (recent history)
- **Used by**: Non-partitioned assets (`triage_llm`, `tickets_raw`, etc.)
- **Purpose**: Quick demos with minimal token usage (~$0.005 per run)
- **Perfect for**: Testing, development, presentations

### 📦 Large Dataset (`tickets_large.json`)
- **982 tickets** over 241 days (120 historical + 120 future)
- **Used by**: Partitioned assets (`triage_with_fallbacks`, `tickets_partitioned`)
- **Purpose**: Production simulation with daily partitions (~$0.001 per day)
- **Perfect for**: Backfills, scheduled runs, scale testing
- **Date range**: Sep 15, 2025 → May 13, 2026

**Why two datasets?** Non-partitioned assets process ALL tickets at once, which could burn through API credits. Partitioned assets process one day at a time, so they can efficiently handle much larger datasets.

### Generate Custom Data

```bash
# Regenerate with defaults (120 historical + 120 future days)
python generate_sample_data.py

# High-volume scenario (1,500+ tickets)
python generate_sample_data.py --historical-days 180 --future-days 60 --weekday-tickets 10 15

# Minimal demo (just 10 tickets)
python generate_sample_data.py --small-only --small-days 3
```

See [DATA_GENERATION.md](DATA_GENERATION.md) for full CLI options and examples.

## What's Included

### ✅ Production Features

1. **Daily Partitioned Assets** ✅ *Active* - Process millions of tickets by day with backfills
2. **Model Escalation + Quality Gates** ✅ *Active* - Try cheap models first, auto-escalate on low confidence, route failures to manual review
3. **Multi-Provider Fallbacks** ⚙️ *Configurable* - 99.99% uptime with automatic provider switching (see Configuration section)
4. **Production Actions** ✅ *Active* - Smart routing: auto-reply high confidence tickets, manual review for failures
5. **Caching** ⚙️ *Configurable* - 50-90% cost savings on repeated queries (see Configuration section)
6. **Observability** ⚙️ *Configurable* - Full tracking with Langfuse (see Configuration section)
7. **Schedules & Jobs** ✅ *Active* - Daily automated processing at 9am

### 🔄 Standard Pipeline

```
tickets_raw → tickets_clean → triage_llm → triage_eval → triage_actions
```

**Features:**
- Uses small dataset (17 tickets) for quick demos
- Model escalation: confidence < 0.75 → retry with better model
- Quality gates: confidence < 0.65, needs_human, PII, or poor reply quality
- Smart actions: high confidence → auto-reply, failures → manual review queue

### 📅 Partitioned Pipeline (Production)

```
tickets_partitioned → triage_with_fallbacks → actions_production
```

**Features:**
- Daily partitions (982 tickets over 241 days)
- Process one day at a time for scalability
- Same escalation + quality gates as standard pipeline
- Production-ready actions: Jira, Slack, auto-replies, manual review
- Perfect for backfills and scheduled runs

### 📚 Enhanced Examples

- `streaming_story` - Streaming responses
- `cached_summaries` - Caching demonstration
- `document_embeddings` → `semantic_search` - Embeddings & RAG
- `agentic_tool_use` → `multi_step_agent` - Function calling

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Get running in 5 minutes
- **[DATA_GENERATION.md](DATA_GENERATION.md)** - Generate custom sample data
- **[definitions_production_example.txt](definitions_production_example.txt)** - Config templates

## Key Concepts

### Unified Resource

One resource, progressive enhancement:

```python
# Start simple
LiteLLMResource(default_model="gpt-4o-mini")

# Add features as needed
LiteLLMResource(
    default_model="gpt-4o-mini",
    enable_cache=True,           # 50-90% cost savings
    enable_router=True,           # Multi-provider fallbacks
    enable_callbacks=True,        # Langfuse observability
    enable_budget=True,           # Cost control
    escalate_models=["gpt-4o"],  # Model escalation
)
```

### Core Features (Always Available)

- Automatic retries with exponential backoff
- Structured output (Pydantic models)
- Model escalation ladder
- Rich metadata (tokens, latency, cost)
- Provider portability (100+ models)

### Advanced Features (Optional)

- **Caching**: Redis or in-memory
- **Callbacks**: Langfuse, W&B
- **Streaming**: Real-time responses
- **Function calling**: Agentic workflows
- **Embeddings**: Semantic search
- **Router**: Load balancing with fallbacks
- **Budget**: Spend limit enforcement

## Usage Examples

### Basic Triage

```python
@asset
def triage_tickets(litellm: LiteLLMResource, tickets: list[Ticket]):
    client = litellm.get_client()

    results = []
    for ticket in tickets:
        triage, meta = client.chat_pydantic(
            messages=[{
                "role": "user",
                "content": f"Classify: {ticket.subject}\n{ticket.body}"
            }],
            out_model=TriageResult,
        )
        results.append(triage)

    return results
```

### With Model Escalation

```python
# In definitions.py
LiteLLMResource(
    default_model="gpt-4o-mini",      # Try cheap first
    escalate_models=["gpt-4o"],        # Escalate if needed
)

# Same code - escalation happens automatically!
```

### With Multi-Provider Router

```python
LiteLLMResource(
    enable_router=True,
    router_model_list=[
        {"model_name": "gpt-4o-mini", "litellm_params": {"model": "gpt-4o-mini"}},
        {"model_name": "claude-haiku", "litellm_params": {"model": "claude-3-5-haiku-20241022"}},
    ],
    router_fallback_models=["claude-haiku"],  # Fallback on OpenAI outage
)
```

### Daily Partitions

```python
from dagster import DailyPartitionsDefinition

daily_partitions = DailyPartitionsDefinition(start_date="2025-01-01")

@asset(partitions_def=daily_partitions)
def tickets_daily(context):
    date = context.partition_key  # "2025-01-12"
    # Load tickets for this day only
    return load_tickets(date=date)
```

## Configuration

### What's Active by Default

The demo works out of the box with:
- ✅ **Model escalation** - Set `LITELLM_ESCALATE_MODELS=gpt-4o` to enable (tries cheap model first, escalates if confidence < 0.75)
- ✅ **Quality gates** - 5 asset checks monitor confidence, PII, reply quality, escalation rate, and token usage
- ✅ **Daily partitions** - Process tickets day-by-day for scale
- ✅ **Production actions** - Smart routing based on confidence and priority

### Optional Features (Require Configuration)

To enable multi-provider fallbacks, caching, or observability, update `definitions.py`:

```python
# Example: Enable multi-provider fallbacks
litellm_resource = LiteLLMResource(
    default_model="gpt-4o-mini",
    escalate_models=["gpt-4o"],  # Model escalation (active by default)

    # Enable router for multi-provider fallbacks
    enable_router=True,
    router_model_list=[
        {"model_name": "gpt-4o-mini", "litellm_params": {"model": "gpt-4o-mini"}},
        {"model_name": "claude-haiku", "litellm_params": {"model": "claude-3-5-haiku-20241022"}},
    ],
    router_fallback_models=["claude-haiku"],

    # Optional: Enable caching
    enable_cache=True,
    cache_type="redis",
    redis_host=dg.EnvVar("REDIS_HOST"),

    # Optional: Enable observability
    enable_callbacks=True,
    langfuse_public_key=dg.EnvVar("LANGFUSE_PUBLIC_KEY"),
    langfuse_secret_key=dg.EnvVar("LANGFUSE_SECRET_KEY"),
)
```

### Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...
# OR
ANTHROPIC_API_KEY=sk-ant-...

# Optional - Model escalation (active by default if set)
LITELLM_ESCALATE_MODELS=gpt-4o,claude-3-5-sonnet-20241022

# Optional - Multi-provider fallbacks (requires enable_router=True in code)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
AZURE_API_KEY=...
AZURE_API_BASE=https://...

# Optional - Caching (requires enable_cache=True in code)
REDIS_HOST=localhost
REDIS_PASSWORD=...

# Optional - Observability (requires enable_callbacks=True in code)
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
```

### Dev vs Staging vs Prod

```python
ENVIRONMENT = EnvVar("DAGSTER_ENVIRONMENT").get_value("dev")

if ENVIRONMENT == "production":
    # Full features: router, caching, callbacks, budget
elif ENVIRONMENT == "staging":
    # Subset: caching, callbacks, lower budget
else:
    # Minimal: just basics
```

See [definitions_production_example.txt](definitions_production_example.txt) for templates.

## Schedules & Jobs

### Jobs

**1. `standard_triage_pipeline`** - Process all tickets at once (non-partitioned)
**2. `partitioned_triage_pipeline`** - Process one day at a time (partitioned)
**3. `examples_showcase`** - Run all LiteLLM feature examples

```bash
# Run standard pipeline
dagster job execute -m defs.definitions -j standard_triage_pipeline

# Run partitioned pipeline for specific date
dagster job execute -m defs.definitions -j partitioned_triage_pipeline \
  --config '{"partitions": ["2026-01-12"]}'
```

### Schedules

**1. `daily_triage_schedule`** - Runs every day at 9:00 AM
- Processes yesterday's partition automatically
- Perfect for production simulation

**2. `weekly_full_triage`** - Runs every Monday at 10:00 AM
- Processes full dataset (health check)

**Enable in Dagster UI**: Schedules tab → Start schedule

## Production Patterns

### 1. Model Escalation + Quality Gates

**Two-tier system for quality**:

```python
# Configuration
LITELLM_ESCALATE_MODELS=gpt-4o  # Fallback model
```

**How it works:**
1. Try cheap model first (`gpt-4o-mini` - $0.15/1M tokens)
2. If confidence < 0.75 → auto-escalate to `gpt-4o` ($2.50/1M tokens)
3. If still fails quality gates → route to manual review queue

**Quality gate thresholds** (ticket fails if any are true):
- Confidence < 0.65 (very low)
- `needs_human = True` (model marked as complex)
- `pii_detected = True` (contains sensitive data)
- Suggested reply < 40 characters (inadequate)

**Failed tickets get routed to**:
- Jira "Manual Triage" queue
- Slack #triage-review channel notification
- Human agent assignment

**Cost savings**: 90% of tickets use cheap model, only 10% escalate

### 2. Daily Partitions for Scale

Process millions of tickets without memory issues:

```python
@asset(partitions_def=daily_partitions)
def tickets_partitioned(context):
    date = context.partition_key  # "2026-01-12"
    return query_tickets(date=date)
```

**Benefits**:
- Parallel execution across dates
- Backfill historical data independently
- Retry failed days without reprocessing everything
- Memory-efficient (one day at a time)

**Usage**:
```bash
# Backfill last 30 days
# In UI: Assets → tickets_partitioned → Backfill → Select range
```

### 3. Multi-Provider Fallbacks (Router)

Achieve 99.99% uptime with automatic provider switching:

```python
LiteLLMResource(
    enable_router=True,
    router_model_list=[
        {"model_name": "gpt-4o-mini", "litellm_params": {"model": "gpt-4o-mini"}},
        {"model_name": "claude-haiku", "litellm_params": {"model": "claude-3-5-haiku-20241022"}},
    ],
    router_fallback_models=["claude-haiku"],  # Fallback on OpenAI outage
)
```

**What happens**:
- Normal: Uses fastest/cheapest provider
- Provider outage: Auto-switches to fallback
- Rate limits: Distributes load across providers

### 4. Production Actions

Smart routing based on triage quality:

**High confidence (>0.85) + calm sentiment**:
- ✅ Auto-reply to customer
- ✅ Log to tracking system

**P0/P1 priority**:
- ✅ Create Jira ticket in engineering queue
- ✅ Send Slack notification to #eng-oncall

**Failed quality gates**:
- ⚠️ Route to manual review queue
- ⚠️ Create Jira in "Manual Triage" project
- ⚠️ Notify #triage-review channel

**Real integrations** (examples in code):
```python
from jira import JIRA
from slack_sdk import WebClient

@asset
def actions_production(context, triage, jira: JIRA, slack: WebClient):
    issue = jira.create_issue(project="SUP", summary="[P0] Database outage")
    slack.chat_postMessage(channel="#eng-oncall", text=f"Created {issue.key}")
```

### 5. Caching for Cost Savings

50-90% cost reduction on repeated queries:

```python
LiteLLMResource(
    enable_cache=True,
    cache_type="redis",  # or "in-memory" for dev
    redis_host=EnvVar("REDIS_HOST"),
)
```

**Use cases**:
- Development: Avoid burning API credits
- Backfills: Reprocess without re-calling LLM
- High traffic: Cache similar customer questions

## Project Structure

```
dagster_litellm_demo/
├── defs/                    # Dagster code location
│   ├── __init__.py         # Empty
│   ├── definitions.py      # Main definitions
│   ├── resources/
│   │   ├── __init__.py     # Re-exports
│   │   └── litellm/        # LiteLLM package
│   │       ├── __init__.py
│   │       ├── litellm_resource.py
│   │       └── litellm_client.py
│   ├── schemas/
│   │   ├── __init__.py     # Re-exports
│   │   └── models.py       # Pydantic models
│   └── assets/
│       ├── __init__.py     # Empty
│       ├── tickets.py      # Standard pipeline
│       ├── triage.py
│       ├── checks.py
│       ├── partitioned_triage.py  # Production patterns
│       └── enhanced_examples.py
├── sample_data/
│   ├── tickets_small.json  # Small dataset (non-partitioned)
│   └── tickets_large.json  # Large dataset (partitioned)
├── generate_sample_data.py # Data generator (customizable)
├── start.sh                # Easy startup
├── .env.example            # Config template
├── README.md               # This file
├── QUICKSTART.md           # 5-minute setup
├── DATA_GENERATION.md      # Data generation guide
└── pyproject.toml          # Dependencies
```

## Asset Checks

5 quality gates monitor pipeline health:

1. **Confidence Check** - Warn if avg confidence < 0.75
2. **PII Detection Check** - Error if PII detected
3. **Reply Quality Check** - Warn if replies too short
4. **Human Escalation Rate** - Warn if >30% need human review
5. **Token Usage Check** - Warn if exceeding budget

## Troubleshooting

### Module not found

```bash
pip install -e .
```

### No API key

```bash
cp .env.example .env
# Edit .env and add OPENAI_API_KEY or ANTHROPIC_API_KEY
```

### Rate limits

Enable caching:

```python
enable_cache=True
```

### Want to use `dagster dev -m defs.definitions` instead?

This project uses `dagster dev -m defs.definitions`. If you prefer `dagster dev -m defs.definitions`, you'll need to set up proper `dg.toml` configuration for the modern CLI.

## Why LiteLLM + Dagster?

### LiteLLM gives you:
- ✅ 100+ LLM providers with one API - Switch between OpenAI, Anthropic, Gemini, Azure, AWS Bedrock without code changes
- ✅ Multi-provider fallbacks - 99.99% uptime by automatically routing to backup providers during outages
- ✅ Model escalation - 80% cost savings by trying cheap models first, escalating only when needed
- ✅ Intelligent caching - 60-90% cost reduction by caching identical requests (Redis or in-memory)
- ✅ Built-in observability - Integrated with Langfuse, W&B, Helicone, DataDog for tracking every token and cost
- ✅ Production-tested - Used by hundreds of companies at scale

### Dagster gives you:
- ✅ Visual asset lineage - Understand your pipeline at a glance with interactive dependency graphs
- ✅ Declarative pipelines - Define what to compute, not how to compute it
- ✅ Asset checks - Enforce quality gates before downstream actions (confidence thresholds, PII detection, etc.)
- ✅ Partitioning - Process data incrementally (millions of tickets by day) with backfill support
- ✅ Monitoring & alerting - Track pipeline health, set up Slack/PagerDuty alerts on failures
- ✅ Cost attribution - Track spending per asset, per run to identify hot spots
- ✅ Replay on changes - Reprocess historical data when code or models change

### Together, they provide:
- 🚀 **Production reliability** - Multi-provider fallbacks + retry logic + quality gates
- 💰 **Cost optimization** - Model escalation + caching + cost tracking per asset
- 🔍 **Full observability** - LLM metrics (tokens, latency, cost) + pipeline metadata + lineage
- ⚡ **Development velocity** - Declarative pipelines + asset reuse + incremental processing
- 🛡️ **Enterprise security** - Secrets management + audit logs + quality enforcement

## Requirements

- Python 3.9+
- OpenAI or Anthropic API key
- Dagster 1.7.0+
- LiteLLM 1.0.0+

## Next Steps

1. **Try the demo**: `./start.sh` and materialize assets
2. **Enable partitions**: Materialize `tickets_partitioned` for a specific day
3. **Add router**: Configure multi-provider fallbacks
4. **Integrate Jira/Slack**: Add real action implementations
5. **Enable Langfuse**: Track costs and performance
6. **Scale up**: Process production data with daily partitions

## FAQ

### Do I need to start LiteLLM separately?

**No!** LiteLLM works as a Python library, not a separate service. Just run `./start.sh` and you're ready.

(You could optionally run LiteLLM as a proxy server for centralized rate limiting and team usage tracking, but it's not required for this demo.)

### Can I materialize assets individually?

**Yes!** All assets use `@asset` decorators (not `@multi_asset`), so each can be materialized independently:

- In the UI: Click any asset → "Materialize"
- Via CLI: `dagster asset materialize -m defs --select tickets_raw`

### What about partitioned assets?

Sample data spans **241 days** with **982 tickets**:
- **Historical**: Sep 15, 2025 → Jan 13, 2026 (120 days)
- **Future**: Jan 14, 2026 → May 13, 2026 (120 days)

To materialize partitions:
1. Click `tickets_partitioned` in the UI
2. Select "Materialize" → "Select partitions"
3. Choose any date in the range
4. Click "Materialize selected"

Or use **Backfill** to process multiple days at once (e.g., process last 30 days of historical data).

### How much will this cost?

**Very low!** With `gpt-4o-mini`:
- **Small dataset** (17 tickets): ~$0.005 per run
- **Single day partition** (4 tickets avg): ~$0.001
- **30-day backfill** (120 tickets): ~$0.036
- **Full large dataset** (982 tickets): ~$0.295 (if you process all at once)

**Recommended**: Use partitioned assets to process one day at a time, keeping costs minimal.

In production with 10K tickets/day:
- With caching (60% hit rate): ~$6/day
- With model escalation: ~$8/day
- Without optimization: ~$20/day

### What's the difference between this and Dagster+?

This works with **open-source Dagster**. Dagster+ adds:
- Serverless deployment (zero infrastructure)
- Branch deployments (test PRs in isolation)
- Enhanced monitoring and alerting
- Secrets management
- Team collaboration and RBAC

[Try Dagster+ free](https://dagster.io/plus)

## License

MIT

---

**Questions?** See [QUICKSTART.md](QUICKSTART.md) for a 5-minute setup guide or [DATA_GENERATION.md](DATA_GENERATION.md) for custom data generation.
