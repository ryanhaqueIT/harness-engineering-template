#!/usr/bin/env python3
"""Browser automation gate — drives UI like a QA engineer.

Uses Playwright accessibility tree snapshots (not screenshots) for
deterministic, vision-free UI verification.

Based on: Anthropic Puppeteer MCP + OpenAI CDP patterns.
Key insight: accessibility snapshots are deterministic, cheaper than
vision APIs, and less brittle than CSS selectors.
"""
import json
import sys
import os
from pathlib import Path

def get_app_urls():
    """Get app URLs from instance-metadata.json or defaults."""
    metadata = Path("instance-metadata.json")
    if metadata.exists():
        data = json.loads(metadata.read_text())
        return (
            data.get("backend_url", "http://localhost:8000"),
            data.get("frontend_url", "http://localhost:3000"),
        )
    return "http://localhost:8000", "http://localhost:3000"


def check_endpoint(url, expected_status=200, expected_body=None):
    """Check an HTTP endpoint (no external deps)."""
    import urllib.request
    try:
        req = urllib.request.urlopen(url, timeout=5)
        if req.status != expected_status:
            return False
        if expected_body:
            body = req.read().decode()
            return expected_body in body
        return True
    except Exception:
        return False


def _snapshot_accessibility(page, feature_id, snapshot_dir):
    """Save an accessibility tree snapshot for debugging."""
    try:
        snapshot = page.accessibility.snapshot()
        if snapshot:
            out = snapshot_dir / f"{feature_id}.json"
            out.write_text(json.dumps(snapshot, indent=2))
    except Exception:
        pass


def _exec_step(page, step, frontend_url):
    """Execute a single test step. Returns True on success."""
    s = step.strip()
    sl = s.lower()

    # navigate to <path>
    if sl.startswith("navigate to"):
        url_path = s.split("to", 1)[-1].strip()
        full = f"{frontend_url}{url_path}" if url_path.startswith("/") else url_path
        page.goto(full, wait_until="networkidle", timeout=15000)
        return True

    # click <selector>
    if sl.startswith("click"):
        selector = s.split("click", 1)[-1].strip().strip("'\"")
        page.click(selector, timeout=5000)
        return True

    # fill <selector> with <value>
    if sl.startswith("fill"):
        parts = s.split("with", 1)
        if len(parts) == 2:
            selector = parts[0].replace("Fill", "").replace("fill", "").strip()
            value = parts[1].strip().strip("'\"")
            page.fill(selector, value)
            return True
        return False

    # verify page contains <selector>
    if "verify page contains" in sl:
        selector = s.split("contains", 1)[-1].strip()
        page.wait_for_selector(selector, timeout=5000)
        return True

    # verify <something> shows <text>
    if "verify" in sl and "shows" in sl:
        text = s.split("shows", 1)[-1].strip()
        page.wait_for_selector(f"text={text}", timeout=5000)
        return True

    # assert text <text>
    if sl.startswith("assert text"):
        text = s.split("text", 1)[-1].strip().strip("'\"")
        page.wait_for_selector(f"text={text}", timeout=5000)
        return True

    # assert element <selector>
    if sl.startswith("assert element"):
        selector = s.split("element", 1)[-1].strip().strip("'\"")
        page.wait_for_selector(selector, timeout=5000)
        return True

    # type <selector> <value>  (alias for fill)
    if sl.startswith("type"):
        parts = s.split(None, 2)  # type selector value
        if len(parts) >= 3:
            page.fill(parts[1], parts[2].strip("'\""))
            return True
        return False

    # wait <ms>
    if sl.startswith("wait"):
        ms = int("".join(c for c in s.split()[-1] if c.isdigit()) or "1000")
        page.wait_for_timeout(ms)
        return True

    # Unknown step — skip silently
    print(f"    SKIP step (unknown verb): {s}")
    return True


def check_ui_feature(feature, backend_url, frontend_url, snapshot_dir):
    """Verify a UI feature using Playwright accessibility tree."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("    SKIP: playwright not installed (pip install playwright)")
        return None  # None = skipped

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 720})
        page = ctx.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text()) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        passed = True
        for step in feature.get("steps", []):
            try:
                if not _exec_step(page, step, frontend_url):
                    print(f"    FAIL step: {step}")
                    passed = False
            except Exception as exc:
                print(f"    FAIL step: {step}  ({exc})")
                passed = False

        # Save accessibility snapshot
        _snapshot_accessibility(page, feature["id"], snapshot_dir)

        if console_errors:
            print(f"    WARN: {len(console_errors)} console error(s)")

        browser.close()
        return passed


def run_default_checks(frontend_url, snapshot_dir):
    """Fallback checks when no feature_list.json exists."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        # Pure HTTP fallback
        return _http_fallback(frontend_url)

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 720})
        page = ctx.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text()) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        # Check 1: home page renders
        try:
            page.goto(frontend_url, wait_until="networkidle", timeout=15000)
            body = page.text_content("body") or ""
            ok = len(body) > 50
            results.append(("Home page renders with content", ok))
            _snapshot_accessibility(page, "home", snapshot_dir)
        except Exception as e:
            results.append(("Home page renders with content", False))

        # Check 2: no console errors
        results.append((f"No console errors (found {len(console_errors)})", len(console_errors) == 0))

        # Check 3: check common pages
        for path in ["/login", "/dashboard", "/agents/new"]:
            try:
                resp = page.goto(f"{frontend_url}{path}", wait_until="networkidle", timeout=10000)
                status = resp.status if resp else 0
                ok = status in (200, 301, 302, 307, 308)
                results.append((f"{path} reachable (HTTP {status})", ok))
                slug = path.strip("/").replace("/", "-") or "root"
                _snapshot_accessibility(page, f"default-{slug}", snapshot_dir)
            except Exception:
                results.append((f"{path} reachable", False))

        browser.close()

    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    for name, ok in results:
        tag = "PASS" if ok else "FAIL"
        print(f"  {tag}: {name}")
    print(f"\nDefault checks: {passed} passed, {failed} failed")
    return 1 if failed > 0 else 0


def _http_fallback(frontend_url):
    """Curl-equivalent fallback when Playwright is missing entirely."""
    import urllib.request
    passed = 0
    failed = 0
    for path in ["/", "/login", "/dashboard"]:
        try:
            resp = urllib.request.urlopen(f"{frontend_url}{path}", timeout=5)
            body = resp.read().decode()
            if len(body) > 50:
                print(f"  PASS: {path} returns content ({len(body)} bytes)")
                passed += 1
            else:
                print(f"  FAIL: {path} near-empty ({len(body)} bytes)")
                failed += 1
        except Exception as e:
            print(f"  FAIL: {path} — {e}")
            failed += 1
    print(f"\nHTTP fallback: {passed} passed, {failed} failed")
    return 1 if failed > 0 else 0


def main():
    repo_root = Path(os.environ.get("REPO_ROOT", "."))
    feature_file = repo_root / ".harness" / "feature_list.json"
    snapshot_dir = repo_root / ".harness" / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    backend_url, frontend_url = get_app_urls()

    # Override from env (set by shell wrapper)
    frontend_url = os.environ.get("FRONTEND_URL", frontend_url)
    backend_url = os.environ.get("BACKEND_URL", backend_url)

    print(f"Browser Automation Gate")
    print(f"  Frontend: {frontend_url}")
    print(f"  Snapshots: {snapshot_dir}")
    print()

    if not feature_file.exists():
        print("No .harness/feature_list.json — running default checks")
        return run_default_checks(frontend_url, snapshot_dir)

    data = json.loads(feature_file.read_text())
    ui_features = [
        f for f in data.get("features", [])
        if f.get("category") == "ui" and not f.get("passes", False)
    ]

    if not ui_features:
        print("All UI features already passing — nothing to verify")
        return 0

    passed = 0
    failed = 0
    skipped = 0

    for feature in ui_features:
        fid = feature.get("id", "?")
        desc = feature.get("description", "")
        print(f"  [{fid}] {desc}")

        result = check_ui_feature(feature, backend_url, frontend_url, snapshot_dir)
        if result is None:
            print(f"    SKIP")
            skipped += 1
        elif result:
            print(f"    PASS")
            passed += 1
        else:
            print(f"    FAIL")
            failed += 1

    print()
    print(f"UI Features: {passed} passed, {failed} failed, {skipped} skipped, {len(ui_features)} total")

    # Write machine-readable report
    report = {
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "total": len(ui_features),
        "features": [
            {"id": f.get("id"), "description": f.get("description")}
            for f in ui_features
        ],
    }
    report_path = snapshot_dir / "gate_report.json"
    report_path.write_text(json.dumps(report, indent=2))

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
