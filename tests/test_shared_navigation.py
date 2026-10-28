from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shared_navigation_and_local_assets():
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    assert 'class="monarch-shell"' in page
    assert 'href="assets/monarch/design.css"' in page
    assert 'href="https://monarchcastle.com/products/"' in page
    assert (ROOT / "assets/monarch/fonts/IBMPlexSans-Regular.woff2").is_file()
    assert page.index('class="skip-link"') < page.index('class="monarch-shell"')
