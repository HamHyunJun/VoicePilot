"""OS 조작부. 실행 중인 OS에 맞는 구현을 고른다."""

from __future__ import annotations

import sys

from .base import DesktopController, Monitor, PlatformError, Rect, Window
from .dummy import DummyController


def create_controller(dry_run: bool = False) -> DesktopController:
    if dry_run:
        return DummyController()
    if sys.platform == "darwin":
        from .macos import MacOSController

        return MacOSController()
    raise PlatformError(f"아직 지원하지 않는 OS입니다: {sys.platform}. `--dry-run`으로 동작을 확인할 수 있습니다.")


__all__ = ["DesktopController", "DummyController", "Monitor", "PlatformError", "Rect", "Window", "create_controller"]
