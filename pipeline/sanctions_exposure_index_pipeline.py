# -*- coding: utf-8 -*-
"""Canonical project data pipeline. Identity and sources come from config.yaml."""
import json
import os
import sys
import time
from datetime import datetime, timezone

import yaml

sys.path.insert(0, os.path.dirname(__file__))
from data_fetcher import fetch_exchange_rates, fetch_gdelt, fetch_gdelt_events, fetch_google_news_rss, safe_fetch
from openrouter_llm import analyze_with_llm

GDELT_SPACING_SECONDS = 6
GDELT_RETRIES = 3
GDELT_RETRY_WAIT_SECONDS = 20
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


def normalize_geo_points(geo):
    features = (geo or {}).get("features", [])[:200]
    points = []
    for feature in features:
        coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
        properties = feature.get("properties") or {}
        lat, lon = coords[1], coords[0]
        if not (isinstance(lat, (int, float)) and isinstance(lon, (int, float))):
            continue
        name = properties.get("name") or properties.get("locationName") or "Coverage point"
        points.append({
            "name": str(name)[:80],
            "lat": round(float(lat), 4),
            "lon": round(float(lon), 4),
            "count": int(properties.get("count") or 1),
        })
    return points


def extract_live_data(config):
    live = {}
    query = config.get("gdelt_query", "geopolitical risk")
    print(f"[LIVE] GDELT query: {query}")

    articles = []
    for attempt in range(1, GDELT_RETRIES + 1):
        articles = safe_fetch(fetch_gdelt, query, "1d", SNAPSHOT_SIZE) or []
        if articles:
            print(f"  GDELT articles: {len(articles)} (attempt {attempt})")
            break
        if attempt < GDELT_RETRIES:
            print(f"  GDELT attempt {attempt}: no articles; retrying in {GDELT_RETRY_WAIT_SECONDS}s")
            time.sleep(GDELT_RETRY_WAIT_SECONDS)

    used_fallback = False
    if not articles:
        articles = safe_fetch(fetch_google_news_rss, query, SNAPSHOT_SIZE) or []
        used_fallback = bool(articles)
        if used_fallback:
            print(f"  Google News RSS fallback: {len(articles)} articles")
            time.sleep(GDELT_SPACING_SECONDS)

    geo_points = normalize_geo_points(safe_fetch(fetch_gdelt_events, query, "1d"))
    if geo_points:
        live["geo_points"] = geo_points
        print(f"  GDELT geo points: {len(geo_points)}")

    if articles:
        live["gdelt_articles"] = articles[:SNAPSHOT_SIZE]

    if config.get("include_forex"):
        rates = safe_fetch(fetch_exchange_rates, "USD")
        if rates:
            live["exchange_rates"] = rates[:20]
            print(f"  Forex: {len(live['exchange_rates'])} rates")

    return live, used_fallback


def retain_previous(live, previous):
    notes = []
    previous_live = previous.get("live_data") or {}
    if not live.get("gdelt_articles") and previous_live.get("gdelt_articles"):
        live["gdelt_articles"] = previous_live["gdelt_articles"][:SNAPSHOT_SIZE]
        notes.append("GDELT news unavailable; retained last validated snapshot.")
        print(f"  gdelt_articles: retained {len(live['gdelt_articles'])} items from previous run")
    if not live.get("geo_points") and previous_live.get("geo_points"):
        live["geo_points"] = previous_live["geo_points"][:200]
        notes.append("GDELT geo unavailable; retained last validated snapshot.")
    return notes


def build_stats(articles, geo_points):
    domains = len({a.get("domain") for a in articles if a.get("domain")})
    tones = [float(a.get("tone")) for a in articles if isinstance(a.get("tone"), (int, float))]
    mean_tone = sum(tones) / len(tones) if tones else 0.0
    tone_index = round(max(0, min(100, 50 + mean_tone * 5)))
    direction = "positive" if mean_tone > 0.2 else ("negative" if mean_tone < -0.2 else "neutral")
    return [
        {"label": "Articles Tracked", "value": str(len(articles)), "delta": "live" if articles else "none"},
        {"label": "News Domains", "value": str(domains), "delta": "deduplicated"},
        {"label": "Tone Index", "value": f"{tone_index}/100 ({direction})", "delta": "GDELT scale"},
        {"label": "Geo Points", "value": str(len(geo_points)), "delta": "geolocated"},
    ]


def main():
    config = load_config()
    project = (config.get("project") or {}).get("id", "unknown-project")
    title = (config.get("project") or {}).get("name", project)
    print(f"=== {title} pipeline ===")

    previous = load_previous()
    live, used_fallback = extract_live_data(config)
    notes = retain_previous(live, previous)
    if used_fallback:
        notes.append("GDELT unavailable; headlines sourced via Google News RSS fallback.")

    articles = live.get("gdelt_articles", [])
    fresh_news = bool(articles) and not any("gdelt_articles" in note for note in notes)
    mode = "live" if fresh_news else ("partial" if articles else "unavailable")

    llm_summary = ""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key and articles:
        print("[LLM] Analyzing with OpenRouter...")
        llm_summary = analyze_with_llm(
            {
                "meta": {"project": project, "mode": mode},
                "events": articles[:5],
                "stats": build_stats(articles, live.get("geo_points", [])),
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
            "version": "1.1.0",
        },
        "stats": build_stats(articles, live.get("geo_points", [])),
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
    print(f"Done. {out_path} ({size} bytes) mode={mode} articles={len(articles)} geo={len(live.get('geo_points', []))}")


if __name__ == "__main__":
    main()
