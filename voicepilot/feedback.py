"""사용자 피드백 (효과음·콘솔 출력·오버레이)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from typing import Protocol

log = logging.getLogger(__name__)

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


class OverlayFeedback:
    """다른 피드백을 감싸서, 호출어를 들으면 화면 가운데에 듣는 중 애니메이션을 띄운다.

    애니메이션은 별도 프로세스(`platform/macos_overlay.py`)가 그린다. 띄우지 못해도 음성 제어는 계속 동작한다.
    """

    def __init__(self, inner: Feedback, timeout: float = 6.0, spawn=None):
        self.inner = inner
        self.timeout = timeout
        self._spawn = spawn or _spawn_overlay
        self._proc = None
        self._disabled = False

    def _send(self, line: str) -> None:
        if self._disabled:
            return
        try:
            if self._proc is None or self._proc.poll() is not None:
                self._proc = self._spawn()
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
        except (OSError, ValueError):  # 프로세스를 못 띄우거나 파이프가 끊김
            log.warning("오버레이를 표시하지 못해 끕니다.", exc_info=True)
            self._disabled = True

    def on_wake(self) -> None:
        self.inner.on_wake()
        self._send(f"show {self.timeout}")

    def on_timeout(self) -> None:
        self.inner.on_timeout()
        self._send("hide")

    def on_heard(self, text: str) -> None:
        self.inner.on_heard(text)
        self._send("hide")

    def on_result(self, ok: bool, message: str) -> None:
        self.inner.on_result(ok, message)


def _spawn_overlay():
    return subprocess.Popen(
        [sys.executable, "-m", "voicepilot.platform.macos_overlay"],
        stdin=subprocess.PIPE,
        text=True,
    )
