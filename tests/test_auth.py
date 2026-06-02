import json
import pytest
from pathlib import Path
from boss_job_hunter.auth import save_cookies, load_cookies, COOKIE_PATH


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("boss_job_hunter.auth.COOKIE_PATH", tmp_path / "cookies.json")
    cookies = [{"name": "token", "value": "abc123", "domain": ".zhipin.com"}]
    save_cookies(cookies)
    loaded = load_cookies()
    assert loaded == cookies


def test_load_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("boss_job_hunter.auth.COOKIE_PATH", tmp_path / "missing.json")
    assert load_cookies() is None
