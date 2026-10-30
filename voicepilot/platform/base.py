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


@dataclass(frozen=True)
class Tab:
    """브라우저 창 안의 탭 하나. `index`는 창 안에서 1부터 세는 탭 번호, `app_window_index`는 앱이 세는 창 번호다."""

    window: Window
    index: int
    title: str
    app_window_index: int = 0
    url: str = ""


class PlatformError(RuntimeError):
    """OS 조작 중 발생한 오류 (권한 부족 등)."""


class DesktopController(ABC):
    @abstractmethod
    def list_windows(self) -> list[Window]:
        """보이는 일반 창 목록을 앞쪽(최근에 포커스된) 창부터 돌려준다."""

    def list_tabs(self, windows: list[Window]) -> list[Tab]:
        """주어진 창들 중 브라우저 창의 모든 탭(가려진 탭 포함)을 돌려준다. 지원하지 않으면 빈 목록."""
        return []

    def select_tab(self, tab: Tab) -> None:
        """탭을 선택하고 그 창을 맨 앞으로 가져온다."""
        raise PlatformError("이 OS에서는 탭 전환을 지원하지 않습니다.")

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
    def hide_app(self, window: Window) -> None:
        """창이 속한 앱을 숨긴다 (그 앱의 모든 창이 화면에서 내려간다). 다시 보려면 앱을 활성화하면 된다."""

    @abstractmethod
    def launch_app(self, names: list[str]) -> str:
        """후보 이름을 차례로 시도해 처음 실행(또는 앞으로 가져오기)에 성공한 앱 이름을 돌려준다. 모두 실패하면 PlatformError."""

    @abstractmethod
    def open_url(self, url: str, app_names: list[str]) -> str:
        """주소를 연다. `app_names`를 차례로 시도해 처음 성공한 앱 이름을 돌려주고, 비어 있으면 기본 브라우저로 연다("")."""

    @abstractmethod
    def click(self, button: str = "left", count: int = 1) -> None:
        """현재 커서 위치를 클릭한다. button은 "left"/"right", count=2면 더블클릭."""

    @abstractmethod
    def scroll(self, lines: int) -> None:
        """현재 커서 위치에서 스크롤한다. 양수는 위로, 음수는 아래로 `lines`줄."""
