"""마이크 입력 (sounddevice).

콜백에서 받은 오디오를 큐에 넣고, 메인 루프가 꺼내 쓴다.
"""

from __future__ import annotations

import queue

import numpy as np


class Microphone:
    def __init__(self, sample_rate: int = 16000, device: int | str | None = None, block_ms: int = 30):
        self.sample_rate = sample_rate
        self.device = device
        self.blocksize = int(sample_rate * block_ms / 1000)
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream = None

    def __enter__(self) -> "Microphone":
        import sounddevice as sd  # 실제 녹음할 때만 필요하므로 지연 로딩

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            self._queue.put(indata[:, 0].copy())

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.blocksize,
            device=self.device,
            callback=callback,
        )
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def read(self, timeout: float = 0.1) -> np.ndarray | None:
        """오디오 블록 하나를 꺼낸다. 시간 안에 없으면 None."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
