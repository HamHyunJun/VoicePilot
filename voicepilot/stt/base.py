"""음성 인식 엔진 인터페이스. 다른 오프라인 엔진(whisper.cpp 등)도 이 형태로 붙인다."""

from __future__ import annotations

from typing import Protocol

import numpy as np


class SpeechRecognizer(Protocol):
    def transcribe(self, audio: np.ndarray) -> str:
        """16kHz 모노 float32 오디오를 문장으로 바꾼다."""
        ...
