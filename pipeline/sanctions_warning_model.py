"""Explainable sanctions-expansion precursor model.

The output measures public pressure signals. It is not legal advice, a list
screening result, or a probability that any person will be designated.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests


WEIGHTS = {
    "ofac_action_velocity": 0.35,
    "sdn_delta_breadth": 0.20,
    "official_posture_shift": 0.25,
    "energy_market_dislocation": 0.20,
}

POSTURE_TERMS = {
    "unprecedented": 3.5,
    "maximum pressure": 3.5,
    "economic d-day": 3.5,
    "economic outcast": 3.0,
    "largest action": 3.0,
    "intensifies": 3.0,
    "increases sanctions": 3.0,
    "additional sanctions": 2.5,
    "further action": 2.5,
    "escalating pressure": 2.5,
    "dismantles": 2.0,
    "disrupts": 2.0,
    "targets": 1.5,
    "targeting": 1.5,
    "sanctions": 1.0,
}

RELIEF_TERMS = ("relief", "removal", "rescission", "general license", "authorizes")

THEMES = {
    "iran": ("iran", "irgc"),
    "russia": ("russia", "russian"),
    "cuba": ("cuba", "cuban"),
    "venezuela": ("venezuela", "venezuelan"),
    "counter_terrorism": ("terror", "hizballah", "hamas"),
    "counter_narcotics": ("narcotics", "cartel", "cocaine"),
    "non_proliferation": ("proliferation", "weapons", "missile", "nuclear"),
    "cyber": ("cyber", "ransomware", "crypto exchange"),
}

FRED_SERIES = {
    "brent": {"id": "DCOILBRENTEU", "label": "Brent crude", "unit": "USD/barrel"},
    "wti": {"id": "DCOILWTICO", "label": "WTI crude", "unit": "USD/barrel"},
}


def _clamp(value, low=0.0, high=100.0):
    return max(low, min(high, float(value)))


def _parse_date(value):
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _parse_datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _robust_z(current, baseline):
    clean = [float(value) for value in baseline if math.isfinite(float(value))]
    if len(clean) < 4:
        return 0.0
    median = statistics.median(clean)
    mad = statistics.median(abs(value - median) for value in clean)
    if mad > 1e-9:
        return (current - median) / (1.4826 * mad)
    spread = statistics.pstdev(clean)
    return (current - median) / spread if spread > 1e-9 else 0.0


def _release_text(release):
    return f"{release.get('title') or ''} {release.get('action_title') or ''}".lower()


def _weekly_release_metrics(releases, now):
    weeks = [{"actions": 0, "designation": 0, "posture": 0.0, "release_count": 0} for _ in range(14)]
    evidence = []
    for release in releases:
        observed = _parse_date(release.get("date"))
        if not observed:
            continue
        age = (now.date() - observed).days
        if not 0 <= age < len(weeks) * 7:
            continue
        week = age // 7
        text = _release_text(release)
        posture_terms = sorted(term for term in POSTURE_TERMS if term in text)
        relief_terms = sorted(term for term in RELIEF_TERMS if term in text)
        theme_matches = sorted(theme for theme, terms in THEMES.items() if any(term in text for term in terms))
        designation = any(token in text for token in ("designation", "sanction", "targets", "targeting", "pressure", "dismantl", "disrupt"))
        weeks[week]["actions"] += 1
        weeks[week]["release_count"] += 1
        weeks[week]["designation"] += int(designation)
        weeks[week]["posture"] += sum(POSTURE_TERMS[term] for term in posture_terms)
        if week == 0:
            evidence.append({
                **release,
                "posture_terms": posture_terms,
                "relief_terms": relief_terms,
                "themes": theme_matches,
                "designation_signal": designation,
            })
    return weeks, evidence


def _action_component(releases, now):
    weeks, evidence = _weekly_release_metrics(releases, now)
    baseline = [float(row["designation"]) for row in weeks[1:13]]
    current = weeks[0]["designation"]
    anomaly_z = _robust_z(float(current), baseline)
    current_themes = sorted({theme for row in evidence for theme in row["themes"]})
    density_score = _clamp(current * 8, high=45)
    anomaly_score = _clamp(max(0.0, anomaly_z) * 12.5, high=35)
    breadth_score = _clamp(len(current_themes) * 4, high=20)
    return {
        "id": "ofac_action_velocity",
        "label": "OFAC action velocity",
        "available": bool(releases),
        "score": round(_clamp(density_score + anomaly_score + breadth_score), 1),
        "releases_considered": len(releases),
        "current_7d_designation_releases": current,
        "current_7d_all_releases": weeks[0]["actions"],
        "prior_7d_designation_releases": weeks[1]["designation"],
        "baseline_weeks": len(baseline),
        "baseline_weekly_median": round(statistics.median(baseline), 2) if baseline else 0.0,
        "anomaly_z": round(anomaly_z, 2),
        "themes": current_themes,
        "evidence": sorted(evidence, key=lambda row: str(row.get("date") or ""), reverse=True)[:12],
    }


def _sdn_delta_component(snapshot, previous_snapshot):
    entries = list(snapshot.get("entries") or [])
    previous_entries = list((previous_snapshot or {}).get("entries") or [])
    current_map = {str(row.get("id")): row for row in entries if row.get("id")}
    previous_map = {str(row.get("id")): row for row in previous_entries if row.get("id")}
    available = bool(entries) and bool(previous_entries)
    added_ids = sorted(set(current_map) - set(previous_map)) if available else []
    removed_ids = sorted(set(previous_map) - set(current_map)) if available else []
    score = _clamp(len(added_ids) * 2.5 + len(removed_ids)) if available else 0.0
    program_counts = {}
    type_counts = {}
    for row in entries:
        program = str(row.get("program") or "Unspecified")
        entry_type = str(row.get("type") or "Unspecified")
        program_counts[program] = program_counts.get(program, 0) + 1
        type_counts[entry_type] = type_counts.get(entry_type, 0) + 1
    return {
        "id": "sdn_delta_breadth",
        "label": "Exact SDN list delta",
        "available": available,
        "score": round(score, 1),
        "current_count": len(entries),
        "previous_count": len(previous_entries) if previous_entries else None,
        "added_count": len(added_ids) if available else None,
        "removed_count": len(removed_ids) if available else None,
        "changed": bool(added_ids or removed_ids) if available else None,
        "publish_date": snapshot.get("publish_date"),
        "sha256": snapshot.get("sha256"),
        "top_programs": [
            {"program": key, "count": value}
            for key, value in sorted(program_counts.items(), key=lambda item: item[1], reverse=True)[:12]
        ],
        "types": [
            {"type": key, "count": value}
            for key, value in sorted(type_counts.items(), key=lambda item: item[1], reverse=True)
        ],
        "added": [current_map[key] for key in added_ids[:20]],
        "removed": [previous_map[key] for key in removed_ids[:20]],
        "retained": bool(snapshot.get("cached") or snapshot.get("retained")),
    }


def _posture_component(releases, now):
    weeks, evidence = _weekly_release_metrics(releases, now)
    current_count = weeks[0]["release_count"]
    current_rate = weeks[0]["posture"] / max(current_count, 1)
    baseline = [row["posture"] / row["release_count"] for row in weeks[1:13] if row["release_count"]]
    anomaly_z = _robust_z(current_rate, baseline)
    density_score = _clamp(current_rate * 12, high=55)
    anomaly_score = _clamp(max(0.0, anomaly_z) * 20, high=45)
    score = density_score if len(baseline) < 4 else 0.6 * density_score + 0.4 * anomaly_score
    matched = [row for row in evidence if row["posture_terms"]]
    relief = [row for row in evidence if row["relief_terms"]]
    return {
        "id": "official_posture_shift",
        "label": "Official coercive-language shift",
        "available": bool(releases),
        "score": round(_clamp(score), 1),
        "current_7d_releases": current_count,
        "current_weighted_term_rate": round(current_rate, 3),
        "baseline_weeks": len(baseline),
        "anomaly_z": round(anomaly_z, 2),
        "matched_release_count": len(matched),
        "relief_release_count": len(relief),
        "evidence": matched[:12],
        "terms": POSTURE_TERMS,
    }


def _market_cache_path(series_id):
    root = Path(os.path.expanduser("~")) / ".cache" / "sanctions-exposure-index" / "fred"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{series_id}.json"


def _fetch_fred_series(series_id, now):
    cache = _market_cache_path(series_id)
    start = (now.date() - timedelta(days=260)).isoformat()
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    error = None
    for attempt in range(1, 5):
        try:
            response = requests.get(url, timeout=25, headers={"User-Agent": "sanctions-exposure-index/2.0"})
            response.raise_for_status()
            rows = []
            for row in csv.DictReader(io.StringIO(response.text)):
                raw = row.get(series_id)
                if raw and raw != ".":
                    rows.append({"date": row["observation_date"], "value": float(raw)})
            if len(rows) < 20:
                raise ValueError("insufficient FRED observations")
            cache.write_text(json.dumps({"fetched_at": now.isoformat(), "rows": rows}), encoding="utf-8")
            return rows, False
        except Exception as exc:
            error = exc
            if attempt < 4:
                time.sleep(attempt)
    print(f"[FRED-{series_id}] live fetch failed after 4 attempts: {error}")
    try:
        payload = json.loads(cache.read_text(encoding="utf-8"))
        fetched = _parse_datetime(payload.get("fetched_at"))
        age = now - fetched if fetched else timedelta(days=999)
        if timedelta(0) <= age <= timedelta(hours=72) and len(payload.get("rows", [])) >= 20:
            return payload["rows"], True
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return [], False


def _energy_market_component(now):
    with ThreadPoolExecutor(max_workers=2) as executor:
        loaded = dict(zip(FRED_SERIES, executor.map(lambda key: _fetch_fred_series(FRED_SERIES[key]["id"], now), FRED_SERIES)))
    indicators = []
    series_by_date = {}
    for key, spec in FRED_SERIES.items():
        rows, cached = loaded[key]
        values = [float(row["value"]) for row in rows]
        changes = [((values[index] / values[index - 5]) - 1) * 100 for index in range(5, len(values)) if values[index - 5]]
        latest = changes[-1] if changes else 0.0
        anomaly_z = _robust_z(latest, changes[:-1]) if changes else 0.0
        indicators.append({
            "id": key,
            "label": spec["label"],
            "available": bool(rows),
            "latest_value": round(values[-1], 3) if values else None,
            "five_session_change_pct": round(latest, 3),
            "anomaly_z": round(anomaly_z, 2),
            "score": round(_clamp((abs(anomaly_z) - 1) * 35), 1),
            "observed_at": rows[-1]["date"] if rows else None,
            "unit": spec["unit"],
            "cached": cached,
            "source_url": f"https://fred.stlouisfed.org/series/{spec['id']}",
        })
        series_by_date[key] = {row["date"]: float(row["value"]) for row in rows}

    common_dates = sorted(set(series_by_date.get("brent", {})) & set(series_by_date.get("wti", {})))
    spreads = [series_by_date["brent"][day] - series_by_date["wti"][day] for day in common_dates]
    spread_changes = [spreads[index] - spreads[index - 5] for index in range(5, len(spreads))]
    if spread_changes:
        spread_z = _robust_z(spread_changes[-1], spread_changes[:-1])
        indicators.append({
            "id": "brent_wti_spread",
            "label": "Brent-WTI spread",
            "available": True,
            "latest_value": round(spreads[-1], 3),
            "five_session_change": round(spread_changes[-1], 3),
            "anomaly_z": round(spread_z, 2),
            "score": round(_clamp((abs(spread_z) - 1) * 35), 1),
            "observed_at": common_dates[-1],
            "unit": "USD/barrel",
            "cached": any(row.get("cached") for row in indicators),
            "source_url": "https://fred.stlouisfed.org/",
        })
    available = [row for row in indicators if row.get("available")]
    ranked = sorted((row["score"] for row in available), reverse=True)
    score = ranked[0] if len(ranked) == 1 else (0.65 * ranked[0] + 0.35 * ranked[1] if ranked else 0.0)
    return {
        "id": "energy_market_dislocation",
        "label": "Oil-price and benchmark-spread dislocation",
        "available": bool(available),
        "score": round(score, 1),
        "indicators": indicators,
        "series_available": sum(row["id"] in FRED_SERIES and row.get("available") for row in indicators),
        "retained": bool(available) and all(row.get("cached") for row in available),
    }


def _level(score):
    if score >= 75:
        return "SEVERE"
    if score >= 55:
        return "ELEVATED"
    if score >= 35:
        return "WATCH"
    return "BASELINE"


def build_sanctions_warning(snapshot, press, previous_snapshot=None, previous_warning=None, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    releases = list(press.get("releases") or [])
    action = _action_component(releases, now)
    delta = _sdn_delta_component(snapshot, previous_snapshot or {})
    posture = _posture_component(releases, now)
    market = _energy_market_component(now)
    if not market.get("available") and previous_warning:
        previous_issued = _parse_datetime(previous_warning.get("issued_at"))
        age = now - previous_issued if previous_issued else timedelta(days=999)
        previous_market = next(
            (row for row in previous_warning.get("components", []) if row.get("id") == "energy_market_dislocation" and row.get("available")),
            None,
        )
        if previous_market and timedelta(0) <= age <= timedelta(hours=72):
            market = dict(previous_market)
            market["retained"] = True
    action["retained"] = bool(press.get("cached") or press.get("retained"))
    posture["retained"] = action["retained"]
    components = [action, delta, posture, market]
    available = [component for component in components if component["available"]]
    denominator = sum(WEIGHTS[component["id"]] for component in available)
    base_score = (
        sum(component["score"] * WEIGHTS[component["id"]] for component in available) / denominator
        if denominator else 0.0
    )
    official_elevated = [component["id"] for component in (action, delta, posture) if component["available"] and component["score"] >= 35]
    market_elevated = market["available"] and market["score"] >= 35
    concurrence_bonus = 5.0 if official_elevated and market_elevated else 0.0
    score = _clamp(base_score + concurrence_bonus)

    source_quality = 0.85 if action.get("retained") else 1.0
    snapshot_quality = 0.85 if delta.get("retained") else 1.0
    market_quality = 0.85 if market.get("retained") else 1.0
    confidence_score = 100 * (
        0.35 * min(1.0, len(releases) / 60) * source_quality
        + 0.30 * min(1.0, delta["current_count"] / 10000) * snapshot_quality
        + 0.10 * int(delta["available"])
        + 0.25 * min(1.0, market["series_available"] / 2) * market_quality
    )
    confidence = "HIGH" if confidence_score >= 75 else "MEDIUM" if confidence_score >= 45 else "LOW"
    reasons = {
        "ofac_action_velocity": "Official designation-linked releases are elevated against prior weekly activity.",
        "sdn_delta_breadth": "The official SDN file changed materially since the previous accepted snapshot.",
        "official_posture_shift": "Coercive language in official OFAC-linked release titles shifted above its recent baseline.",
        "energy_market_dislocation": "Brent, WTI, or their benchmark spread moved unusually against a robust recent baseline.",
    }
    alerts = [
        {"id": component["id"], "title": component["label"], "score": component["score"], "level": _level(component["score"]), "why": reasons[component["id"]]}
        for component in available if component["score"] >= 35
    ]
    alerts.sort(key=lambda row: row["score"], reverse=True)
    history = list((previous_warning or {}).get("history") or [])[-179:]
    if history:
        last = _parse_datetime(history[-1].get("timestamp"))
        if last and timedelta(0) <= now - last < timedelta(hours=1):
            history.pop()
    history.append({
        "timestamp": now.isoformat(), "score": round(score, 1), "level": _level(score),
        "components": {component["id"]: component["score"] for component in components},
    })
    return {
        "issued_at": now.isoformat(),
        "horizon": "0-30 days",
        "classification": "sanctions-expansion-pressure-not-designation-probability",
        "score": round(score, 1),
        "level": _level(score),
        "confidence": confidence,
        "confidence_score": round(confidence_score, 1),
        "components": components,
        "concurrence": {
            "active": bool(concurrence_bonus),
            "official_components": official_elevated,
            "market_component_elevated": market_elevated,
            "score_bonus": concurrence_bonus,
        },
        "alerts": alerts,
        "history": history,
        "data_health": {
            "sdn_entries": delta["current_count"],
            "ofac_releases": len(releases),
            "market_series_available": market["series_available"],
            "available_components": len(available),
            "retained_components": [component["id"] for component in components if component.get("retained")],
        },
        "method": {
            "name": "Sanctions expansion precursor concurrence model v1",
            "aggregation": "availability-renormalized weighted mean; 5-point bonus requires both official and market elevation",
            "weights": WEIGHTS,
            "action_window": "current seven days versus 12 prior non-overlapping weekly OFAC-linked release counts",
            "posture_window": "current seven-day weighted official-title term rate versus up to 12 prior weekly rates",
            "market_window": "five-session Brent, WTI, and Brent-WTI spread changes versus median/MAD baselines",
            "posture_terms": POSTURE_TERMS,
            "warning": "This is public sanctions-expansion pressure, not legal advice, list screening, or a designation probability.",
        },
        "sources": [
            {"name": "OFAC Sanctions List Service", "url": "https://ofac.treasury.gov/sanctions-list-service"},
            {"name": "OFAC-related press releases", "url": "https://ofac.treasury.gov/press-releases"},
            {"name": "FRED Brent crude", "url": "https://fred.stlouisfed.org/series/DCOILBRENTEU"},
            {"name": "FRED WTI crude", "url": "https://fred.stlouisfed.org/series/DCOILWTICO"},
        ],
    }
