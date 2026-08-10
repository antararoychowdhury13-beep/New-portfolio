"""A4 runtime · Browser interaction — the synthetic user's hands.

Executes ``models.Action`` objects against a real page via Playwright and
captures what the participant would see: a viewport-only screenshot per
step (never full-page — the perception contract forbids knowledge below
the fold) plus the telemetry the scoring engine consumes.

The synthetic user's mind never touches this module directly: it emits an
Action (click "Billing"), this layer performs it, and the perception layer
turns the resulting screenshot back into words. The DOM stays sealed inside
this file — targets are located by their VISIBLE TEXT only, the same way a
human finds them.

Requires the ``live`` extra (``pip install -e ".[live]"``) and a Chromium
Playwright can launch (``PLAYWRIGHT_BROWSERS_PATH`` or ``executable_path``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from .models import Action

DEFAULT_VIEWPORT = (390, 780)  # mobile-first, matches the fixture app


class BrowserError(RuntimeError):
    """Raised when the browser layer cannot start or act."""


@dataclass
class StepResult:
    """What observably happened after one action — telemetry, not judgement."""
    ok: bool
    screen_id: str                      # where the participant ended up
    screen_changed: bool
    screenshot: str                     # path to the viewport capture
    note: str = ""                      # e.g. "target not found" (a misclick)


@dataclass
class BrowserSession:
    """One participant's browser. One session per participant — no shared
    state between synthetic users, ever."""
    start_url: str
    shot_dir: str | Path
    viewport: tuple[int, int] = DEFAULT_VIEWPORT
    executable_path: str | None = None
    _pw: object = field(default=None, repr=False)
    _browser: object = field(default=None, repr=False)
    _page: object = field(default=None, repr=False)
    _shot_count: int = 0

    # ------------------------------------------------------------ lifecycle

    def __enter__(self) -> "BrowserSession":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserError(
                'Playwright is not installed. Run: pip install -e ".[live]" '
                "then ensure a Chromium build is available."
            ) from exc
        self._pw = sync_playwright().start()
        launch_kwargs = {}
        if self.executable_path:
            launch_kwargs["executable_path"] = self.executable_path
        self._browser = self._pw.chromium.launch(**launch_kwargs)
        self._page = self._browser.new_page(
            viewport={"width": self.viewport[0], "height": self.viewport[1]}
        )
        Path(self.shot_dir).mkdir(parents=True, exist_ok=True)
        self._page.goto(self.start_url)
        self._page.wait_for_load_state()
        return self

    def __exit__(self, *exc) -> None:
        for closer in (self._browser, self._pw):
            try:
                if closer is not None:
                    closer.close() if closer is self._browser else closer.stop()
            except Exception:
                pass

    # ------------------------------------------------------------ observing

    def screen_id(self) -> str:
        """Stable screen identity: the page <title> if set, else the URL
        path stem. Fixture pages title themselves with their screen id."""
        title = (self._page.title() or "").strip()
        if title:
            return title.lower().replace(" ", "_")
        stem = Path(urlparse(self._page.url).path).stem
        return stem or "start"

    def capture(self) -> str:
        """Viewport-only screenshot — what the participant can currently see."""
        self._shot_count += 1
        path = Path(self.shot_dir) / f"{self._shot_count:03d}_{self.screen_id()}.png"
        self._page.screenshot(path=str(path), full_page=False)
        return str(path)

    # -------------------------------------------------------------- acting

    def act(self, action: Action) -> StepResult:
        before = self.screen_id()
        note = ""
        try:
            if action.type == "click":
                note = self._click_visible_text(action.target_label or "")
            elif action.type == "scroll":
                self._page.mouse.wheel(0, int(self.viewport[1] * 0.8))
            elif action.type == "back":
                self._page.go_back()
            elif action.type == "type":
                note = self._type_into(action.target_label or "", action.value or "")
            elif action.type in ("open_help", "give_up", "declare_done"):
                # Cognitive outcomes, not browser gestures. open_help is a
                # click on visible help affordances if any exist.
                if action.type == "open_help":
                    note = self._click_visible_text("help")
            else:
                note = f"unknown action type: {action.type}"
        except Exception as exc:  # a failed gesture is telemetry, not a crash
            note = f"action failed: {type(exc).__name__}: {exc}"
        self._page.wait_for_load_state()
        after = self.screen_id()
        return StepResult(
            ok=not note,
            screen_id=after,
            screen_changed=after != before,
            screenshot=self.capture(),
            note=note,
        )

    def _click_visible_text(self, label: str) -> str:
        """Click the element a human would identify by this visible text.
        Case-insensitive substring match, first visible hit wins — the same
        imprecision a real finger has. Returns '' on success, a note if not."""
        if not label:
            return "click with no target label"
        locator = self._page.get_by_text(label, exact=False).first
        try:
            locator.wait_for(state="visible", timeout=2000)
        except Exception:
            return f"target not found: {label!r}"
        # Click the nearest actionable ancestor so hitting a row's text works.
        target = locator.locator(
            "xpath=ancestor-or-self::*[self::a or self::button][1]"
        )
        (target if target.count() > 0 else locator).first.click(timeout=2000)
        return ""

    def _type_into(self, label: str, value: str) -> str:
        locator = self._page.get_by_placeholder(label).or_(
            self._page.get_by_label(label)
        ).first
        try:
            locator.wait_for(state="visible", timeout=2000)
        except Exception:
            return f"field not found: {label!r}"
        locator.fill(value)
        return ""
