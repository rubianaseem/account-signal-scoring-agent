# Setup Guide

## 1. Where this installs

Plain Python script, nothing installed system-wide. Clone it, create a virtual environment inside the folder, install dependencies into that environment.

```bash
git clone https://github.com/rubianaseem/account-signal-scoring-agent.git
cd account-signal-scoring-agent

python3 -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

You'll see `(venv)` at the start of your terminal prompt when it's active. Type `deactivate` to leave it.

## 2. Run it with sample data

```bash
python account_signal_scoring_agent.py --input sample_accounts.csv
```

Runs entirely offline against the mock CSV.

## 3. Add your API key for AI-generated briefs (optional)

```bash
cp .env.example .env
```

Add to `.env`:

```
ANTHROPIC_API_KEY=your_key_here
```

Get one at https://console.anthropic.com/. Without it, the script still scores and routes accounts — you just get a templated (non-AI) brief instead of a written one.

## 4. Connecting real signal sources

This script expects one row per account with pre-aggregated signal counts. The work is turning your raw signal feeds into that shape — here's how for the most common sources:

**G2 (intent/comparison data)**
G2 provides a Buyer Intent export/API for paying accounts. Pull comparison-page visits per company and map them to the `g2_comparison_visits` column.

**6sense / Bombora (intent platforms)**
These already do account-level intent scoring — pull their per-account intent score via API and either feed it directly as a pre-computed intent score (bypassing `score_intent()`), or map their signal categories into the weighted signals here.

**Website behaviour (GA4 / HockeyStack / Dreamdata)**
Pull page-view and pricing-page-visit counts per account (these tools resolve anonymous visitors to companies via IP/firmographic matching) and map to `pricing_page_views`.

**Product usage (if you have a PLG motion)**
Pull trial/usage data from your product analytics (Mixpanel, Amplitude, or your own database) and map active days to `product_trial_active_days`.

**Putting it together via a warehouse**
The cleanest approach at scale: land all these signals in Snowflake (or BigQuery), join them into one row per account, and use Hightouch (or a simple scheduled query + CSV export) to feed this script. Replace `load_accounts()` in the script with a database query instead of a CSV read once you're at that point.

## 5. Using this repo with an AI coding assistant (Cursor, Claude Code, Codex, Grok)

You don't need any of these to run the script — they're for extending it.

**Cursor** — open the folder in Cursor, use chat (Cmd+L) to ask e.g. *"Add a loader that pulls accounts from Snowflake using the snowflake-connector-python package, aggregating the same signal columns this script expects"*

**Claude Code** — `cd` into the folder, run `claude`, ask it the same way — it can read `account_signal_scoring_agent.py` and write a new loader function directly

**Codex CLI** — `cd` into the folder, run `codex`, same approach as Claude Code

**Grok (or any assistant without file access)** — paste the script's contents into the chat along with what you want added, then copy the result back into the file yourself

## Troubleshooting

- **"ModuleNotFoundError"** — activate the virtual environment and re-run `pip install -r requirements.txt`
- **All accounts route to NURTURE** — check your `ICP_PROFILE` industries/size match your actual data, and that signal counts aren't all zero
- **Briefs look templated, not AI-written** — `ANTHROPIC_API_KEY` isn't set, or `.env` isn't in the same folder as the script
