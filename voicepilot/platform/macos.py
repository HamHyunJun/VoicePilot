"""macOS 조작부 (pyobjc 사용).

필요한 권한 (시스템 설정 → 개인정보 보호 및 보안)
- 손쉬운 사용: 특정 창을 앞으로 가져오기(AXRaise)
- 화면 기록: 다른 앱 창의 제목 읽기. 권한이 없으면 제목이 비어 앱 이름으로만 찾는다.
"""

from __future__ import annotations

import logging
import os

from .base import DesktopController, Monitor, PlatformError, Rect, Window

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
        return windows

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
