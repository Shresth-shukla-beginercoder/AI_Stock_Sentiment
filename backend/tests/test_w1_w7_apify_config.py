"""W1/W7: config-driven Apify actor refs, credential aliasing, and the
no-guess run-input construction rule.

Settings is instantiated with ``_env_file=None`` so the test never reads the
owner's real ``.env`` (no credentials enter the test process).
"""

from app.collectors.apify import (
    ActorAvailability,
    build_run_input,
    configured_actors,
    resolve_exchange_actors,
)
from app.core.config import Settings


def test_apify_token_canonical_name_wins_over_legacy_alias():
    both = Settings(_env_file=None, apify_api_token="canon", apify_api_key="legacy")
    assert both.apify_token() == "canon"
    legacy_only = Settings(_env_file=None, apify_api_key="legacy")
    assert legacy_only.apify_token() == "legacy"
    assert Settings(_env_file=None).apify_token() is None


def test_credentials_helpers_treat_apify_honestly():
    none = Settings(_env_file=None)
    assert "APIFY_API_TOKEN" in none.missing_credentials()
    assert "APIFY_API_TOKEN" not in none.configured_credentials()
    # Satisfied via the legacy alias: still reported as configured.
    legacy = Settings(_env_file=None, apify_api_key="x")
    assert "APIFY_API_TOKEN" in legacy.configured_credentials()
    assert "APIFY_API_TOKEN" not in legacy.missing_credentials()


def test_actor_refs_come_from_settings_not_hardcoded_candidates():
    defaults = Settings(_env_file=None)
    # HKEX social platforms: telegram + hkgolden, both canonical IDs by default.
    assert configured_actors(defaults, "HKEX") == [
        ("telegram", "kCdMrRb7UiSRSFYeO"),
        ("hkgolden", "fSZMN7Wfwuye4J8cd"),
    ]
    # KRX social platforms: telegram + naver (Daum is a NEWS source, not here).
    assert configured_actors(defaults, "KRX") == [
        ("telegram", "kCdMrRb7UiSRSFYeO"),
        ("naver", "xxFbG2oX6UpaPtcTC"),
    ]
    # Owner-supplied refs flow through settings (config -> code wiring, W7).
    custom = Settings(_env_file=None, apify_actor_telegram="ns/tg-actor",
                     apify_actor_naver="ns2/naver-actor")
    assert configured_actors(custom, "krx") == [
        ("telegram", "ns/tg-actor"),
        ("naver", "ns2/naver-actor"),
    ]


def test_example_input_empty_query_key_gets_ticker():
    avail = ActorAvailability(
        ref="a/b", platform="telegram", available=True, reason="available",
        example_input={"keyword": "", "limit": 100},
    )
    inp, note = build_run_input(avail, "0700")
    assert inp == {"keyword": "0700", "limit": 100}
    assert "query field" in note


def test_example_input_used_as_is_when_already_set():
    avail = ActorAvailability(
        ref="a/b", platform="telegram", available=True, reason="available",
        example_input={"keyword": "hk stocks"},
    )
    inp, note = build_run_input(avail, "0700")
    assert inp == {"keyword": "hk stocks"}
    assert "query field" not in note


def test_schema_required_string_query_field_filled():
    schema = {
        "properties": {"keyword": {"type": "string"},
                       "limit": {"type": "number", "default": 50}},
        "required": ["keyword"],
    }
    avail = ActorAvailability(ref="a/b", platform="lihkg", available=True,
                              reason="available", input_schema=schema)
    inp, note = build_run_input(avail, "9988")
    assert inp == {"keyword": "9988"}
    assert "required string properties" in note


def test_unfillable_required_input_is_never_guessed():
    """An array-valued required field (e.g. a channel-username list) cannot be
    filled with a ticker -> the input is declared not constructible."""
    schema = {"properties": {"channel_list": {"type": "array"}}, "required": ["channel_list"]}
    avail = ActorAvailability(ref="a/b", platform="telegram", available=True,
                              reason="available", input_schema=schema)
    inp, note = build_run_input(avail, "0700")
    assert inp is None
    assert "channel_list" in note and "not safely constructible" in note


def test_no_example_no_schema_is_not_constructible():
    avail = ActorAvailability(ref="a/b", platform="telegram", available=True,
                              reason="available")
    inp, note = build_run_input(avail, "0700")
    assert inp is None
    assert "not constructible" in note


def test_unconfigured_platforms_are_recorded_not_run():
    class _NoVerify:
        def verify_actor(self, ref, platform=None):
            raise AssertionError("unconfigured actors must not be verified")

    # Empty refs -> honestly recorded as not configured (never verified/run).
    s = Settings(_env_file=None, apify_actor_telegram="", apify_actor_hkgolden="")
    recs = resolve_exchange_actors(s, "HKEX", _NoVerify(), "0700")
    assert [r["platform"] for r in recs] == ["telegram", "hkgolden"]
    for r in recs:
        assert r["configured"] is False
        assert r["available"] is False
        assert r["run_input"] is None
        assert r["reason"] == "not configured"


def test_configured_but_unavailable_actor_records_reason():
    class _Unavailable:
        def verify_actor(self, ref, platform=None):
            return ActorAvailability(ref=ref, platform=platform,
                                     available=False, reason="not found")

    recs = resolve_exchange_actors(Settings(_env_file=None), "HKEX", _Unavailable(), "0700")
    assert len(recs) == 2
    for r in recs:
        assert r["configured"] is True
        assert r["available"] is False
        assert r["run_input"] is None
        assert r["reason"] == "not found"


def test_configured_available_actor_gets_built_run_input():
    class _Available:
        def verify_actor(self, ref, platform=None):
            return ActorAvailability(ref=ref, platform=platform, available=True,
                                     reason="available", example_input={"keyword": ""})

    recs = resolve_exchange_actors(Settings(_env_file=None), "HKEX", _Available(), "0700")
    assert len(recs) == 2
    for r in recs:
        assert r["available"] is True
        assert r["run_input"] == {"keyword": "0700"}
