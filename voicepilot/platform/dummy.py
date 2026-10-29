"""실제 OS를 건드리지 않는 가짜 조작부.

테스트와 `--dry-run` 실행에서 쓴다. 호출된 동작을 `calls`에 기록한다.
"""

from __future__ import annotations

from dataclasses import replace

from .base import DesktopController, Monitor, PlatformError, Rect, Tab, Window


class DummyController(DesktopController):
    def __init__(self, windows: list[Window] | None = None, monitors: list[Monitor] | None = None):
        self.windows = list(windows) if windows is not None else _sample_windows()
        self.monitors = list(monitors) if monitors is not None else _sample_monitors()
        self.apps = {"Google Chrome", "Safari", "Fork", "Notes"}  # launch_app이 찾을 수 있는 설치된 앱
        self.tabs: dict[int, list] = {}  # 창 id → 탭 목록. 항목은 "제목" 또는 ("제목", "주소") (테스트용)
        self.tabs_error: str | None = None  # 값이 있으면 list_tabs가 이 메시지로 실패한다
        self.calls: list[tuple] = []
        self.cursor: tuple[float, float] = (0.0, 0.0)

    def list_windows(self) -> list[Window]:
        return list(self.windows)

    def list_monitors(self) -> list[Monitor]:
        return list(self.monitors)

    def focus_window(self, window: Window) -> None:
        self.calls.append(("focus_window", window.id))
        # 포커스된 창을 맨 앞으로 옮겨 실제 OS 동작을 흉내 낸다.
        self.windows = [window] + [w for w in self.windows if w.id != window.id]

    def move_cursor(self, x: float, y: float) -> None:
        self.calls.append(("move_cursor", x, y))
        self.cursor = (x, y)

    def list_tabs(self, windows: list[Window]) -> list[Tab]:
        if self.tabs_error:
            raise PlatformError(self.tabs_error)
        tabs = []
        for n, w in enumerate(windows, 1):
            for i, entry in enumerate(self.tabs.get(w.id, []), 1):
                title, url = (entry, "") if isinstance(entry, str) else entry
                tabs.append(Tab(w, i, title, app_window_index=n, url=url))
        return tabs

    def select_tab(self, tab: Tab) -> None:
        self.calls.append(("select_tab", tab.window.id, tab.index))
        # 창의 제목을 새로 선택한 탭 제목으로 바꿔 실제 동작을 흉내 낸다.
        self.windows = [replace(w, title=tab.title) if w.id == tab.window.id else w for w in self.windows]

    def hide_app(self, window: Window) -> None:
        self.calls.append(("hide_app", window.pid))
        self.windows = [w for w in self.windows if w.pid != window.pid]

    def launch_app(self, names: list[str]) -> str:
        self.calls.append(("launch_app", tuple(names)))
        for name in names:
            if name in self.apps:
                return name
        raise PlatformError(f"'{names[0]}' 앱을 찾지 못했습니다.")

    def click(self, button: str = "left", count: int = 1) -> None:
        self.calls.append(("click", button, count))

    def scroll(self, lines: int) -> None:
        self.calls.append(("scroll", lines))


def _sample_monitors() -> list[Monitor]:
    return [
        Monitor(1, Rect(0, 0, 1920, 1080), is_main=True),
        Monitor(2, Rect(1920, 0, 2560, 1440)),
    ]


def _sample_windows() -> list[Window]:
    return [
        Window(101, "Code", "main.py — voicepilot", 11, Rect(100, 100, 1200, 800)),
        Window(102, "Google Chrome", "GitHub", 12, Rect(2000, 100, 1600, 1000)),
        Window(103, "ClaudeBoard", "ClaudeBoard", 13, Rect(2200, 200, 1200, 900)),
    ]
