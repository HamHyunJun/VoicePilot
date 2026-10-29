"""한국어 문장 정규화와 유사도 계산 도구.

음성 인식 결과는 띄어쓰기·문장부호가 들쭉날쭉하고 받침 하나가 틀리는 경우가 많다.
그래서 비교할 때는 문장부호를 지우고, 한글을 자모 단위로 나눈 뒤 유사도를 계산한다.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# 한글 음절 분해용 테이블 (유니코드 한글 음절 = 0xAC00 + (초성*21 + 중성)*28 + 종성)
_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
_HANGUL_BASE = 0xAC00
_HANGUL_LAST = 0xD7A3

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """소문자로 바꾸고 문장부호를 지운 뒤 공백을 하나로 합친다."""
    text = _PUNCT_RE.sub(" ", text.lower())
    return _SPACE_RE.sub(" ", text).strip()


def compact(text: str) -> str:
    """정규화 후 공백까지 모두 제거한다. 띄어쓰기 차이를 무시할 때 쓴다."""
    return normalize(text).replace(" ", "")


def to_jamo(text: str) -> str:
    """한글 음절을 초성·중성·종성 자모로 풀어 쓴다. 한글이 아닌 글자는 그대로 둔다."""
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if _HANGUL_BASE <= code <= _HANGUL_LAST:
            offset = code - _HANGUL_BASE
            cho, rest = divmod(offset, 21 * 28)
            jung, jong = divmod(rest, 28)
            out.append(_CHO[cho])
            out.append(_JUNG[jung])
            if jong:
                out.append(_JONG[jong])
        else:
            out.append(ch)
    return "".join(out)


def similarity(a: str, b: str) -> float:
    """두 문장의 유사도(0.0~1.0). 공백을 무시하고 자모 단위로 비교한다."""
    ja, jb = to_jamo(compact(a)), to_jamo(compact(b))
    if not ja and not jb:
        return 1.0
    if not ja or not jb:
        return 0.0
    return SequenceMatcher(None, ja, jb, autojunk=False).ratio()


# 슬롯 값 끝에 붙는 조사. 긴 것부터 검사해야 "으로"가 "로"보다 먼저 떨어진다.
_PARTICLES = ("으로요", "으로", "에게로", "에게", "한테", "로요", "로", "에서", "에", "을", "를", "은", "는", "이", "가")


def strip_particle(word: str) -> str:
    """단어 끝의 조사를 하나 떼어 낸다. 떼고 나서 아무것도 남지 않으면 원래 단어를 돌려준다."""
    word = word.strip()
    for p in _PARTICLES:
        if word.endswith(p) and len(word) > len(p):
            return word[: -len(p)].strip()
    return word


_NATIVE_NUMBERS = {
    "첫": 1, "첫째": 1, "한": 1, "하나": 1,
    "두": 2, "둘": 2, "둘째": 2,
    "세": 3, "셋": 3, "셋째": 3,
    "네": 4, "넷": 4, "넷째": 4,
    "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9,
}
_SINO_NUMBERS = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
_NUMBER_SUFFIX_RE = re.compile(r"(번째|번|째|번의|번으로|으로|로)$")


def parse_korean_number(text: str) -> int | None:
    """"1번", "두 번째", "삼번" 같은 표현을 정수로 바꾼다. 해석할 수 없으면 None."""
    word = compact(text)
    digits = re.match(r"^(\d+)", word)
    if digits:
        return int(digits.group(1))
    # 접미사를 떼어 가며 숫자 단어를 찾는다 ("두번째" → "두", "삼번" → "삼")
    for _ in range(3):
        if word in _NATIVE_NUMBERS:
            return _NATIVE_NUMBERS[word]
        if word in _SINO_NUMBERS:
            return _SINO_NUMBERS[word]
        stripped = _NUMBER_SUFFIX_RE.sub("", word)
        if stripped == word:
            break
        word = stripped
    return None
