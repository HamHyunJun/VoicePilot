"""동작 실행기.

명령 사전의 `action` 이름을 처리 함수에 연결한다. 처리 함수는 OS 조작부 인터페이스만 사용한다.
새 동작은 `@executor.register("이름")` 또는 `ActionExecutor.register()`로 추가한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from ..commands.matcher import Intent
from ..platform.base import DesktopController, PlatformError, Tab, Window
from .targets import WindowResolver, monitor_of_point, resolve_monitor, sort_monitors, topmost_window_on

log = logging.getLogger(__name__)

_SCROLL_LINES = 10  # "스크롤 내려" 한 번에 움직일 줄 수


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


def _scoped_windows(ex: ActionExecutor, args: dict[str, Any], windows: list[Window]) -> tuple[list[Window], str]:
    """`position`/`index`가 있으면 그 모니터에 있는 창만 돌려준다. 두 번째 값은 실패 메시지에 붙일 안내 문구."""
    position, index = args.get("position"), args.get("index")
    if not (position or index):
        return windows, ""
    monitor = resolve_monitor(
        ex.controller.list_monitors(),
        position=str(position) if position else None,
        index=int(index) if index else None,
    )
    if monitor is None:
        raise PlatformError("해당 모니터를 찾지 못했습니다.")
    return [w for w in windows if monitor.bounds.contains(*w.bounds.center)], "그 모니터에서 "


def _find_tab(ex: ActionExecutor, target: str, windows: list[Window]) -> tuple[Tab | None, str]:
    """창 제목에서 못 찾은 이름을 브라우저 탭 제목·주소에서 찾는다. 두 번째 값은 못 읽었을 때 붙일 안내 문구."""
    try:
        tabs = ex.controller.list_tabs(windows)
    except PlatformError as e:
        return None, f" ({e})"
    # 제목과 주소를 한 목록에 번갈아 넣어 찾는다. ("깃허브" → 제목이 달라도 주소에 github.com이 있으면 찾음)
    index = ex.resolver.best_title(target, [text for t in tabs for text in (t.title, t.url)])
    return (tabs[index // 2] if index is not None else None), ""


def _focus_window(ex: ActionExecutor, args: dict[str, Any]) -> ActionResult:
    target = str(args.get("target", "")).strip()
    if not target:
        return ActionResult(False, "어떤 창으로 갈지 알아듣지 못했습니다.")
    all_windows = ex.controller.list_windows()
    windows, where = _scoped_windows(ex, args, all_windows)
    app = str(args.get("app", "")).strip()
    if app:
        # "크롬 화면에서 npm 열어줘": 먼저 앱을 정하고, 그 앱의 창들 중에서 제목으로 target을 찾는다.
        app_window = ex.resolver.resolve(app, windows)
        if app_window is None:
            return ActionResult(False, f"{where}'{app}' 창을 찾지 못했습니다.")
        windows = [w for w in windows if w.pid == app_window.pid]
    window = ex.resolver.resolve(target, windows, titles_only=bool(app))  # 앱을 정했으면 제목만 본다
    tab_hint = ""
    if window is None:
        # 가려진 탭일 수 있으니 브라우저 탭 제목도 찾아본다.
        tab, tab_hint = _find_tab(ex, target, windows)
        if tab is not None:
            ex.controller.select_tab(tab)  # 창도 함께 맨 앞으로 가져온다
            ex.controller.move_cursor(*tab.window.bounds.center)
            return ActionResult(True, f"{tab.title} 탭으로 이동했습니다.")
    if window is None and app:
        hint = " 창 제목을 읽지 못했습니다. 손쉬운 사용 권한을 확인하세요." if not any(w.title for w in windows) else ""
        return ActionResult(False, f"{where}'{app}' 창 중에 '{target}'을(를) 찾지 못했습니다.{hint}{tab_hint}")
    if window is None:
        # 어느 모니터에도 창이 없으면 꺼진 앱으로 보고 실행한다. 다른 모니터에 창이 있으면 실행하지 않는다.
        if args.get("launch_if_missing") and ex.resolver.resolve(target, all_windows) is None:
            try:
                result = _launch_app(ex, args)
            except PlatformError:
                return ActionResult(False, f"'{target}' 창도 앱도 찾지 못했습니다.{tab_hint}")
            # 앱이 열리는 모니터는 macOS가 정한다. 지정한 모니터로 옮겨 주지는 못한다.
            return ActionResult(True, result.message + (" (모니터 위치는 지정할 수 없어요)" if where else ""))
        return ActionResult(False, f"{where}'{target}' 창을 찾지 못했습니다.{tab_hint}")
    ex.controller.focus_window(window)
    ex.controller.move_cursor(*window.bounds.center)
    label = window.title or window.app_name
    return ActionResult(True, f"{label} 창으로 이동했습니다.")


def _hide_window(ex: ActionExecutor, args: dict[str, Any]) -> ActionResult:
    target = str(args.get("target", "")).strip()
    if not target:
        return ActionResult(False, "어떤 창을 숨길지 알아듣지 못했습니다.")
    windows, where = _scoped_windows(ex, args, ex.controller.list_windows())
    window = ex.resolver.resolve(target, windows)
    if window is None:
        return ActionResult(False, f"{where}'{target}' 창을 찾지 못했습니다.")
    ex.controller.hide_app(window)
    return ActionResult(True, f"{window.app_name} 앱을 숨겼습니다.")


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


def _launch_app(ex: ActionExecutor, args: dict[str, Any]) -> ActionResult:
    target = str(args.get("target", "")).strip()
    if not target:
        return ActionResult(False, "어떤 앱을 실행할지 알아듣지 못했습니다.")
    # 별칭으로 얻은 실제 앱 이름을 먼저, 말한 이름 그대로는 마지막에 시도한다.
    names = sorted(ex.resolver.candidates_for(target), key=lambda n: (n == target, -len(n)))
    launched = ex.controller.launch_app(names)
    return ActionResult(True, f"{launched} 앱을 실행했습니다.")


def _click(ex: ActionExecutor, args: dict[str, Any]) -> ActionResult:
    button = str(args.get("button", "left"))
    count = int(args.get("count", 1))
    ex.controller.click(button, count)
    name = {"left": "왼쪽", "right": "오른쪽"}.get(button, button)
    return ActionResult(True, f"{name} 버튼을 {'더블' if count == 2 else ''}클릭했습니다.")


def _scroll(ex: ActionExecutor, args: dict[str, Any]) -> ActionResult:
    direction = args.get("direction")
    if direction not in ("up", "down"):
        return ActionResult(False, "스크롤 방향을 알아듣지 못했습니다.")
    lines = int(args.get("lines", _SCROLL_LINES))
    ex.controller.scroll(lines if direction == "up" else -lines)
    return ActionResult(True, "위로 스크롤했습니다." if direction == "up" else "아래로 스크롤했습니다.")


_DEFAULT_HANDLERS: dict[str, Handler] = {
    "focus_window": _focus_window,
    "focus_monitor": _focus_monitor,
    "hide_window": _hide_window,
    "launch_app": _launch_app,
    "click": _click,
    "scroll": _scroll,
}
