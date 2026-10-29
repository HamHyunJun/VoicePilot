"""테스트 공용 준비물."""

from pathlib import Path

import pytest

from voicepilot.actions import ActionExecutor, WindowResolver
from voicepilot.assistant import Assistant
from voicepilot.commands import CommandMatcher, load_command_file
from voicepilot.platform import DummyController
from voicepilot.wakeword import WakeWordDetector

ROOT = Path(__file__).resolve().parent.parent
COMMANDS = ROOT / "config" / "commands.yaml"


class RecordingFeedback:
    """피드백 호출을 기록만 하는 가짜 객체."""

    def __init__(self):
        self.events = []

    def on_wake(self):
        self.events.append(("wake",))

    def on_timeout(self):
        self.events.append(("timeout",))

    def on_heard(self, text):
        self.events.append(("heard", text))

    def on_result(self, ok, message):
        self.events.append(("result", ok, message))


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def command_file():
    return load_command_file(COMMANDS)


@pytest.fixture
def matcher(command_file):
    return CommandMatcher(command_file.commands)


@pytest.fixture
def controller():
    return DummyController()


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def feedback():
    return RecordingFeedback()


@pytest.fixture
def assistant(command_file, matcher, controller, feedback, clock):
    return Assistant(
        wake=WakeWordDetector(["파일럿", "파일롯", "pilot"]),
        matcher=matcher,
        executor=ActionExecutor(controller, WindowResolver(command_file.aliases)),
        feedback=feedback,
        listen_timeout=5.0,
        clock=clock,
    )
