"""구성 요소를 조립하고 실행 루프를 돌린다."""

from __future__ import annotations

import logging
import sys
from typing import TextIO

from .actions import ActionExecutor, WindowResolver
from .assistant import Assistant
from .commands import CommandMatcher, load_command_file
from .config import Settings
from .feedback import ConsoleFeedback
from .platform import DesktopController
from .wakeword import WakeWordDetector

log = logging.getLogger(__name__)


def build_assistant(settings: Settings, controller: DesktopController, feedback=None) -> Assistant:
    command_file = load_command_file(settings.commands_file)
    return Assistant(
        wake=WakeWordDetector(settings.wake.words, threshold=settings.wake.threshold),
        matcher=CommandMatcher(command_file.commands, threshold=settings.match_threshold),
        executor=ActionExecutor(
            controller,
            WindowResolver(command_file.aliases, threshold=settings.window_match_threshold),
        ),
        feedback=feedback or ConsoleFeedback(sound=settings.sound),
        listen_timeout=settings.wake.listen_timeout,
    )


def run_text_loop(assistant: Assistant, stdin: TextIO = sys.stdin) -> None:
    """키보드로 문장을 입력해 음성 없이 동작을 확인하는 모드."""
    print("텍스트 모드입니다. 예: '파일럿 클로드보드로 넘어와'  (종료: Ctrl+D)", flush=True)
    for line in stdin:
        assistant.handle_text(line)


def run_voice_loop(assistant: Assistant, settings: Settings) -> None:
    """마이크 → 발화 분리 → 로컬 음성 인식 → 도우미 순서로 계속 처리한다."""
    from .audio import SpeechSegmenter
    from .audio.microphone import Microphone
    from .stt.whisper_engine import WhisperRecognizer

    stt = WhisperRecognizer(
        model=settings.stt.model,
        language=settings.stt.language,
        device=settings.stt.device,
        compute_type=settings.stt.compute_type,
        beam_size=settings.stt.beam_size,
        initial_prompt=settings.stt.initial_prompt or None,
        local_files_only=settings.stt.local_files_only,
    )
    segmenter = SpeechSegmenter(settings.audio)
    words = ", ".join(settings.wake.words[:2])
    print(f"준비 완료. '{words}'(이)라고 부른 뒤 명령하세요. (종료: Ctrl+C)", flush=True)

    with Microphone(settings.audio.sample_rate, device=settings.input_device) as mic:
        while True:
            block = mic.read(timeout=0.1)
            assistant.tick()
            if block is None:
                continue
            for segment in segmenter.feed(block):
                text = stt.transcribe(segment)
                log.debug("인식: %s", text)
                if text:
                    assistant.handle_text(text)
