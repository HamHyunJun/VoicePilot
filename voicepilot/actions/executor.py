"""동작 실행기.

명령 사전의 `action` 이름을 처리 함수에 연결한다. 처리 함수는 OS 조작부 인터페이스만 사용한다.
새 동작은 `@executor.register("이름")` 또는 `ActionExecutor.register()`로 추가한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from ..commands.matcher import Intent
from ..platform.base import DesktopController, PlatformError
from .targets import WindowResolver, monitor_of_point, resolve_monitor, sort_monitors, topmost_window_on

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str


Handler = Callable[["ActionExecutor", dict[str, Any]], ActionResult]


class ActionExecutor:
    def __init__(self, controller: DesktopController, resolver: WindowResolver | None = None):
        self.controller = controller
        self.resolver = resolver or WindowResolver()
        self._handlers: dict[str, Handler] = dict(_DEFAULT_HANDLERS)

    def register(self, name: str, handler: Handler) -> None:
        self._handlers[name] = handler

    @property
    def actions(self) -> list[str]:
        return sorted(self._handlers)

    def execute(self, intent: Intent) -> ActionResult:
        handler = self._handlers.get(intent.action)
        if handler is None:
            return ActionResult(False, f"아직 지원하지 않는 동작입니다: {intent.action}")
        try:
            return handler(self, intent.args)
        except PlatformError as e:
            log.exception("동작 실행 실패")
            return ActionResult(False, str(e))


def _focus_window(ex: ActionExecutor, args: dict[str, Any]) -> ActionResult:
    target = str(args.get("target", "")).strip()
    if not target:
        return ActionResult(False, "어떤 창으로 갈지 알아듣지 못했습니다.")
    window = ex.resolver.resolve(target, ex.controller.list_windows())
    if window is None:
        return ActionResult(False, f"'{target}' 창을 찾지 못했습니다.")
    ex.controller.focus_window(window)
    ex.controller.move_cursor(*window.bounds.center)
    label = window.title or window.app_name
    return ActionResult(True, f"{label} 창으로 이동했습니다.")


def _focus_monitor(ex: ActionExecutor, args: dict[str, Any]) -> ActionResult:
    monitors = ex.controller.list_monitors()
    windows = ex.controller.list_windows()

    # "다음 화면"을 위해 지금 맨 앞 창이 있는 모니터를 현재 모니터로 본다.
    current = None
    if windows:
        current = monitor_of_point(monitors, *windows[0].bounds.center)

    index = args.get("index")
    monitor = resolve_monitor(
        monitors,
        position=args.get("position"),
        index=int(index) if index is not None else None,
        current=current,
    )
    if monitor is None:
        return ActionResult(False, "해당 모니터를 찾지 못했습니다.")

    window = topmost_window_on(monitor, windows)
    if window is not None:
        ex.controller.focus_window(window)
    ex.controller.move_cursor(*monitor.bounds.center)
    number = sort_monitors(monitors).index(monitor) + 1
    return ActionResult(True, f"{number}번 모니터로 이동했습니다.")


_DEFAULT_HANDLERS: dict[str, Handler] = {
    "focus_window": _focus_window,
    "focus_monitor": _focus_monitor,
}
