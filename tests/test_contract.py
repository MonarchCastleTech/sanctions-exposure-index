from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_product_contract():
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8")
    joined = page + script
    for term in ("Early Warning", "Methodology", "OFAC Sanctions List Service", "FRED"):
        assert term in joined
    for fake in ("OpenSanctions", "EU Sanctions", "UN Comtrade"):
        assert fake not in joined
    assert "python -m pytest -q" in workflow
    assert "actions/cache" in workflow
    assert "set -euo pipefail" in workflow
    assert "attempt in 1 2 3 4 5" in workflow
