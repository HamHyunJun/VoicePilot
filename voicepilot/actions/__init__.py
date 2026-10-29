"""인식된 명령을 OS 조작으로 바꾸는 동작 실행부."""

from .executor import ActionExecutor, ActionResult
from .targets import WindowResolver

__all__ = ["ActionExecutor", "ActionResult", "WindowResolver"]
