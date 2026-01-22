# Data Generation Guide

This demo uses **two separate datasets** optimized for different use cases:

1. **tickets_small.json** - For non-partitioned assets (quick demos, low token usage)
2. **tickets_large.json** - For partitioned assets (production simulation, scalable)

## Why Two Datasets?

### Non-Partitioned Assets Problem
Non-partitioned assets (like `triage_llm`) process **ALL tickets at once**:
- More tickets = more API calls = more tokens = higher cost
- Demo runs could accidentally burn through API credits

### Solution: Separate Datasets
- **Small dataset**: 20-30 tickets for quick demos
- **Large dataset**: Hundreds of tickets with historical + future data

## Quick Start

Generate both datasets with defaults:
```bash
python generate_sample_data.py
```

This creates:
- `tickets_small.json`: 21 tickets (7 days, lower volume)
- `tickets_large.json`: 385 tickets (60 historical + 30 future days)

## CLI Options

### Date Ranges

```bash
# Generate 90 historical + 60 future days
python generate_sample_data.py --historical-days 90 --future-days 60

# Result: tickets_large.json with 150 days of data
```

### Ticket Volume

```bash
# High-volume scenario (more tickets per day)
python generate_sample_data.py --weekday-tickets 10 15 --weekend-tickets 2 5

# Low-volume scenario (fewer tickets per day)
python generate_sample_data.py --weekday-tickets 1 3 --weekend-tickets 0 1
```

**Default volumes:**
- Weekdays: 3-8 tickets/day
- Weekends: 0-3 tickets/day

### Generate Specific Dataset

```bash
# Generate only large dataset (for partitioned assets)
python generate_sample_data.py --large-only

# Generate only small dataset (for demos)
python generate_sample_data.py --small-only --small-days 5

# Result: 5-day small dataset for even faster demos
```

## Example Scenarios

### 1. Quick Demo Setup (Minimal Token Usage)
```bash
# Small dataset with just 3 days
python generate_sample_data.py --small-only --small-days 3

# Result: ~10 tickets total
# Perfect for: Quick demos, presentations, testing
```

### 2. Production Simulation
```bash
# Large dataset with 6 months of data + 2 months future
python generate_sample_data.py --large-only \
  --historical-days 180 \
  --future-days 60 \
  --weekday-tickets 5 12

# Result: ~1,500 tickets over 240 days
# Perfect for: Backfill testing, schedule simulation, scale testing
```

### 3. High-Volume Scenario
```bash
# Simulate busy support team
python generate_sample_data.py \
  --weekday-tickets 15 25 \
  --weekend-tickets 5 10

# Result: ~1,000+ tickets over 90 days
# Perfect for: Performance testing, cost estimation
```

### 4. Both Datasets with Custom Settings
```bash
# Custom small dataset (10 days) + large dataset (120 days)
python generate_sample_data.py \
  --small-days 10 \
  --historical-days 90 \
  --future-days 30
```

## Data Structure

Each ticket includes:
```json
{
  "id": "T-0001",
  "subject": "Can't login to my account",
  "body": "Hi support team, I've been trying...",
  "customer_name": "Alice Johnson",
  "customer_email": "user1@example.com",
  "created_at": "2026-01-12T14:30:00Z",
  "source": "zendesk"
}
```

**Ticket variety:**
- Access issues (login, passwords, permissions)
- Bugs (crashes, performance, data issues)
- How-to questions
- Billing inquiries
- Feature requests
- Security reports
- Positive feedback

**Realistic patterns:**
- More tickets on weekdays
- Fewer tickets on weekends
- Random times during business hours (9am-6pm)
- 20 different customer names
- 4 different sources (zendesk, intercom, jira, email)

## How Assets Use the Data

### Non-Partitioned Pipeline
**Assets**: `tickets_raw` → `tickets_clean` → `triage_llm` → `triage_eval` → `triage_actions`

**Data source**: `tickets_small.json`

**Behavior**:
- Loads ALL tickets at once
- Processes everything in a single run
- Uses small dataset to minimize token usage

**Cost example** (with defaults):
- 21 tickets × ~500 tokens/ticket × $0.60/1M = **~$0.006 per run**

### Partitioned Pipeline
**Assets**: `tickets_partitioned` → `triage_with_fallbacks` → `actions_production`

**Data source**: `tickets_large.json`

**Behavior**:
- Loads one day's tickets at a time
- Filters by partition date
- Can handle thousands of tickets efficiently

**Cost example** (with defaults):
- 5 tickets/day × ~500 tokens/ticket × $0.60/1M = **~$0.0015 per partition**
- 30 partitions = **~$0.045 total**

## Regenerating Data

### After Code Changes
If you update ticket templates or generation logic:
```bash
python generate_sample_data.py
```

### Before Demo
Generate fresh data with today's date as the anchor:
```bash
# Small dataset for demo
python generate_sample_data.py --small-only --small-days 7

# Data will span: (today - 7 days) to today
```

### For Testing
Generate minimal data to test changes:
```bash
python generate_sample_data.py --small-only --small-days 2
```

## Viewing Generated Data

```bash
# View small dataset
python -c "import json; print(json.dumps(json.load(open('sample_data/tickets_small.json')), indent=2))" | head -50

# View large dataset summary
python -c "
import json
from collections import Counter
data = json.load(open('sample_data/tickets_large.json'))
print(f'Total tickets: {len(data)}')
dates = [t['created_at'][:10] for t in data]
print(f'Date range: {min(dates)} to {max(dates)}')
print(f'Dates with tickets: {len(set(dates))}')
print(f'Avg tickets/day: {len(data) / len(set(dates)):.1f}')
"
```

## Cost Estimation

Use the generator to estimate costs before running:

```bash
# Generate with your planned settings
python generate_sample_data.py --weekday-tickets 10 15

# Check ticket count
python -c "import json; print(f'Total tickets: {len(json.load(open(\"sample_data/tickets_large.json\")))}')"

# Estimate cost (assuming 500 tokens/ticket, $0.60/1M for gpt-4o-mini)
python -c "
import json
tickets = len(json.load(open('sample_data/tickets_large.json')))
tokens = tickets * 500
cost = (tokens / 1_000_000) * 0.60
print(f'Estimated cost: \${cost:.4f}')
"
```

## Best Practices

1. **Use small dataset for development**
   - Faster iteration
   - Lower API costs
   - Easier to debug

2. **Use large dataset for production simulation**
   - Test backfills
   - Validate schedules
   - Monitor performance at scale

3. **Regenerate data regularly**
   - Keep future dates relevant
   - Test with fresh data patterns
   - Update ticket templates as needed

4. **Version control your settings**
   ```bash
   # Document your generation command
   python generate_sample_data.py \
     --historical-days 60 \
     --future-days 30 \
     --weekday-tickets 5 10 \
     > data_generation.log
   ```

5. **Test both datasets work**
   ```bash
   # After generation, test both pipelines
   dagster job execute -m defs.definitions -j standard_triage_pipeline
   dagster job execute -m defs.definitions -j partitioned_triage_pipeline --config '{"partitions": ["2026-01-12"]}'
   ```

## Troubleshooting

**Issue**: "No tickets found for partition"
```bash
# Check if date has tickets
python -c "
import json
data = json.load(open('sample_data/tickets_large.json'))
partition = '2026-01-12'
count = sum(1 for t in data if t['created_at'].startswith(partition))
print(f'Tickets for {partition}: {count}')
"
```

**Issue**: "File not found"
```bash
# Verify files exist
ls -lh sample_data/

# Regenerate if missing
python generate_sample_data.py
```

**Issue**: "Too many tokens used"
```bash
# Use smaller dataset for non-partitioned assets
python generate_sample_data.py --small-only --small-days 3

# Or reduce ticket volume
python generate_sample_data.py --weekday-tickets 1 2 --weekend-tickets 0 1
```

## Summary

| Dataset | Purpose | Size | Token Usage | Use Case |
|---------|---------|------|-------------|----------|
| **tickets_small.json** | Quick demos | 20-30 tickets | Low (~$0.01) | Non-partitioned assets, testing |
| **tickets_large.json** | Production sim | 300-500+ tickets | Medium ($0.05-0.10) | Partitioned assets, backfills |

Generate with:
```bash
python generate_sample_data.py
```

Customize with CLI options as needed!
