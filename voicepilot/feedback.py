"""사용자 피드백 (효과음·콘솔 출력).

최소 버전은 콘솔 출력과 macOS 기본 효과음만 쓴다. 오버레이 창은 다음 단계에서 같은 인터페이스로 추가한다.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Protocol

# macOS 기본 효과음 파일
_MAC_SOUNDS = {
    "wake": "/System/Library/Sounds/Tink.aiff",
    "success": "/System/Library/Sounds/Pop.aiff",
    "fail": "/System/Library/Sounds/Basso.aiff",
}


class Feedback(Protocol):
    def on_wake(self) -> None: ...
    def on_timeout(self) -> None: ...
    def on_heard(self, text: str) -> None: ...
    def on_result(self, ok: bool, message: str) -> None: ...


class ConsoleFeedback:
    """콘솔에 상태를 출력하고, 가능하면 효과음을 낸다."""

    def __init__(self, sound: bool = True, out=None):
        self.out = out or sys.stdout
        self.sound = sound and sys.platform == "darwin" and shutil.which("afplay") is not None

    def _print(self, msg: str) -> None:
        print(msg, file=self.out, flush=True)

    def _play(self, name: str) -> None:
        if not self.sound:
            return
        # 소리를 기다리지 않도록 백그라운드로 재생한다.
        subprocess.Popen(["afplay", _MAC_SOUNDS[name]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def on_wake(self) -> None:
        self._print("🎙  듣고 있어요...")
        self._play("wake")

    def on_timeout(self) -> None:
        self._print("…명령이 없어 대기 상태로 돌아갑니다.")

    def on_heard(self, text: str) -> None:
        self._print(f"🗣  {text}")

    def on_result(self, ok: bool, message: str) -> None:
        self._print(("✅ " if ok else "⚠️  ") + message)
        self._play("success" if ok else "fail")
