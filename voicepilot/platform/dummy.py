"""실제 OS를 건드리지 않는 가짜 조작부.

테스트와 `--dry-run` 실행에서 쓴다. 호출된 동작을 `calls`에 기록한다.
"""

from __future__ import annotations

from .base import DesktopController, Monitor, Rect, Window


class DummyController(DesktopController):
    def __init__(self, windows: list[Window] | None = None, monitors: list[Monitor] | None = None):
        self.windows = list(windows) if windows is not None else _sample_windows()
        self.monitors = list(monitors) if monitors is not None else _sample_monitors()
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
