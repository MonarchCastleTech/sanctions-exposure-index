# -*- coding: utf-8 -*-
"""Shared data fetchers for MCT Intelligence projects."""
import os
import json
import requests
from datetime import datetime, timezone, timedelta

def fetch_nasa_firms(api_key=None, region="world", days=1):
    """Fetch NASA FIRMS fire/thermal anomaly data."""
    key = api_key or os.environ.get("NASA_FIRMS_API_KEY", "")
    if not key:
        return []
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NPP/{region}/{days}"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            lines = r.text.strip().split("\n")
            if len(lines) < 2:
                return []
            headers = lines[0].split(",")
            return [
                dict(zip(headers, line.split(",")))
                for line in lines[1:]
                if line.strip()
            ][:500]
        return []
    except Exception as e:
        print(f"[NASA-FIRMS] Error: {e}")
        return []

def fetch_cisa_kev():
    """Fetch CISA Known Exploited Vulnerabilities catalog."""
    url = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "MCT-Intel/1.0"})
        if r.status_code == 200:
            data = r.json()
            vulns = data.get("vulnerabilities", [])
            return [
                {
                    "cveID": v.get("cveID", ""),
                    "vendorProject": v.get("vendorProject", ""),
                    "product": v.get("product", ""),
                    "vulnerabilityName": v.get("vulnerabilityName", ""),
                    "dateAdded": v.get("dateAdded", ""),
                    "shortDescription": v.get("shortDescription", ""),
                    "dueDate": v.get("requiredAction", ""),
                    "source": "CISA-KEV"
                }
                for v in vulns
            ]
        return []
    except Exception as e:
        print(f"[CISA-KEV] Error: {e}")
        return []

def fetch_acled(*_args, **_kwargs):
    """Disabled until a licensed ACLED key is explicitly configured."""
    return []

def fetch_opensanctions(*_args, **_kwargs):
    """Disabled: current OpenSanctions API requires authenticated access."""
    return {}

def fetch_census_country():
    """Fetch World Bank country indicators (GDP, population)."""
    url = "https://api.worldbank.org/v2/country?format=json&per_page=300"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            data = r.json()
            if len(data) > 1:
                return [
                    {
                        "id": c.get("id", ""),
                        "name": c.get("name", ""),
                        "region": c.get("region", {}).get("value", ""),
                        "capitalCity": c.get("capitalCity", ""),
                        "longitude": c.get("longitude", ""),
                        "latitude": c.get("latitude", ""),
                    }
                    for c in data[1]
                ]
        return []
    except Exception as e:
        print(f"[WorldBank] Error: {e}")
        return []

def fetch_coingecko(coin="bitcoin"):
    """Fetch crypto market data from CoinGecko (free, no key)."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin}"
    try:
        r = requests.get(url, params={"localization": "false", "tickers": "false"}, timeout=30)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"[CoinGecko] Error: {e}")
        return {}

def fetch_exchange_rates(base="USD"):
    """Fetch free exchange rates (no key needed)."""
    url = f"https://api.exchangerate-api.com/v4/latest/{base}"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            data = r.json()
            rates = data.get("rates", {})
            # Return top 20 rates as list of dicts
            return [{"currency": k, "rate": v} for k, v in list(rates.items())[:20]]
        return []
    except Exception as e:
        print(f"[ExchangeRate] Error: {e}")
        return []

def fetch_weather(lat, lon):
    """Fetch free weather from Open-Meteo (no key)."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {"latitude": lat, "longitude": lon, "current": "temperature_2m,wind_speed_10m"}
    try:
        r = requests.get(url, params=params, timeout=30)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"[OpenMeteo] Error: {e}")
        return {}

def fetch_covid_global():
    """Fetch COVID-19 summary data."""
    url = "https://disease.sh/v3/covid-19/countries"
    try:
        r = requests.get(url, timeout=30)
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        print(f"[COVID] Error: {e}")
        return []

def fetch_earthquakes(hours=24):
    """Fetch recent earthquake data from USGS."""
    url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            data = r.json()
            features = data.get("features", [])
            return [
                {
                    "place": f.get("properties", {}).get("place", ""),
                    "mag": f.get("properties", {}).get("mag", 0),
                    "time": f.get("properties", {}).get("time", ""),
                    "lon": f.get("geometry", {}).get("coordinates", [0, 0, 0])[0],
                    "lat": f.get("geometry", {}).get("coordinates", [0, 0, 0])[1],
                    "depth": f.get("geometry", {}).get("coordinates", [0, 0, 0])[2],
                    "source": "USGS"
                }
                for f in features[:200]
            ]
        return []
    except Exception as e:
        print(f"[USGS-Quake] Error: {e}")
        return []

def safe_fetch(fetcher, *args, **kwargs):
    """Wrapper that catches all exceptions and returns empty data."""
    try:
        return fetcher(*args, **kwargs)
    except Exception as e:
        print(f"[SafeFetch] {fetcher.__name__} failed: {e}")
        return {} if not isinstance(args, list) else []

def fetch_google_news_rss(query, max_results=50):
    """Fetch news headlines from Google News RSS."""
    import re
    import urllib.parse
    import xml.etree.ElementTree as ET
    from datetime import datetime, timezone

    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "MCT-Intel/1.0"})
        if r.status_code != 200:
            print(f"[GoogleNews] HTTP {r.status_code}")
            return []
        root = ET.fromstring(r.content)
        items = root.findall(".//item")[:max_results]
        articles = []
        for item in items:
            title = (item.findtext("title") or "").strip()
            link = item.findtext("link") or ""
            pub = item.findtext("pubDate") or ""
            source_el = item.find("source")
            source_name = source_el.text.strip() if source_el is not None and source_el.text else ""
            if source_name and title.endswith(" - " + source_name):
                title = title[: -(len(source_name) + 3)].strip()
            seendate = ""
            for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
                try:
                    dt = datetime.strptime(pub.replace("GMT", "UTC"), fmt)
                    seendate = dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    break
                except ValueError:
                    continue
            if not seendate:
                seendate = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            domain = re.sub(r"[^a-z0-9.-]", "", (source_name or "news.google.com").lower()) or "news.google.com"
            articles.append({
                "title": title,
                "url": link,
                "domain": domain,
                "language": "",
                "tone": 0,
                "seendate": seendate,
                "source": "GoogleNews",
            })
        return articles
    except Exception as e:
        print(f"[GoogleNews] Error: {e}")
        return []
