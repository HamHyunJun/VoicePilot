"""에너지 기반 발화 구간 분리기(VAD).

마이크 소리를 30ms 프레임으로 나눠 RMS(소리 크기)를 잰다.
- 주변 소음 크기(noise floor)를 조용한 프레임으로 계속 추정하고, 그보다 충분히 크면 말소리로 본다.
- 말이 시작되면 직전 소리(pre-roll)를 붙여 앞 음절이 잘리지 않게 한다.
- 일정 시간 조용하면 발화 하나가 끝난 것으로 보고 돌려준다.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass
class SegmenterConfig:
    sample_rate: int = 16000
    frame_ms: int = 30
    # 말소리 판정 임계값 = max(min_rms, 소음 크기 × start_ratio)
    start_ratio: float = 3.0
    min_rms: float = 0.01
    silence_ms: int = 700
    min_speech_ms: int = 250
    max_speech_s: float = 10.0
    pre_roll_ms: int = 300


class SpeechSegmenter:
    def __init__(self, config: SegmenterConfig | None = None):
        self.cfg = config or SegmenterConfig()
        self.frame_len = int(self.cfg.sample_rate * self.cfg.frame_ms / 1000)
        self._pending = np.zeros(0, dtype=np.float32)
        self._pre_roll: deque[np.ndarray] = deque(maxlen=max(1, self.cfg.pre_roll_ms // self.cfg.frame_ms))
        self._speech: list[np.ndarray] = []
        self._voiced_frames = 0
        self._silent_frames = 0
        self.noise_floor = self.cfg.min_rms / 2

    @property
    def in_speech(self) -> bool:
        return bool(self._speech)

    @property
    def threshold(self) -> float:
        return max(self.cfg.min_rms, self.noise_floor * self.cfg.start_ratio)

    def feed(self, samples: np.ndarray) -> list[np.ndarray]:
        """오디오 조각을 넣고, 끝난 발화들을 float32 배열 목록으로 돌려준다."""
        data = np.asarray(samples, dtype=np.float32).reshape(-1)
        self._pending = np.concatenate([self._pending, data])
        segments: list[np.ndarray] = []
        while len(self._pending) >= self.frame_len:
            frame = self._pending[: self.frame_len]
            self._pending = self._pending[self.frame_len :]
            seg = self._process_frame(frame)
            if seg is not None:
                segments.append(seg)
        return segments

    def flush(self) -> np.ndarray | None:
        """진행 중인 발화를 강제로 끝낸다 (프로그램 종료 시)."""
        return self._finish() if self._speech else None

    def _process_frame(self, frame: np.ndarray) -> np.ndarray | None:
        rms = float(np.sqrt(np.mean(frame * frame)))
        voiced = rms >= self.threshold
        frame_ms = self.cfg.frame_ms

        if not self._speech:
            if voiced:
                self._speech = list(self._pre_roll) + [frame]
                self._voiced_frames, self._silent_frames = 1, 0
                self._pre_roll.clear()
            else:
                # 조용할 때만 소음 크기를 천천히 따라간다.
                self.noise_floor = 0.95 * self.noise_floor + 0.05 * rms
                self._pre_roll.append(frame)
            return None

        self._speech.append(frame)
        if voiced:
            self._voiced_frames += 1
            self._silent_frames = 0
        else:
            self._silent_frames += 1

        too_long = len(self._speech) * frame_ms >= self.cfg.max_speech_s * 1000
        if self._silent_frames * frame_ms >= self.cfg.silence_ms or too_long:
            return self._finish()
        return None

    def _finish(self) -> np.ndarray | None:
        speech, voiced = self._speech, self._voiced_frames
        self._speech, self._voiced_frames, self._silent_frames = [], 0, 0
        # 너무 짧은 소리(기침, 딸깍 소리)는 버린다.
        if voiced * self.cfg.frame_ms < self.cfg.min_speech_ms:
            return None
        return np.concatenate(speech)
