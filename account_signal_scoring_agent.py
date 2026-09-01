#!/usr/bin/env python3
"""
Account Signal-Scoring Agent
-----------------------------
Scores accounts on fit + recency-weighted intent across multiple signal
types, then routes them to HOT_AE_ALERT, SDR_QUEUE, or NURTURE with an
AI-generated brief for the hottest accounts.

Usage:
    python account_signal_scoring_agent.py --input sample_accounts.csv
"""

import argparse
import csv
import math
import os
import sys
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

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


@dataclass
class Account:
    company: str
    industry: str
    company_size: int
    days_since_last_signal: int
    g2_comparison_visits: int
    pricing_page_views: int
    distinct_stakeholders_engaged: int
    product_trial_active_days: int
    content_downloads: int
    fit_score: int = field(default=0)
    intent_score: int = field(default=0)
    routing_tier: str = field(default="")
    brief: str = field(default="")

    @classmethod
    def from_dict(cls, d: dict) -> "Account":
        return cls(
            company=d["company"],
            industry=d["industry"],
            company_size=int(d["company_size"]),
            days_since_last_signal=int(d["days_since_last_signal"]),
            g2_comparison_visits=int(d["g2_comparison_visits"]),
            pricing_page_views=int(d["pricing_page_views"]),
            distinct_stakeholders_engaged=int(d["distinct_stakeholders_engaged"]),
            product_trial_active_days=int(d["product_trial_active_days"]),
            content_downloads=int(d["content_downloads"]),
        )


def score_fit(account: Account) -> int:
    score = 0
    if account.industry in ICP_PROFILE["target_industries"]:
        score += 50
    if account.company_size >= ICP_PROFILE["min_company_size"]:
        score += 50
    elif account.company_size >= ICP_PROFILE["min_company_size"] * 0.25:
        score += 20
    return min(score, 100)


def decay_factor(days_since: int) -> float:
    return math.pow(0.5, days_since / DECAY_HALF_LIFE_DAYS)


def score_intent(account: Account) -> int:
    raw = (
        account.g2_comparison_visits * SIGNAL_WEIGHTS["g2_comparison_visits"]
        + account.pricing_page_views * SIGNAL_WEIGHTS["pricing_page_views"]
        + account.distinct_stakeholders_engaged * SIGNAL_WEIGHTS["distinct_stakeholders_engaged"]
        + account.product_trial_active_days * SIGNAL_WEIGHTS["product_trial_active_days"]
        + account.content_downloads * SIGNAL_WEIGHTS["content_downloads"]
    )
    weighted = raw * decay_factor(account.days_since_last_signal)
    return min(int(weighted), 100)


def route(fit: int, intent: int) -> str:
    hot = ROUTING_THRESHOLDS["HOT_AE_ALERT"]
    sdr = ROUTING_THRESHOLDS["SDR_QUEUE"]
    if fit >= hot["fit"] and intent >= hot["intent"]:
        return "HOT_AE_ALERT"
    if fit >= sdr["fit"] and intent >= sdr["intent"]:
        return "SDR_QUEUE"
    return "NURTURE"


def generate_brief(account: Account) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return (
            f"{account.company} scores {account.fit_score}/100 fit, "
            f"{account.intent_score}/100 intent -> {account.routing_tier}. "
            f"(Set ANTHROPIC_API_KEY for an AI-generated brief.)"
        )
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            f"Write a 2-3 sentence account brief for a sales rep. Account: "
            f"{account.company}, industry: {account.industry}, size: "
            f"{account.company_size}. Signals in the last {account.days_since_last_signal} "
            f"days: {account.g2_comparison_visits} G2 comparison visits, "
            f"{account.pricing_page_views} pricing page views, "
            f"{account.distinct_stakeholders_engaged} distinct stakeholders engaged, "
            f"{account.product_trial_active_days} days of active trial use, "
            f"{account.content_downloads} content downloads. Fit: "
            f"{account.fit_score}/100, intent: {account.intent_score}/100, "
            f"routed {account.routing_tier}. Explain why and recommend a next action."
        )
        response = client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as exc:  # pragma: no cover
        return f"(Brief generation failed: {exc})"


def load_accounts(path: str) -> list[Account]:
    with open(path, newline="", encoding="utf-8") as f:
        return [Account.from_dict(row) for row in csv.DictReader(f)]


def main():
    parser = argparse.ArgumentParser(description="Score and route accounts by fit + intent.")
    parser.add_argument("--input", required=True, help="Path to an accounts CSV file")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    for account in load_accounts(args.input):
        account.fit_score = score_fit(account)
        account.intent_score = score_intent(account)
        account.routing_tier = route(account.fit_score, account.intent_score)
        account.brief = generate_brief(account)

        print(f"\nAccount: {account.company}")
        print(f"Fit: {account.fit_score}/100 | Intent: {account.intent_score}/100 (signal-weighted, recency-decayed)")
        print(f"Routing: {account.routing_tier}")
        print(f"Brief: {account.brief}")


if __name__ == "__main__":
    main()
