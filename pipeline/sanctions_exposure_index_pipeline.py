# -*- coding: utf-8 -*-
"""Autonomous public-data pipeline for sanctions-expansion early warning."""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import yaml

sys.path.insert(0, os.path.dirname(__file__))
from data_fetcher import fetch_google_news_rss, fetch_ofac_press_releases, fetch_ofac_sdn_snapshot, safe_fetch
from sanctions_warning_model import build_sanctions_warning

SNAPSHOT_SIZE = 50
EVENT_LIMIT = 15


def load_config():
    with open(os.path.join(os.path.dirname(__file__), "config.yaml"), "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_previous():
    try:
        with open("data/output.json", "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}


def _retained(previous_live, key):
    value = previous_live.get(key)
    if not value:
        return None
    retained = dict(value) if isinstance(value, dict) else list(value)
    if isinstance(retained, dict):
        retained["retained"] = True
    return retained


def extract_live_data(config, previous):
    query = config.get("news_query") or "(sanctions OR embargo OR export controls) when:7d"
    with ThreadPoolExecutor(max_workers=3) as executor:
        jobs = {
            "ofac_sdn": executor.submit(fetch_ofac_sdn_snapshot),
            "ofac_releases": executor.submit(fetch_ofac_press_releases, 4),
            "news_articles": executor.submit(safe_fetch, fetch_google_news_rss, query, SNAPSHOT_SIZE),
        }
    live = {key: job.result() for key, job in jobs.items()}
    live["news_articles"] = list(live.get("news_articles") or [])[:SNAPSHOT_SIZE]
    notes = []
    previous_live = previous.get("live_data") or {}
    for key, label in (("ofac_sdn", "OFAC SDN"), ("ofac_releases", "OFAC releases")):
        if not live.get(key):
            live[key] = _retained(previous_live, key)
            if live[key]:
                notes.append(f"{label} unavailable; retained last accepted snapshot.")
    if not live["news_articles"] and previous_live.get("news_articles"):
        live["news_articles"] = list(previous_live["news_articles"])[:SNAPSHOT_SIZE]
        notes.append("Context news unavailable; retained last accepted snapshot.")
    return {key: value for key, value in live.items() if value}, notes


def build_stats(warning):
    health = warning.get("data_health") or {}
    delta = next((row for row in warning.get("components", []) if row.get("id") == "sdn_delta_breadth"), {})
    return [
        {"label": "Expansion Pressure", "value": f"{warning.get('score', 0):.1f}/100", "delta": warning.get("level", "UNAVAILABLE")},
        {"label": "Official SDN Entries", "value": f"{health.get('sdn_entries', 0):,}", "delta": f"{(delta.get('added_count') or 0):+d} since accepted snapshot"},
        {"label": "Official Releases", "value": str(health.get("ofac_releases", 0)), "delta": "rolling official baseline"},
        {"label": "Model Coverage", "value": f"{health.get('available_components', 0)}/4", "delta": warning.get("confidence", "LOW") + " confidence"},
    ]


def main():
    config = load_config()
    previous = load_previous()
    live, notes = extract_live_data(config, previous)
    snapshot = live.get("ofac_sdn") or {}
    releases = live.get("ofac_releases") or {}
    if not snapshot and not releases:
        print("No official source available; preserving last-good output.")
        return False

    warning = build_sanctions_warning(
        snapshot,
        releases,
        previous_snapshot=(previous.get("live_data") or {}).get("ofac_sdn"),
        previous_warning=previous.get("early_warning"),
    )
    official_current = snapshot and not (snapshot.get("cached") or snapshot.get("retained"))
    releases_current = releases and not (releases.get("cached") or releases.get("retained"))
    mode = "live" if official_current and releases_current else "partial"
    articles = live.get("news_articles") or []
    events = list((releases.get("releases") or [])[:EVENT_LIMIT]) or articles[:EVENT_LIMIT]
    output = {
        "meta": {
            "project": (config.get("project") or {}).get("id", "sanctions-exposure-index"),
            "generated": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "sources": ["OFAC Sanctions List Service", "OFAC press releases", "FRED Brent/WTI"],
            "source_notes": notes,
            "version": "2.0.0",
        },
        "early_warning": warning,
        "stats": build_stats(warning),
        "live_data": live,
        "events": events,
        "llm_summary": "",
    }
    os.makedirs("data", exist_ok=True)
    with open("data/output.json", "w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, ensure_ascii=False)
    print(f"Done. mode={mode} score={warning['score']} level={warning['level']} entries={snapshot.get('count', 0)}")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if main() else 2)
