"""구성 요소를 조립하고 실행 루프를 돌린다."""

from __future__ import annotations

import logging
import sys
from typing import TextIO

from .actions import ActionExecutor, WindowResolver
from .assistant import Assistant, State
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


_QUICK_WAKE_MAX_S = 1.5  # 이보다 긴 발화는 작은 모델이 호출어만 듣고 나머지를 놓쳤을 수 있어 다시 인식한다


def transcribe_segment(assistant: Assistant, stt, quick, segment, sample_rate: int) -> str:
    """대기 중에는 작은 모델로 호출어부터 확인한다. "파일럿"만 짧게 불렀으면 바로 쓰고, 그 밖에는 정확한 모델로 다시 인식한다."""
    if quick is None or assistant.state is not State.IDLE:
        return stt.transcribe(segment)
    text = quick.transcribe(segment)
    wake = assistant.wake.detect(text)
    if wake.detected and not wake.command and len(segment) / sample_rate <= _QUICK_WAKE_MAX_S:
        return text
    return stt.transcribe(segment)


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
    quick = None
    if settings.stt.wake_model and settings.stt.wake_model != settings.stt.model:
        quick = WhisperRecognizer(
            model=settings.stt.wake_model,
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
            # 호출어 뒤에 긴 문장을 말하면 문장이 끝나기 전에 듣기 시간이 지나 버리므로, 말하는 동안은 시간을 멈춘다.
            if segmenter.in_speech:
                assistant.hold()
            else:
                assistant.tick()
            if block is None:
                continue
            for segment in segmenter.feed(block):
                assistant.hold()  # 인식하는 시간(1~2초)도 듣기 시간에 넣지 않는다
                text = transcribe_segment(assistant, stt, quick, segment, settings.audio.sample_rate)
                log.debug("인식: %s", text)
                assistant.hold()
                if text and assistant.handle_text(text).kind == "ignored":
                    print(f"…호출어 없이 들린 말(무시): {text}", flush=True)
