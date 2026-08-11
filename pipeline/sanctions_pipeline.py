# -*- coding: utf-8 -*-
"""Sanctions Exposure Index - Data Extraction Pipeline"""
import os
import json
import yaml
import requests
from datetime import datetime, timezone
from openrouter_llm import analyze_with_llm

def load_config():
    with open('pipeline/config.yaml', 'r') as f:
        return yaml.safe_load(f)

def fetch_gdelt(query, timespan="1d"):
    """Fetch GDELT Global Knowledge Graph data."""
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {
        "query": query,
        "mode": "ArtList",
        "maxrecords": 250,
        "timespan": timespan,
        "format": "json"
    }
    try:
        r = requests.get(url, params=params, timeout=30)
        return r.json() if r.status_code == 200 else {"articles": []}
    except Exception as e:
        print(f"GDELT fetch error: {e}")
        return {"articles": []}

def fetch_acled(api_key, region=None):
    """Fetch ACLED conflict event data."""
    url = "https://api.acleddata.com/acled/read"
    params = {"key": api_key, "limit": 500, "terms": "accept"}
    if region:
        params["region"] = region
    try:
        r = requests.get(url, params=params, timeout=30)
        return r.json().get("data", []) if r.status_code == 200 else []
    except Exception as e:
        print(f"ACLED fetch error: {e}")
        return []

def fetch_opensanctions():
    """Fetch latest sanctions data from OpenSanctions."""
    url = "https://www.opensanctions.org/api/2/entities/"
    try:
        r = requests.get(url, params={"limit": 100}, timeout=30)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"OpenSanctions fetch error: {e}")
        return {}

def generate_demo_data(config):
    """Generate demonstration data structure."""
    return {
        "meta": {
            "project": "sanctions-exposure-index",
            "generated": datetime.now(timezone.utc).isoformat(),
            "sources": ["OpenSanctions", "OFAC SDN", "EU Sanctions", "UN Comtrade"],
            "version": "1.0.0"
        },
        "stats": [
            {"label": "Listed Entities", "value": "78,432", "delta": "+5%"},
            {"label": "New (7d)", "value": "+234", "delta": "+2"},
            {"label": "Relationships", "value": "2.1M", "delta": "-3%"},
            {"label": "Jurisdictions", "value": "42", "delta": "stable"},
        ],
        "entities": [
            {"id": i, "name": f"Entity {i}", "score": round(2 + (i * 1.3) % 8, 1), "category": "monitoring", "last_seen": datetime.now(timezone.utc).isoformat()}
            for i in range(1, 11)
        ],
        "events": [
            {"id": i, "title": f"Event {i}", "severity": ["low", "medium", "high"][i % 3], "timestamp": datetime.now(timezone.utc).isoformat(), "source": "OpenSanctions"}
            for i in range(1, 16)
        ],
        "timeseries": [
            {"date": f"2026-0{8 + (i // 28)}-{(i % 28) + 1:02d}", "value": round(3 + (i * 0.1) % 5, 2)}
            for i in range(30)
        ],
        "llm_summary": "Demo mode: Connect OpenRouter API for AI-generated analysis."
    }

def main():
    config = load_config()
    output = generate_demo_data(config)

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key:
        print("Running LLM analysis...")
        output["llm_summary"] = analyze_with_llm(
            output,
            config["openrouter"]["model"],
            api_key
        )

    os.makedirs("data", exist_ok=True)
    with open("data/output.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"Data written to data/output.json ({len(json.dumps(output))} bytes)")

if __name__ == "__main__":
    main()
