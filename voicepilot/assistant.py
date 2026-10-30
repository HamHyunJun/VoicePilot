"""도우미의 상태 기계.

  IDLE ──(호출어만 들림)──▶ LISTENING ──(명령 실행 또는 시간 초과)──▶ IDLE
   │
   └─(호출어 + 명령을 한 번에 말함)──▶ 바로 실행

음성 입력과 무관하게 문장만 받으므로, 텍스트 모드와 단위 테스트에서도 그대로 쓴다.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass
from typing import Callable

from .actions.executor import ActionExecutor, ActionResult
from .commands.matcher import CommandMatcher, Intent
from .feedback import Feedback
from .wakeword import WakeWordDetector


class State(enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"


@dataclass(frozen=True)
class Outcome:
    """문장 하나를 처리한 결과. 테스트와 로그에서 쓴다."""

    kind: str  # "ignored" | "wake" | "executed" | "unknown"
    intent: Intent | None = None
    result: ActionResult | None = None


class Assistant:
    def __init__(
        self,
        wake: WakeWordDetector,
        matcher: CommandMatcher,
        executor: ActionExecutor,
        feedback: Feedback,
        listen_timeout: float = 6.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.wake = wake
        self.matcher = matcher
        self.executor = executor
        self.feedback = feedback
        self.listen_timeout = listen_timeout
        self.clock = clock
        self.state = State.IDLE
        self._deadline = 0.0
        self._fragment = ""  # 모르는 명령으로 끝난 앞부분 ("크롬에서" 다음에 쉬었다 말한 경우를 잇기 위해)
        self._fragment_until = 0.0

    def tick(self) -> None:
        """듣기 상태 시간 초과를 확인한다. 오디오 루프에서 주기적으로 부른다."""
        if self.state is State.LISTENING and self.clock() >= self._deadline:
            self.state = State.IDLE
            self.feedback.on_timeout()

    def hold(self) -> None:
        """말하는 중이거나 인식 중에는 듣기 시간이 흘러가지 않게 시간 초과를 다시 잰다."""
        if self.state is State.LISTENING:
            self._deadline = self.clock() + self.listen_timeout

    def handle_text(self, text: str) -> Outcome:
        self.tick()
        text = text.strip()
        if not text:
            return Outcome("ignored")

        if self.state is State.IDLE:
            wake = self.wake.detect(text)
            if not wake.detected:
                if self._fragment and self.clock() < self._fragment_until:
                    return self._run_command(text)  # 앞부분과 이어 붙여 실행
                return Outcome("ignored")
            if not wake.command:
                self._start_listening()
                return Outcome("wake")
            return self._run_command(wake.command)

        # LISTENING: 호출어를 다시 붙여 말해도 받아 준다.
        wake = self.wake.detect(text)
        command = wake.command if wake.detected else text
        if not command:
            self._start_listening()
            return Outcome("wake")
        return self._run_command(command)

    def _start_listening(self) -> None:
        self.state = State.LISTENING
        self._deadline = self.clock() + self.listen_timeout
        self.feedback.on_wake()

    def _run_command(self, command: str) -> Outcome:
        self.state = State.IDLE
        if self._fragment and self.clock() < self._fragment_until:
            command = f"{self._fragment} {command}"
        self._fragment = ""
        self.feedback.on_heard(command)
        intent = self.matcher.match(command)
        if intent is None:
            self._fragment, self._fragment_until = command, self.clock() + self.listen_timeout
            self.feedback.on_result(False, f"모르는 명령이에요: {command}")
            return Outcome("unknown")
        result = self.executor.execute(intent)
        self.feedback.on_result(result.ok, result.message)
        return Outcome("executed", intent, result)
