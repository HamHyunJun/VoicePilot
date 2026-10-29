"""faster-whisper 기반 로컬 음성 인식.

모델은 처음 한 번만 내려받고 이후에는 내 컴퓨터의 캐시에서 불러온다.
`model`에 내려받아 둔 폴더 경로를 주면 인터넷 연결을 전혀 쓰지 않는다.
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)


class WhisperRecognizer:
    def __init__(
        self,
        model: str = "small",
        language: str = "ko",
        device: str = "auto",
        compute_type: str = "int8",
        beam_size: int = 1,
        initial_prompt: str | None = None,
        local_files_only: bool = False,
    ):
        from faster_whisper import WhisperModel  # 무거운 의존성이라 지연 로딩

        log.info("Whisper 모델 불러오는 중: %s (%s, %s)", model, device, compute_type)
        self.model = WhisperModel(model, device=device, compute_type=compute_type, local_files_only=local_files_only)
        self.language = language
        self.beam_size = beam_size
        # 웨이크워드·앱 이름을 미리 알려 주면 "파일럿"을 다른 단어로 적는 일이 줄어든다.
        self.initial_prompt = initial_prompt

    def transcribe(self, audio: np.ndarray) -> str:
        segments, _info = self.model.transcribe(
            np.asarray(audio, dtype=np.float32),
            language=self.language,
            beam_size=self.beam_size,
            initial_prompt=self.initial_prompt,
            condition_on_previous_text=False,
            without_timestamps=True,
            vad_filter=False,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
