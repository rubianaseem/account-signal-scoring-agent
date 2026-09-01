#!/usr/bin/env python3
"""
Account Signal-Scoring Agent (v2 — evidence-gathering)
-----------------------------------------------
Gathers signal evidence per account into a persistent "brain" file
(brain/<account>.json + a human-readable .md rendering) and computes
fit/intent from accumulated evidence with recency decay — not a
one-off snapshot. Includes a --report mode that ranks every account
you've tracked and tells reps where to spend their time this week.

Usage:
    python account_signal_scoring_agent.py --input sample_accounts.csv
    python account_signal_scoring_agent.py --report
    python account_signal_scoring_agent.py --show "Nimbus Manufacturing"
"""

import argparse
import csv
import json
import math
import os
import re
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

BRAIN_DIR = "brain"

SIGNAL_WEIGHTS = {
    "g2_comparison_visits": 8,
    "pricing_page_views": 6,
    "distinct_stakeholders_engaged": 10,
    "product_trial_active_days": 4,
    "content_downloads": 3,
}
DECAY_HALF_LIFE_DAYS = 10

ICP_PROFILE = {
    "target_industries": {"Manufacturing", "SaaS", "Healthcare", "Energy", "Financial Services"},
    "min_company_size": 200,
}

ROUTING_THRESHOLDS = {
    "HOT_AE_ALERT": {"fit": 65, "intent": 70},
    "SDR_QUEUE": {"fit": 40, "intent": 35},
}


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "unknown"


def load_brain(slug: str) -> dict:
    path = os.path.join(BRAIN_DIR, f"{slug}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {
        "company": None,
        "industry": None,
        "company_size": 0,
        "signals": {k* 0 for k in SIGNAL_WEIGHTS},
        "last_signal_date": None,
        "evidence_log": [],
        "verdict_history": [],
    }


def save_brain(slug: str, brain: dict):
    os.makedirs(BRAIN_DIR, exist_ok=True)
    with open(os.path.join(BRAIN_DIR, f"{slug}.json"), "w", encoding="utf-8") as f:
        json.dump(brain, f, indent=2)
    render_markdown(slug, brain)


def render_markdown(slug: str, brain: dict):
    lines = [f"# {brain['company']}", "", "## Profile"]
    lines.append(f"- Industry: {brain.get('industry') or 'Unknown'}")
    lines.append(f"- Company size: {brain.get('company_size') or 'Unknown'}")
    lines.append("")
    lines.append("## Accumulated signals")
    for key, value in brain["signals"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Evidence log")
    for entry in brain["evidence_log"]:
        lines.append(f"- {entry['date']}: {entry['note']}")
    lines.append("")
    if brain.get("latest_verdict"):
        v = brain["latest_verdict"]
        lines.append(f"## Latest verdict ({v['date']})")
        lines.append(f"- Fit: {v['fit_score']}/100")
        lines.append(f"- Intent: {v['intent_score']}/100 (recency-decayed)")
        lines.append(f"- Routing: {v['routing_tier']}")
        lines.append(f"- Reasoning: {v['brief']}")
    with open(os.path.join(BRAIN_DIR, f"{slug}.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def ingest_row(brain: dict, row: dict, today: str) -> list:
    changes = []
    brain["company"] = row["company"]
    brain["industry"] = row["industry"]
    brain["company_size"] = int(row["company_size"])
    brain["last_signal_date"] = today

    for key in SIGNAL_WEIGHTS:
        added = int(row[key])
        if added:
            brain["signals"][key] += added
            changes.append(f"+{added} {key.replace('_', ' ')}")

    brain["evidence_log"].append(
        {"date": today, "note": ", ".join(changes) if changes else "checked in, no new signals"}
    )
    return changes


def score_fit(brain: dict) -> int:
    score = 0
    if brain["industry"] in ICP_PROFILE["target_industries"]:
        score += 50
    if brain["company_size"] >= ICP_PROFILE["min_company_size"]:
        score += 50
    elif brain["company_size"] >= ICP_PROFILE["min_company_size"] * 0.25:
        score += 20
    return min(score, 100)


def days_since(date_str: str, today: str) -> int:
    if not date_str:
        return 999
    d1 = datetime.strptime(date_str, "%Y-%m-%d")
    d2 = datetime.strptime(today, "%Y-%m-%d")
    return max((d2 - d1).days, 0)


def score_intent(brain: dict, today: str) -> int:
    raw = sum(brain["signals"][k] * w for k, w in SIGNAL_WEIGHTS.items())
    decay = math.pow(0.5, days_since(brain["last_signal_date"], today) / DECAY_HALF_LIFE_DAYS)
    return min(int(raw * decay), 100)


def route(fit: int, intent: int) -> str:
    hot = ROUTING_THRESHOLDS["HOT_AE_ALERT"]
    sdr = ROUTING_THRESHOLDS["SDR_QUEUE"]
    if fit >= hot["fit"] and intent >= hot["intent"]:
        return "HOT_AE_ALERT"
    if fit >= sdr["fit"] and intent >= sdr["intent"]:
        return "SDR_QUEUE"
    return "NURTURE"


def generate_brief(brain: dict, fit: int, intent: int, tier: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return (
            f"{brain['company']} scores {fit}/100 fit, {intent}/100 intent "
            f"across {len(brain['evidence_log'])} logged check-ins -> {tier}. "
            f"(Set ANTHROPIC_API_KEY for an AI-generated brief.)"
        )
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        history = "; ".join(e["note"] for e in brain["evidence_log"][-5:])
        prompt = (
            f"Write a 2-3 sentence account brief for a sales rep. Account: "
            f"{brain['company']}, industry: {brain['industry']}, size: "
            f"{brain['company_size']}. Fit: {fit}/100, intent: {intent}/100 "
            f"(recency-decayed), routed {tier}. Recent evidence: {history}. "
            f"Explain why and recommend a next action."
        )
        response = client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as exc:  # pragma: no cover
        return f"(Brief generation failed: {exc})"


def process_row(row: dict, today: str):
    slug = slugify(row["company"])
    brain = load_brain(slug)
    changes = ingest_row(brain, row, today)

    fit = score_fit(brain)
    intent = score_intent(brain, today)
    tier = route(fit, intent)
    brief = generate_brief(brain, fit, intent, tier)

    brain["latest_verdict"] = {
        "date": today, "fit_score": fit, "intent_score": intent,
        "routing_tier": tier, "brief": brief,
    }
    brain["verdict_history"].append(brain["latest_verdict"])
    save_brain(slug, brain)

    print(f"\nAccount: {brain['company']}")
    print(f"New evidence this run: {', '.join(changes) if changes else '(none)'}")
    print(f"Fit: {fit}/100 | Intent: {intent}/100 (from {len(brain['evidence_log'])} check-ins)")
    print(f"Routing: {tier}")
    print(f"Brief: {brief}")
    print(f"Brain file: {BRAIN_DIR}/{slug}.md")


def report(today: str):
    if not os.path.isdir(BRAIN_DIR):
        print("No accounts tracked yet — run --input against a CSV first.")
        return

    accounts = []
    for filename in os.listdir(BRAIN_DIR):
        if not filename.endswith(".json"):
            continue
        with open(os.path.join(BRAIN_DIR, filename), encoding="utf-8") as f:
            brain = json.load(f)
        if brain.get("latest_verdict"):
            accounts.append(brain)

    accounts.sort(key=lambda b: (b["latest_verdict"]["fit_score"] + b["latest_verdict"]["intent_score"]), reverse=True)

    print(f"WHERE TO SPEND YOUR TIME THIS WEEK — {len(accounts)} accounts tracked\n")
    for b in accounts:
        v = b["latest_verdict"]
        print(f"[{v['routing_tier']:<14}] {b['company']:<28} fit {v['fit_score']:>3}  intent {v['intent_score']:>3}  ({v['date']})")

    hot = [b for b in accounts if b["latest_verdict"]["routing_tier"] == "HOT_AE_ALERT"]
    if hot:
        print(f"\n{len(hot)} account(s) need attention now: {', '.join(b['company'] for b in hot)}")


def show_company(name: str):
    slug = slugify(name)
    path = os.path.join(BRAIN_DIR, f"{slug}.md")
    if not os.path.exists(path):
        print(f"No brain file found for '{name}'.")
        return
    with open(path, encoding="utf-8") as f:
        print(f.read())


def main():
    parser = argparse.ArgumentParser(description="Gather account signal evidence and rank where to focus.")
    parser.add_argument("--input", help="Path to an accounts CSV file (ingests as new evidence)")
    parser.add_argument("--report", action="store_true", help="Rank all tracked accounts by fit+intent")
    parser.add_argument("--show", help="Show the accumulated brain file for an account")
    args = parser.parse_args()

    today = datetime.now().strftime("%Y-%m-%d")

    if args.report:
        report(today)
    elif args.show:
        show_company(args.show)
    elif args.input:
        if not os.path.exists(args.input):
            print(f"Input file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        with open(args.input, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                process_row(row, today)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
