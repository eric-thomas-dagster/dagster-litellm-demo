# Quick Start (5 Minutes)

Get the LiteLLM + Dagster demo running fast.

## 1. Install

```bash
cd dagster_litellm_demo
pip install -e .
```

## 2. Configure

```bash
cp .env.example .env
```

Edit `.env` and add your API key:

```bash
LITELLM_DEFAULT_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-your-key-here
```

Or use Anthropic:

```bash
LITELLM_DEFAULT_MODEL=claude-3-5-haiku-20241022
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

## 3. Run

**Option A: Using the start script (recommended)**
```bash
./start.sh
```

**Option B: Direct command**
```bash
dg dev
```

Open http://localhost:3000

**Note:** You don't need to start LiteLLM separately! We use it as a Python library, not as a separate service.

## 4. Execute

In the Dagster UI:

1. Click "Assets" in left sidebar
2. **Option A:** Click "Materialize all" (runs everything)
3. **Option B:** Click any individual asset → "Materialize" (runs just that asset)
4. Watch the pipeline run!

**Asset Groups:**
- `ticket_triage` - Main pipeline (5 assets)
- `partitioned_triage` - Daily partitions (3 assets)
- `examples` - Feature demos (6 assets)

## What Just Happened?

The pipeline processed 17 support tickets (spanning 7 days):

```
tickets_raw → tickets_clean → triage_llm → triage_eval → triage_actions
```

- **triage_llm**: LiteLLM classification with model escalation (confidence < 0.75 → retry with better model)
- **triage_eval**: Quality gates (confidence, PII, reply quality)
- **triage_actions**: Smart routing (auto-reply vs manual review)

Plus 5 asset checks monitoring quality and cost.

## View Results

- **Assets tab**: See lineage graph
- **Click any asset**: View metadata (tokens, cost, samples)
- **Checks tab**: See quality gate results
- **Runs tab**: View execution logs

## Next Steps

See [README.md](README.md) for:
- Model escalation + quality gates
- Daily partitions for scale
- Multi-provider fallbacks (router)
- Production actions (Jira, Slack)
- Caching (50-90% cost savings)
- Schedules & jobs

## Troubleshooting

**"Module litellm not found"**
→ Run `pip install -e .`

**"No API key"**
→ Make sure `.env` exists with `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`

**"Rate limit exceeded"**
→ Add `enable_cache=True` to resource config in `__init__.py`
