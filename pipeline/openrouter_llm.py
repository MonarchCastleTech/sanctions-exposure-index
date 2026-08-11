# -*- coding: utf-8 -*-
"""OpenRouter LLM integration."""
import os
import json
import requests

def analyze_with_llm(data, model, api_key):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/MonarchCastleTech",
        "X-Title": "MCT Intelligence Pipeline"
    }
    prompt = "Analyze this intelligence data. Provide a concise 3-5 sentence brief:\n\n"
    prompt += "Project: " + data.get("meta", {}).get("project", "unknown") + "\n"
    prompt += "Mode: " + data.get("meta", {}).get("mode", "unknown") + "\n"
    prompt += "Sources: " + str(list(data.get("live_data", {}).keys())) + "\n\n"
    prompt += "Recent Events: " + json.dumps(data.get("events", [])[:5]) + "\n\nProvide analysis:"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a senior intelligence analyst."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 500,
        "temperature": 0.3
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return ""
    except Exception as e:
        return ""
