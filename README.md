# Sanctions Exposure Index

Autonomous public-data early warning for sanctions-expansion pressure over a 0–30 day horizon. This is not legal advice, list screening, or an entity-designation probability.

## Reproducible model

The score combines four predeclared components: OFAC action velocity (35%), exact SDN-list delta breadth (20%), official posture-language shift (25%), and Brent/WTI market dislocation (20%). Missing components are excluded and remaining weights are renormalized. A five-point concurrence bonus requires both an elevated official component and the independent energy-market component.

Inputs come from the official OFAC Sanctions List Service, Treasury/OFAC-linked press releases, and public FRED Brent/WTI series. Robust baselines use medians and median absolute deviations rather than fitted black-box parameters.

## Autonomous operation

GitHub Actions runs every six hours, tests code before refresh, caches upstream snapshots for at most 72 hours, preserves the last-good output on total official-source failure, commits accepted source/model output, and deploys GitHub Pages. All formulae, evidence, source URLs, component scores, and history are published in `data/output.json`.

Run locally:

`python -m pip install -r requirements.txt`

`python -m pytest -q`

`python pipeline/sanctions_exposure_index_pipeline.py`

[![Pages](https://github.com/MonarchCastleTech/sanctions-exposure-index/actions/workflows/pipeline.yml/badge.svg)](https://github.com/MonarchCastleTech/sanctions-exposure-index/actions/workflows/pipeline.yml)

Entity and network signals for sanctions exposure monitoring.

**Live dashboard:** https://monarchcastletech.github.io/sanctions-exposure-index/

## Run locally

```bash
python -m pip install -r requirements.txt
python pipeline/sanctions_exposure_index_pipeline.py
python -m http.server 8000
```

Open `http://localhost:8000`. Direct `file://` access cannot fetch `data/output.json` in modern browsers.

## Automation

GitHub Actions refreshes public data every six hours and deploys the static dashboard to GitHub Pages. AI briefs are optional: configure `OPENROUTER_API_KEY` as a repository Actions secret. Without it, core collection and dashboard deployment remain available.

## Data notice

Source availability varies. The dashboard identifies its generation time and operating mode in `data/output.json`. Treat indicators as decision-support signals, not verified ground truth.

## Brand

Part of Monarch Castle Technologies. See [BRAND.md](BRAND.md) for approved asset use.
