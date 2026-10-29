"""macOS 조작부 (pyobjc 사용).

필요한 권한 (시스템 설정 → 개인정보 보호 및 보안)
- 손쉬운 사용: 특정 창을 앞으로 가져오기(AXRaise)
- 화면 기록: 다른 앱 창의 제목 읽기. 권한이 없으면 제목이 비어 앱 이름으로만 찾는다.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import replace

from .base import DesktopController, Monitor, PlatformError, Rect, Tab, Window

log = logging.getLogger(__name__)

try:  # macOS가 아니면 가져오기에 실패한다. 생성 시점에 오류를 알린다.
    import ApplicationServices as AX
    import Quartz
    from AppKit import NSRunningApplication

    _IMPORT_ERROR: Exception | None = None
except ImportError as e:  # pragma: no cover - macOS 전용
    _IMPORT_ERROR = e

# 일반 앱 창이 아닌 시스템 요소
_IGNORED_OWNERS = {"Window Server", "Dock", "Control Center", "Notification Center", "SystemUIServer", "Spotlight"}
_MIN_SIZE = 50
# NSApplicationActivateIgnoringOtherApps
_ACTIVATE_IGNORING_OTHER_APPS = 1 << 1
# AXValue 종류 (pyobjc 상수가 없을 때를 대비한 기본값)
_AX_POINT = 1
_AX_SIZE = 2
_AX_MATCH_TOLERANCE = 8.0  # CG 창과 AX 창의 위치·크기 차이 허용치(px 합)
# 탭을 다룰 수 있는 크롬 계열 브라우저 (CG 창의 앱 이름)
_CHROMIUM_APPS = {"Google Chrome", "Brave Browser", "Microsoft Edge", "Chromium"}
_OSASCRIPT_TIMEOUT = 5.0
# 앱 이름이 아니라 프로세스 번호(pid)로 지정한다. 이름으로 지정하면 헤드리스 크롬처럼 같은 앱의 다른 인스턴스가
# 떠 있을 때 엉뚱한 인스턴스가 응답한다. 창마다 번호, 위치·크기, 탭 제목·주소를 JSON으로 돌려준다.
_LIST_TABS_JS = """
var app = Application(__PID__);
JSON.stringify(app.windows().map(function (w, i) {
    var b = w.bounds();
    return {n: i + 1, x: b.x, y: b.y, w: b.width, h: b.height, titles: w.tabs.title(), urls: w.tabs.url()};
}))
"""
_SELECT_TAB_JS = """
var app = Application(__PID__);
var w = app.windows[__WINDOW__ - 1];
w.activeTabIndex = __TAB__;
w.index = 1;
app.activate();
"""


class MacOSController(DesktopController):  # pragma: no cover - 실기에서만 동작
    def __init__(self) -> None:
        if _IMPORT_ERROR is not None:
            raise PlatformError(
                "pyobjc를 불러오지 못했습니다. macOS에서 `pip install -r requirements.txt`로 설치하세요."
            ) from _IMPORT_ERROR
        if not AX.AXIsProcessTrusted():
            log.warning("손쉬운 사용 권한이 없습니다. 창 포커스가 앱 단위로만 동작할 수 있습니다.")

    # ---- 조회 ----
    def list_windows(self) -> list[Window]:
        options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        infos = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
        own_pid = os.getpid()
        windows: list[Window] = []
        for info in infos:
            if info.get(Quartz.kCGWindowLayer, 0) != 0:
                continue
            owner = str(info.get(Quartz.kCGWindowOwnerName, "") or "")
            pid = int(info.get(Quartz.kCGWindowOwnerPID, 0))
            if owner in _IGNORED_OWNERS or pid == own_pid:
                continue
            b = info.get(Quartz.kCGWindowBounds) or {}
            rect = Rect(float(b.get("X", 0)), float(b.get("Y", 0)), float(b.get("Width", 0)), float(b.get("Height", 0)))
            if rect.width < _MIN_SIZE or rect.height < _MIN_SIZE:
                continue
            windows.append(
                Window(
                    id=int(info.get(Quartz.kCGWindowNumber, 0)),
                    app_name=owner,
                    title=str(info.get(Quartz.kCGWindowName, "") or ""),
                    pid=pid,
                    bounds=rect,
                )
            )
        return self._fill_titles_from_ax(windows)

    def _fill_titles_from_ax(self, windows: list[Window]) -> list[Window]:
        """화면 기록 권한이 없으면 창 제목이 비어 있다. 손쉬운 사용(AX) API로 같은 위치·크기의 창 제목을 채운다.

        CG 창 목록과 AX 창 목록은 둘 다 앞쪽 창부터라서, 위치·크기가 같은 창이 여럿이면 순서대로 짝지운다.
        """
        if not any(not w.title for w in windows) or not AX.AXIsProcessTrusted():
            return windows
        ax_by_pid: dict[int, list[tuple[Rect, str]]] = {}
        result = []
        for w in windows:
            if w.title:
                result.append(w)
                continue
            if w.pid not in ax_by_pid:
                ax_by_pid[w.pid] = self._ax_window_titles(w.pid)
            candidates = ax_by_pid[w.pid]
            for i, (rect, title) in enumerate(candidates):
                moved = abs(rect.x - w.bounds.x) + abs(rect.y - w.bounds.y)
                resized = abs(rect.width - w.bounds.width) + abs(rect.height - w.bounds.height)
                if moved + resized <= _AX_MATCH_TOLERANCE:
                    del candidates[i]  # 같은 AX 창을 두 번 쓰지 않는다
                    w = replace(w, title=title)
                    break
            result.append(w)
        return result

    def _ax_window_titles(self, pid: int) -> list[tuple[Rect, str]]:
        app_el = AX.AXUIElementCreateApplication(pid)
        err, ax_windows = AX.AXUIElementCopyAttributeValue(app_el, AX.kAXWindowsAttribute, None)
        if err or not ax_windows:
            return []
        found = []
        for ax_win in ax_windows:
            pos = self._ax_value(ax_win, AX.kAXPositionAttribute, getattr(AX, "kAXValueCGPointType", _AX_POINT))
            size = self._ax_value(ax_win, AX.kAXSizeAttribute, getattr(AX, "kAXValueCGSizeType", _AX_SIZE))
            err, title = AX.AXUIElementCopyAttributeValue(ax_win, AX.kAXTitleAttribute, None)
            if pos is not None and size is not None and not err and title:
                found.append((Rect(pos.x, pos.y, size.width, size.height), str(title)))
        return found

    def list_tabs(self, windows: list[Window]) -> list[Tab]:
        tabs: list[Tab] = []
        for pid in sorted({w.pid for w in windows if w.app_name in _CHROMIUM_APPS}):
            unused = [w for w in windows if w.pid == pid]  # 같은 위치의 창이 여럿이면 앞쪽부터 순서대로 짝지운다
            script = _LIST_TABS_JS.replace("__PID__", str(pid))
            for info in json.loads(self._osascript(script, unused[0].app_name)):
                for i, w in enumerate(unused):
                    b = w.bounds
                    gap = abs(info["x"] - b.x) + abs(info["y"] - b.y) + abs(info["w"] - b.width) + abs(info["h"] - b.height)
                    if gap <= _AX_MATCH_TOLERANCE:
                        del unused[i]
                        tabs += [Tab(w, n, t, info["n"], u) for n, (t, u) in enumerate(zip(info["titles"], info["urls"]), 1)]
                        break
        return tabs

    def select_tab(self, tab: Tab) -> None:
        if tab.window.app_name not in _CHROMIUM_APPS:
            raise PlatformError(f"'{tab.window.app_name}'의 탭 전환은 지원하지 않습니다.")
        script = (
            _SELECT_TAB_JS.replace("__PID__", str(tab.window.pid))
            .replace("__WINDOW__", str(tab.app_window_index))
            .replace("__TAB__", str(tab.index))
        )
        self._osascript(script, tab.window.app_name)

    @staticmethod
    def _osascript(script: str, app_name: str) -> str:
        try:
            result = subprocess.run(
                ["osascript", "-l", "JavaScript", "-e", script], capture_output=True, text=True, timeout=_OSASCRIPT_TIMEOUT
            )
        except subprocess.TimeoutExpired as e:
            raise PlatformError(f"{app_name}가 응답하지 않습니다.") from e
        if result.returncode != 0:
            if "-1743" in result.stderr:  # errAEEventNotPermitted
                raise PlatformError(
                    f"{app_name} 탭을 읽으려면 시스템 설정 → 개인정보 보호 및 보안 → 자동화에서 허용해 주세요."
                )
            raise PlatformError(f"{app_name} 탭을 다루지 못했습니다: {result.stderr.strip()}")
        return result.stdout

    def list_monitors(self) -> list[Monitor]:
        err, ids, count = Quartz.CGGetActiveDisplayList(16, None, None)
        if err:
            raise PlatformError(f"모니터 목록을 가져오지 못했습니다 (오류 코드 {err}).")
        main_id = Quartz.CGMainDisplayID()
        monitors = []
        for did in list(ids)[:count]:
            r = Quartz.CGDisplayBounds(did)
            monitors.append(
                Monitor(
                    id=int(did),
                    bounds=Rect(r.origin.x, r.origin.y, r.size.width, r.size.height),
                    is_main=(did == main_id),
                )
            )
        return monitors

    # ---- 조작 ----
    def focus_window(self, window: Window) -> None:
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(window.pid)
        if app is None:
            raise PlatformError(f"'{window.app_name}' 프로세스를 찾을 수 없습니다.")
        # 앱 안의 여러 창 중 목표 창을 먼저 올린 뒤 앱을 활성화해야 그 창이 맨 앞에 온다.
        self._raise_ax_window(window)
        app.activateWithOptions_(_ACTIVATE_IGNORING_OTHER_APPS)

    def move_cursor(self, x: float, y: float) -> None:
        point = Quartz.CGPointMake(x, y)
        # 이벤트를 직접 보내야 앱들이 마우스 이동(hover)을 인식한다.
        event = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft)
        if event is not None:
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        Quartz.CGWarpMouseCursorPosition(point)
        Quartz.CGAssociateMouseAndMouseCursorPosition(True)

    def hide_app(self, window: Window) -> None:
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(window.pid)
        if app is None or not app.hide():
            raise PlatformError(f"'{window.app_name}' 앱을 숨기지 못했습니다.")

    def launch_app(self, names: list[str]) -> str:
        for name in names:
            # 말로 들어온 이름이라 경로나 옵션처럼 보이는 값은 시도하지 않는다.
            if "/" in name or name.startswith("-"):
                continue
            # 이미 떠 있는 앱이면 앞으로 가져온다.
            result = subprocess.run(["open", "-a", name], capture_output=True)
            if result.returncode == 0:
                return name
        raise PlatformError(f"'{names[0]}' 앱을 찾지 못했습니다.")

    def click(self, button: str = "left", count: int = 1) -> None:
        if button not in _MOUSE_EVENTS:
            raise PlatformError(f"지원하지 않는 마우스 버튼입니다: {button}")
        down, up, mouse_button = _MOUSE_EVENTS[button]
        pos = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        for click_state in range(1, count + 1):
            for event_type in (down, up):
                event = Quartz.CGEventCreateMouseEvent(None, event_type, pos, mouse_button)
                # 클릭 횟수를 알려 줘야 앱이 더블클릭으로 인식한다.
                Quartz.CGEventSetIntegerValueField(event, Quartz.kCGMouseEventClickState, click_state)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def scroll(self, lines: int) -> None:
        event = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 1, lines)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    # ---- 내부 ----
    def _raise_ax_window(self, window: Window) -> None:
        """손쉬운 사용 API로 같은 위치·크기(또는 같은 제목)의 창을 찾아 AXRaise 한다."""
        app_el = AX.AXUIElementCreateApplication(window.pid)
        err, ax_windows = AX.AXUIElementCopyAttributeValue(app_el, AX.kAXWindowsAttribute, None)
        if err or not ax_windows:
            log.debug("AX 창 목록을 얻지 못함 (오류 %s). 앱 활성화만 합니다.", err)
            return

        best, best_score = None, -1.0
        for ax_win in ax_windows:
            score = 0.0
            pos = self._ax_value(ax_win, AX.kAXPositionAttribute, getattr(AX, "kAXValueCGPointType", _AX_POINT))
            size = self._ax_value(ax_win, AX.kAXSizeAttribute, getattr(AX, "kAXValueCGSizeType", _AX_SIZE))
            if pos is not None and size is not None:
                dist = abs(pos.x - window.bounds.x) + abs(pos.y - window.bounds.y)
                dist += abs(size.width - window.bounds.width) + abs(size.height - window.bounds.height)
                score += max(0.0, 1.0 - dist / 200.0)
            if window.title:
                err, title = AX.AXUIElementCopyAttributeValue(ax_win, AX.kAXTitleAttribute, None)
                if not err and title == window.title:
                    score += 1.0
            if score > best_score:
                best, best_score = ax_win, score

        if best is not None:
            AX.AXUIElementSetAttributeValue(best, AX.kAXMainAttribute, True)
            AX.AXUIElementPerformAction(best, AX.kAXRaiseAction)

    @staticmethod
    def _ax_value(element, attribute, value_type):
        err, value = AX.AXUIElementCopyAttributeValue(element, attribute, None)
        if err or value is None:
            return None
        ok, result = AX.AXValueGetValue(value, value_type, None)
        return result if ok else None
