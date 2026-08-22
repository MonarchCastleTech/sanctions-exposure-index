# -*- coding: utf-8 -*-
"""OpenRouter LLM integration with model fallback chain."""
import requests

API_URL = "https://openrouter.ai/api/v1/chat/completions"


def _model_list(model_config):
    if isinstance(model_config, str):
        return [model_config]
    models = []
    if isinstance(model_config, dict):
        primary = model_config.get("model")
        if primary:
            models.append(primary)
        fallback = model_config.get("fallback_model") or model_config.get("fallback")
        if fallback:
            models.append(fallback)
    return models


def analyze_with_llm(data, model_config, api_key):
    models = _model_list(model_config)
    if not models:
        print("[LLM] No model configured; skipping analysis")
        return ""
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/MonarchCastleTech",
        "X-Title": "MCT Intelligence Pipeline",
    }
    prompt = (
        "Analyze this intelligence data. Provide a concise 3-5 sentence brief.\n\n"
        "Project: " + str(data.get("meta", {}).get("project", "unknown")) + "\n"
        "Data mode: " + str(data.get("meta", {}).get("mode", "unknown")) + "\n"
        "Snapshot stats: " + json.dumps(data.get("stats", [])) + "\n\n"
        "Latest headlines: " + json.dumps(
            [
                {"title": e.get("title", ""), "domain": e.get("domain", ""), "tone": e.get("tone")}
                for e in (data.get("events") or [])[:5]
            ],
            ensure_ascii=False,
        )
    )
    import time

    for attempt, model in enumerate(models * 2):
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a senior intelligence analyst. Be factual and note that you describe a news sample, not ground truth."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 500,
            "temperature": 0.3,
        }
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                if content and content.strip():
                    print(f"[LLM] Success via {model}")
                    return content.strip()
                print(f"[LLM] {model} returned empty content")
                continue
            if response.status_code == 429:
                wait = 10 + attempt * 5
                print(f"[LLM] {model} rate-limited; retrying in {wait}s")
                time.sleep(wait)
                continue
            print(f"[LLM] {model} failed: HTTP {response.status_code}: {response.text[:200]}")
        except Exception as error:
            print(f"[LLM] {model} error: {error}")
    return ""
