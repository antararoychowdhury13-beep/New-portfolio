"""Tests for the browser interaction layer, driven against the fixture app.

These run a real (headless) Chromium. They skip cleanly when Playwright or
a browser build is unavailable, so the core suite stays green everywhere.
"""
import os
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from synthux.browser import BrowserSession  # noqa: E402
from synthux.models import Action  # noqa: E402

APP = Path(__file__).parent / "fixtures" / "app"
START = f"file://{APP}/home.html"
CHROMIUM = os.environ.get("SYNTHUX_CHROMIUM", "/opt/pw-browsers/chromium")


@pytest.fixture()
def session(tmp_path):
    exe = CHROMIUM if Path(CHROMIUM).exists() else None
    try:
        with BrowserSession(START, tmp_path / "shots", executable_path=exe) as s:
            yield s
    except Exception as exc:  # no usable browser in this environment
        pytest.skip(f"no launchable Chromium: {exc}")


def test_optimal_path_reaches_confirmation(session):
    """The happy path: Billing → Payment methods → Manage mandate → Switch."""
    assert session.screen_id() == "home"
    path = ["Billing", "Payment methods", "Manage mandate", "Switch to direct debit"]
    for label in path:
        result = session.act(Action(type="click", target_label=label))
        assert result.ok, result.note
        assert result.screen_changed
    assert session.screen_id() == "dd_confirm"


def test_wrong_turn_and_back(session):
    """The Priya path: Account first, realise, go back."""
    r = session.act(Action(type="click", target_label="Account"))
    assert r.screen_id == "account"
    r = session.act(Action(type="back"))
    assert r.screen_id == "home"
    assert r.screen_changed


def test_misclick_is_telemetry_not_crash(session):
    """Clicking a label that doesn't exist reports a note; nothing raises."""
    r = session.act(Action(type="click", target_label="Change payment method"))
    assert not r.ok
    assert "not found" in r.note
    assert r.screen_id == "home"
    assert not r.screen_changed


def test_screenshots_are_viewport_only(session):
    """Every act() captures what the participant can see, named by step."""
    r1 = session.act(Action(type="click", target_label="Billing"))
    r2 = session.act(Action(type="click", target_label="Payment methods"))
    for r in (r1, r2):
        assert Path(r.screenshot).exists()
        assert Path(r.screenshot).stat().st_size > 5000
    assert "002_" in Path(r2.screenshot).name or "003_" in Path(r2.screenshot).name


def test_help_route_documents_the_trap(session):
    """Help names 'Manage mandate' — the recovery path the simulation uses."""
    session.act(Action(type="click", target_label="Help"))
    assert session.screen_id() == "help"
    r = session.act(Action(type="click", target_label="Set up automatic payment"))
    assert r.screen_id == "payment_methods"
