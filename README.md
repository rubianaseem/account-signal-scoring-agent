# Account Signal-Scoring Agent

Ingests intent and engagement signals across an account (website behaviour, product usage, G2 comparison visits, content engagement), scores the account against your ICP in real time, and routes high-priority accounts to SDR/AE with an AI-generated account brief.

This mirrors the signal-triggered routing agent I built in production at Speechmatics — ingesting intent signals from G2, website behaviour, and product usage, scoring accounts against the ICP model, and routing high-priority accounts with a Claude-generated brief.

## What it does

1. Takes an account record with aggregated signals (not just one contact — the whole account)
2. Scores **fit** (ICP match: industry, size, tech stack overlap) and **intent** (recency + volume of buying signals across the account)
3. Applies decay — a signal from today counts more than one from three weeks ago
4. Routes the account: `HOT_AE_ALERT`, `SDR_QUEUE`, or `NURTURE`
5. Generates an AI account brief summarising why the account is hot and what to lead with

## Quick start

```bash
git clone https://github.com/rubianaseem/account-signal-scoring-agent.git
cd account-signal-scoring-agent
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add ANTHROPIC_API_KEY (optional)
python account_signal_scoring_agent.py --input sample_accounts.csv
```

## Example output

```
Account: Nimbus Manufacturing
Fit: 88/100 | Intent: 91/100 (signal-weighted, recency-decayed)
Routing: HOT_AE_ALERT
Brief: Nimbus Manufacturing has visited a G2 comparison page twice in the
last 5 days and had 3 stakeholders view pricing — this is a buying-committee
signal, not a single-user signal. Recommend AE outreach within the hour,
leading with the comparison page's specific competitor mention.
```

## Cost note

Signal aggregation and scoring is pure rule-based logic — free, no API calls. Only the account brief for accounts that clear the routing threshold calls an LLM (roughly 1 call per hot/warm account, ~600 tokens), so cost scales with qualified accounts, not total signal volume.

## GTM tech stack this maps to

Built against these tools — swap in whatever you actually run:

| Signal / step | Tool used here | Swap with |
|---|---|---|
| Intent data (G2 comparison visits) | G2 | 6sense, Bombora, Intentsify |
| Website behaviour signals | Generic web analytics | GA4, HockeyStack, Dreamdata |
| Attribution / account journey | — | HockeyStack, Dreamdata, LeanData |
| Where scored accounts get routed to | — | Salesforce (create a Task/Alert), Slack webhook, HubSpot workflow |
| Data warehouse feed (optional) | CSV | Snowflake + Hightouch reverse ETL |

## Customising for your stack

- `SIGNAL_WEIGHTS` at the top of the script controls how much each signal type counts — tune to match what actually predicts pipeline in your funnel
- `DECAY_HALF_LIFE_DAYS` controls how fast old signals stop mattering
- Swap `sample_accounts.csv` for a live feed from your CDP, warehouse (Snowflake/Hightouch), or a webhook from G2/6sense/HockeyStack

## How this runs today (and what production would add)

**Trigger:** none built in — run manually (`python account_signal_scoring_agent.py --input ...`) or schedule it (cron/n8n) to re-score accounts on a timer. It doesn't fire automatically when a new signal comes in.

**Action taken:** prints fit/intent scores, routing tier, and the account brief to your terminal only. It does **not** create a Salesforce Task, alert an AE, or update any CRM field — that's a step you'd add on top.

**Self-learning:** no. `SIGNAL_WEIGHTS` and `DECAY_HALF_LIFE_DAYS` are hand-set — there's no model learning from which accounts actually converted. You'd revisit these manually as you see what predicts pipeline.

**Loop:** no persistent process — one pass over the input file per run, then it exits.

**What a production version would add:**
- A scheduled run (hourly/daily) or a webhook triggered by a real-time signal feed (G2/6sense webhook, warehouse change)
- A write-back step: create a Salesforce Task or update an "Account Score" field via API for HOT_AE_ALERT accounts
- A Slack alert to the AE's channel/DM for HOT_AE_ALERT accounts specifically
- Logging which accounts were flagged and what happened to them, to eventually validate/retune the signal weights
