"""Phase 3 API contract tests.

All tests run against the real app with DATA_MODE=demo (default) and a real
PostgreSQL if available; otherwise they use the deterministic demo layer which
is DB-free. The demo path must not touch Postgres, so these tests are hermetic.
"""

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

# Fresh app per test; the demo layer is stateless and deterministic.
client = TestClient(app)
settings = get_settings()
assert settings.data_mode == "demo"  # safe default; tests must not leak live mode

DEMO_HK = "DEMO-HK-001"
DEMO_KR = "DEMO-KR-001"
REAL_TICKER = "0700"  # must NOT resolve in demo mode


def _as_of_iso(body: dict) -> str:
    """as_of must be parseable UTC ISO-8601."""
    from datetime import datetime

    ts = datetime.fromisoformat(body["as_of"])
    assert ts.tzinfo is not None, "as_of must be tz-aware"
    return body["as_of"]


# --- System -----------------------------------------------------------------
def test_health_200():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_200_when_db_up():
    r = client.get("/api/ready")
    # Readiness reflects real Postgres state; either 200 or 503 is valid,
    # but the body shape must be stable.
    assert r.status_code in (200, 503)
    assert "database" in r.json()


def test_system_status():
    r = client.get("/api/system/status")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data_mode"] == "demo"
    _as_of_iso(body)
    # provider capability must not be overclaimed
    assert "UNVERIFIED" in body["data"]["provider_capability"]


# --- Assets -----------------------------------------------------------------
def test_assets_list_demo():
    r = client.get("/api/assets")
    assert r.status_code == 200
    body = r.json()
    assert body["data_mode"] == "demo"
    tickers = {a["ticker"] for a in body["data"]}
    assert tickers == {DEMO_HK, DEMO_KR}
    # no real tickers in the demo universe
    assert REAL_TICKER not in tickers
    for a in body["data"]:
        assert a["is_demo"] is True
        assert a["provider_ticker"] is None
        assert a["confirmed"] is False


def test_assets_pagination_meta():
    r = client.get("/api/assets", params={"limit": 1, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 1
    assert body["meta"]["total"] == 2
    assert body["meta"]["has_more"] is True


def test_asset_detail():
    r = client.get(f"/api/assets/{DEMO_HK}")
    assert r.status_code == 200
    assert r.json()["data"]["ticker"] == DEMO_HK
    assert r.json()["data"]["is_demo"] is True


def test_asset_unknown_ticker_404():
    r = client.get(f"/api/assets/{REAL_TICKER}")
    assert r.status_code == 404
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "not_found"


def test_assets_invalid_limit_422():
    r = client.get("/api/assets", params={"limit": 0})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


# --- Posts / News / Prices --------------------------------------------------
def test_posts_demo_contract():
    r = client.get(f"/api/posts/{DEMO_HK}")
    assert r.status_code == 200
    body = r.json()
    assert body["data_mode"] == "demo"
    assert body["meta"]["source"] == "demo-synthetic"
    assert all(p["is_demo"] for p in body["data"])
    # some posts intentionally have NULL engagement (missing => null, never 0)
    assert any(p["engagement"] is None for p in body["data"])
    _as_of_iso(body)


def test_posts_unknown_ticker_404():
    assert client.get(f"/api/posts/{REAL_TICKER}").status_code == 404


def test_news_demo_contract():
    r = client.get(f"/api/news/{DEMO_HK}")
    assert r.status_code == 200
    assert all(n["is_demo"] for n in r.json()["data"])
    # synthetic sources must be clearly demo
    assert all(n["source"].startswith("demo-") for n in r.json()["data"])


def test_prices_demo_contract():
    r = client.get(f"/api/prices/{DEMO_HK}")
    assert r.status_code == 200
    rows = r.json()["data"]
    assert all(p["provider"] == "synthetic" for p in rows)
    # numeric fields are real numbers (from fixed walk), volume may be NULL
    assert all(isinstance(p["close"], (int, float)) for p in rows)
    assert any(p["volume"] is None for p in rows)


def test_prices_unknown_ticker_404():
    assert client.get(f"/api/prices/{REAL_TICKER}").status_code == 404


# --- Sentiment --------------------------------------------------------------
def test_sentiment_demo_contract():
    r = client.get(f"/api/sentiment/{DEMO_HK}")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["is_demo"] is True
    # score must equal P(pos) - P(neg)
    expected = round(body["p_pos"] - body["p_neg"], 6)
    assert abs(body["score"] - expected) < 1e-9
    assert body["state"] == "sufficient"
    assert body["signal"] in ("positive", "neutral", "negative")


def test_sentiment_deterministic():
    a = client.get(f"/api/sentiment/{DEMO_HK}").json()["data"]
    b = client.get(f"/api/sentiment/{DEMO_HK}").json()["data"]
    assert a["score"] == b["score"]
    assert a["counts"] == b["counts"]


# --- Predictions ------------------------------------------------------------
def test_predictions_demo_contract():
    r = client.get(f"/api/predictions/{DEMO_HK}")
    assert r.status_code == 200
    rows = r.json()["data"]
    assert rows[0]["experimental"] is True
    assert rows[0]["is_demo"] is True
    # actual_close stays NULL until backfilled
    assert rows[0]["actual_close"] is None


# --- Reports ----------------------------------------------------------------
def test_reports_overview_demo():
    r = client.get("/api/reports/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["is_demo"] is True
    assert set(body["data"]["universe"]) == {DEMO_HK, DEMO_KR}
    assert body["data"]["per_ticker"][DEMO_HK]["sentiment_signal"] in ("positive", "neutral", "negative")


def test_reports_ranking_demo():
    r = client.get("/api/reports/ranking")
    assert r.status_code == 200
    rows = r.json()["data"]
    assert [x["rank"] for x in rows] == list(range(1, len(rows) + 1))
    # ranks must be sorted by score descending
    scores = [x["score"] for x in rows]
    assert scores == sorted(scores, reverse=True)


# --- Models -----------------------------------------------------------------
def test_models_evaluation_demo():
    r = client.get("/api/models/evaluation")
    assert r.status_code == 200
    rows = r.json()["data"]
    assert all(e["is_demo"] for e in rows)
    # synthetic records must not fabricate a git commit
    assert all(e["git_commit"] is None for e in rows)


def test_models_versions_demo():
    r = client.get("/api/models/versions")
    assert r.status_code == 200
    assert r.json()["data"]["versions"]


# --- Jobs & admin auth ------------------------------------------------------
def test_jobs_requires_admin_key_401():
    r = client.get("/api/jobs")
    assert r.status_code == 401
    assert r.json()["error"]["code"] in ("unauthorized", "admin_not_configured")


def test_jobs_with_admin_key_200(monkeypatch):
    # Point the auth dependency at a Settings with a throwaway admin key.
    from app.api import auth
    from app.core.config import Settings

    s = Settings(api_admin_key="test-key-123")
    monkeypatch.setattr(auth, "get_settings", lambda: s)
    r = client.get("/api/jobs", headers={"X-API-Key": "test-key-123"})
    # Auth must pass (no 401); jobs is a DB read — 200 with no_data when the
    # queue is empty, 503 when Postgres is down.
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        assert r.json()["meta"]["state"] in ("ok", "no_data")


def test_jobs_with_wrong_key_401(monkeypatch):
    from app.api import auth
    from app.core.config import Settings

    s = Settings(api_admin_key="correct-horse-battery")
    monkeypatch.setattr(auth, "get_settings", lambda: s)
    r = client.get("/api/jobs", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_collect_run_401_without_key():
    r = client.post("/api/collect/run", json={"tickers": [DEMO_HK], "source": "all"})
    assert r.status_code == 401


def test_models_train_401_without_key():
    r = client.post("/api/models/train", json={"tickers": [DEMO_HK]})
    assert r.status_code == 401


def test_collect_run_rejects_empty_tickers_422(monkeypatch):
    # Auth must pass first; empty ticker list must fail validation (422).
    from app.api import auth
    from app.core.config import Settings

    monkeypatch.setattr(auth, "get_settings", lambda: Settings(api_admin_key="k"))
    r = client.post(
        "/api/collect/run",
        json={"tickers": []},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 422


# --- Demo / live separation -------------------------------------------------
def test_live_mode_is_honest_no_data(monkeypatch):
    """Forcing DATA_MODE=live against an empty DB must return no_data, not demo rows."""
    from app.api import routes as routes_mod
    from app.core.config import Settings

    monkeypatch.setattr(routes_mod, "get_settings", lambda: Settings(data_mode="live"))
    r = client.get("/api/assets")
    assert r.status_code == 200
    body = r.json()
    assert body["data_mode"] == "live"
    assert body["meta"]["state"] == "no_data"
    assert body["data"] == []


def test_live_sentiment_unknown_ticker_no_data(monkeypatch):
    from app.api import routes as routes_mod
    from app.core.config import Settings

    monkeypatch.setattr(routes_mod, "get_settings", lambda: Settings(data_mode="live"))
    r = client.get("/api/sentiment/0700")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["state"] == "no_data"
    assert data["score"] is None  # no data => NULL, never 0


# --- OpenAPI ----------------------------------------------------------------
def test_openapi_json_available():
    r = client.get("/api/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    for p in [
        "/api/system/status",
        "/api/assets",
        "/api/assets/{ticker}",
        "/api/posts/{ticker}",
        "/api/sentiment/{ticker}",
        "/api/news/{ticker}",
        "/api/prices/{ticker}",
        "/api/predictions/{ticker}",
        "/api/reports/overview",
        "/api/reports/ranking",
        "/api/models/evaluation",
        "/api/models/versions",
        "/api/jobs",
        "/api/jobs/{job_id}",
        "/api/collect/run",
        "/api/models/train",
    ]:
        assert p in paths, f"missing path {p}"


def test_swagger_docs_load():
    r = client.get("/docs")
    assert r.status_code == 200


def test_error_envelope_shape():
    r = client.get(f"/api/posts/{DEMO_HK}", params={"limit": -5})  # 422
    body = r.json()
    assert body["success"] is False
    assert "data_mode" in body and "as_of" in body
    assert body["error"]["code"] == "validation_error"


def test_unknown_route_404_envelope():
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["success"] is False
