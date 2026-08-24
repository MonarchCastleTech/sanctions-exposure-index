# -*- coding: utf-8 -*-
"""Canonical project data pipeline. Identity and sources come from config.yaml."""
import json
import os
import sys
import time
from datetime import datetime, timezone

import yaml

sys.path.insert(0, os.path.dirname(__file__))
from data_fetcher import fetch_exchange_rates, fetch_google_news_rss, safe_fetch
from openrouter_llm import analyze_with_llm

SNAPSHOT_SIZE = 50
EVENT_LIMIT = 15


def load_config():
    path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_previous():
    try:
        with open("data/output.json", "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}


def extract_live_data(config):
    live = {}
    query = config.get("news_query") or "geopolitical risk"
    print(f"[LIVE] News query: {query}")

    articles = safe_fetch(fetch_google_news_rss, query, SNAPSHOT_SIZE) or []
    if articles:
        live["news_articles"] = articles[:SNAPSHOT_SIZE]
        print(f"  News RSS: {len(articles)} articles")

    if config.get("include_forex"):
        rates = safe_fetch(fetch_exchange_rates, "USD")
        if rates:
            live["exchange_rates"] = rates[:20]
            print(f"  Forex: {len(live['exchange_rates'])} rates")

    return live


def retain_previous(live, previous):
    notes = []
    previous_live = previous.get("live_data") or {}
    for key in ("news_articles"):
        if not live.get("news_articles") and previous_live.get(key):
            live["news_articles"] = previous_live[key][:SNAPSHOT_SIZE]
            notes.append("News feed unavailable; retained last validated snapshot.")
            print(f"  {key}: retained {len(live['news_articles'])} items from previous run")
            break
    return notes


def build_stats(articles, feeds):
    domains = len({a.get("domain") for a in articles if a.get("domain")})
    tones = [float(a.get("tone")) for a in articles if isinstance(a.get("tone"), (int, float))]
    mean_tone = sum(tones) / len(tones) if tones else 0.0
    tone_index = round(max(0, min(100, 50 + mean_tone * 5)))
    direction = "positive" if mean_tone > 0.2 else ("negative" if mean_tone < -0.2 else "neutral")
    return [
        {"label": "Articles Tracked", "value": str(len(articles)), "delta": "live" if articles else "none"},
        {"label": "News Domains", "value": str(domains), "delta": "deduplicated"},
        {"label": "Tone Index", "value": f"{tone_index}/100 ({direction})", "delta": "news scale"},
        {"label": "Live Feeds", "value": str(feeds), "delta": "connected"},
    ]


def main():
    config = load_config()
    project = (config.get("project") or {}).get("id", "unknown-project")
    title = (config.get("project") or {}).get("name", project)
    print(f"=== {title} pipeline ===")

    previous = load_previous()
    live = extract_live_data(config)
    notes = retain_previous(live, previous)

    articles = live.get("news_articles", [])
    fresh_news = bool(articles) and not any("retained" in note for note in notes)
    mode = "live" if fresh_news else ("partial" if articles else "unavailable")

    llm_summary = ""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key and articles:
        print("[LLM] Analyzing with OpenRouter...")
        llm_summary = analyze_with_llm(
            {
                "meta": {"project": project, "mode": mode},
                "events": articles[:5],
                "stats": build_stats(articles, len(live)),
            },
            config.get("openrouter"),
            api_key,
        )
        if llm_summary:
            print("[LLM] Summary received")

    output = {
        "meta": {
            "project": project,
            "generated": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "sources": [key for key, value in live.items() if value],
            "source_notes": notes,
            "version": "1.2.0",
        },
        "stats": build_stats(articles, len(live)),
        "live_data": live,
        "entities": [],
        "events": articles[:EVENT_LIMIT],
        "timeseries": [],
        "llm_summary": llm_summary,
    }

    os.makedirs("data", exist_ok=True)
    out_path = os.path.join("data", "output.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, ensure_ascii=False)

    size = os.path.getsize(out_path)
    print(f"Done. {out_path} ({size} bytes) mode={mode} articles={len(articles)}")


if __name__ == "__main__":
    main()
