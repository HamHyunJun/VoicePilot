"""OS 조작부 인터페이스.

명령 인식부는 이 파일의 타입과 `DesktopController`만 사용한다.
새 OS를 지원하려면 `DesktopController`를 구현한 클래스를 만들고 `platform/__init__.py`에 등록하면 된다.

좌표계: 주 모니터의 왼쪽 위가 (0, 0)이고 x는 오른쪽, y는 아래쪽으로 커지는 전역 좌표를 쓴다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height


@dataclass(frozen=True)
class Window:
    """화면에 보이는 창 하나. `id`는 OS가 준 창 식별자다."""

    id: int
    app_name: str
    title: str
    pid: int
    bounds: Rect


@dataclass(frozen=True)
class Monitor:
    id: int
    bounds: Rect
    is_main: bool = False


class PlatformError(RuntimeError):
    """OS 조작 중 발생한 오류 (권한 부족 등)."""


class DesktopController(ABC):
    @abstractmethod
    def list_windows(self) -> list[Window]:
        """보이는 일반 창 목록을 앞쪽(최근에 포커스된) 창부터 돌려준다."""

    @abstractmethod
    def list_monitors(self) -> list[Monitor]:
        """연결된 모니터 목록."""

    @abstractmethod
    def focus_window(self, window: Window) -> None:
        """창을 맨 앞으로 가져오고 키보드 포커스를 준다."""

    @abstractmethod
    def move_cursor(self, x: float, y: float) -> None:
        """마우스 커서를 전역 좌표 (x, y)로 옮긴다."""

    @abstractmethod
    def click(self, button: str = "left", count: int = 1) -> None:
        """현재 커서 위치를 클릭한다. button은 "left"/"right", count=2면 더블클릭."""

    @abstractmethod
    def scroll(self, lines: int) -> None:
        """현재 커서 위치에서 스크롤한다. 양수는 위로, 음수는 아래로 `lines`줄."""
