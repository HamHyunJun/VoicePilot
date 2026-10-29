"""웨이크워드(호출어) 탐지.

최소 버전은 음성 인식 결과 문장의 앞부분에서 호출어를 찾는다.
Whisper가 "파일럿"을 "파일롯", "파이럿", "Pilot" 등으로 적어도 잡을 수 있게 자모 유사도를 쓴다.
나중에 오디오 기반 탐지기로 바꾸더라도 `detect()`의 반환 형식만 맞추면 된다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .textutil import normalize, similarity


@dataclass(frozen=True)
class WakeResult:
    """호출어 탐지 결과. `command`는 호출어 뒤에 이어 말한 나머지 문장이다."""

    detected: bool
    command: str = ""
    score: float = 0.0


class WakeWordDetector:
    def __init__(self, words: list[str], threshold: float = 0.75, max_words: int = 2):
        if not words:
            raise ValueError("웨이크워드가 하나 이상 필요합니다.")
        self.words = [normalize(w) for w in words]
        self.threshold = threshold
        # 호출어가 차지할 수 있는 최대 어절 수 ("파일 럿"처럼 쪼개져 인식되는 경우 대비)
        self.max_words = max_words

    def detect(self, text: str) -> WakeResult:
        tokens = normalize(text).split()
        if not tokens:
            return WakeResult(False)

        best_score, best_len = 0.0, 0
        # "헤이 파일럿"처럼 앞에 감탄사가 하나 붙는 경우도 허용한다.
        for start in range(min(2, len(tokens))):
            for length in range(1, self.max_words + 1):
                if start + length > len(tokens):
                    break
                candidate = " ".join(tokens[start : start + length])
                score = max(similarity(candidate, w) for w in self.words)
                # 시작 위치가 뒤일수록 약간 감점해 실제 호출어가 맨 앞에 있는 경우를 우선한다.
                score -= 0.05 * start
                if score > best_score:
                    best_score, best_len = score, start + length

        if best_score < self.threshold:
            return WakeResult(False, score=best_score)
        command = " ".join(tokens[best_len:])
        return WakeResult(True, command=command, score=best_score)
