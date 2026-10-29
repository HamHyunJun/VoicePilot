"""명령 사전과 유사 문장 매칭.

명령 하나는 여러 개의 문장 패턴을 가진다. 패턴 안의 `{이름}`은 슬롯으로, 말한 내용에서 값을 뽑아낸다.

매칭 순서
1. 슬롯이 없는 패턴과 정확히 같으면 1.0점
2. 슬롯 패턴이 정규식으로 맞거나, 슬롯이 없는 패턴이 문장 안에 통째로 들어 있으면 0.9~0.99점.
   고정 문구가 문장에서 차지하는 비율이 클수록(더 구체적인 패턴일수록) 점수가 높다.
   예) "두 번째 화면으로 넘어와"는 "{target} 넘어와"보다 "{index} 화면으로 넘어와"에 더 높은 점수
3. 그래도 없으면 자모 유사도로 점수를 매겨 `threshold` 이상인 것 중 최고점
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..textutil import compact, normalize, parse_korean_number, similarity, strip_particle

_SLOT_RE = re.compile(r"\{(\w+)\}")

# 슬롯 이름별 후처리. 지정되지 않은 슬롯은 조사만 떼어 낸다.
_NUMBER_SLOTS = {"index", "number", "count"}


@dataclass(frozen=True)
class Intent:
    """인식된 명령. 동작 실행기에 그대로 전달된다."""

    command_id: str
    action: str
    args: dict[str, Any]
    score: float
    text: str


@dataclass
class _Pattern:
    raw: str
    slots: list[str]
    regex: re.Pattern[str] | None
    # 퍼지 매칭용: 슬롯 앞뒤의 고정 문구
    prefix: str = ""
    suffix: str = ""

    @property
    def literal_len(self) -> int:
        """슬롯을 뺀 고정 문구의 글자 수 (공백 제외)."""
        return len(compact(_SLOT_RE.sub("", self.raw)))


@dataclass
class CommandSpec:
    id: str
    action: str
    patterns: list[str]
    args: dict[str, Any] = field(default_factory=dict)
    _compiled: list[_Pattern] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.patterns:
            raise ValueError(f"명령 '{self.id}'에 패턴이 없습니다.")
        self._compiled = [_compile(p) for p in self.patterns]


def _compile(pattern: str) -> _Pattern:
    text = normalize_pattern(pattern)
    slots = _SLOT_RE.findall(text)
    if not slots:
        return _Pattern(raw=text, slots=[], regex=None)
    if len(set(slots)) != len(slots):
        raise ValueError(f"패턴에 같은 슬롯이 두 번 있습니다: {pattern}")

    # 고정 문구는 공백 차이를 무시하도록 글자 사이에 \s* 를 넣는다.
    parts: list[str] = []
    pos = 0
    for m in _SLOT_RE.finditer(text):
        parts.append(_loose_literal(text[pos : m.start()]))
        parts.append(f"(?P<{m.group(1)}>.+?)")
        pos = m.end()
    parts.append(_loose_literal(text[pos:]))
    regex = re.compile("^" + "".join(parts) + "$")

    first, last = _SLOT_RE.search(text), list(_SLOT_RE.finditer(text))[-1]
    return _Pattern(
        raw=text,
        slots=slots,
        regex=regex,
        prefix=text[: first.start()].strip(),
        suffix=text[last.end() :].strip(),
    )


def normalize_pattern(pattern: str) -> str:
    """슬롯 표기는 지키면서 패턴 문장을 정규화한다."""
    holders: list[str] = []

    def keep(m: re.Match[str]) -> str:
        holders.append(m.group(0))
        return f" slotholder{len(holders) - 1} "

    text = normalize(_SLOT_RE.sub(keep, pattern))
    for i, slot in enumerate(holders):
        text = text.replace(f"slotholder{i}", slot)
    return text


def _loose_literal(text: str) -> str:
    chars = [re.escape(c) for c in text.replace(" ", "")]
    return r"\s*" + r"\s*".join(chars) + r"\s*" if chars else r"\s*"


def _specific_score(literal_len: int, utterance: str) -> float:
    """정확히 맞은 패턴의 점수. 고정 문구 비율이 높을수록 0.9에서 0.99에 가까워진다."""
    coverage = min(1.0, literal_len / max(1, len(compact(utterance))))
    return 0.9 + 0.09 * coverage


def _clean_slot(name: str, value: str) -> Any:
    value = value.strip()
    if name in _NUMBER_SLOTS:
        return parse_korean_number(value)
    return strip_particle(value)


class CommandMatcher:
    def __init__(self, commands: list[CommandSpec], threshold: float = 0.72):
        ids = [c.id for c in commands]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"명령 id가 중복되었습니다: {sorted(dup)}")
        self.commands = commands
        self.threshold = threshold

    def match(self, text: str) -> Intent | None:
        utterance = normalize(text)
        if not utterance:
            return None

        best: Intent | None = None
        for cmd in self.commands:
            for pat in cmd._compiled:
                result = self._score(pat, utterance)
                if result is None:
                    continue
                score, slots = result
                if best is None or score > best.score:
                    args = {**cmd.args, **slots}
                    best = Intent(cmd.id, cmd.action, args, round(score, 3), utterance)

        if best is None or best.score < self.threshold:
            return None
        return best

    def _score(self, pat: _Pattern, utterance: str) -> tuple[float, dict[str, Any]] | None:
        if pat.regex is None:
            if compact(utterance) == compact(pat.raw):
                return 1.0, {}
            if compact(pat.raw) in compact(utterance):
                return _specific_score(pat.literal_len, utterance), {}
            return similarity(utterance, pat.raw), {}

        m = pat.regex.match(utterance)
        if m:
            slots = {name: _clean_slot(name, m.group(name)) for name in pat.slots}
            if all(v not in (None, "") for v in slots.values()):
                return _specific_score(pat.literal_len, utterance), slots

        # 단일 슬롯 패턴만 퍼지 매칭한다: 문장을 어절 경계에서 잘라 앞/뒤 문구와 비교
        if len(pat.slots) != 1:
            return None
        return self._fuzzy_single_slot(pat, utterance)

    def _fuzzy_single_slot(self, pat: _Pattern, utterance: str) -> tuple[float, dict[str, Any]] | None:
        tokens = utterance.split()
        n_pre = len(pat.prefix.split()) if pat.prefix else 0
        n_suf = len(pat.suffix.split()) if pat.suffix else 0
        if len(tokens) < n_pre + n_suf + 1:
            return None
        pre = " ".join(tokens[:n_pre])
        suf = " ".join(tokens[len(tokens) - n_suf :]) if n_suf else ""
        slot_text = " ".join(tokens[n_pre : len(tokens) - n_suf])

        scores = []
        if pat.prefix:
            scores.append(similarity(pre, pat.prefix))
        if pat.suffix:
            scores.append(similarity(suf, pat.suffix))
        if not scores:
            return None
        value = _clean_slot(pat.slots[0], slot_text)
        if value in (None, ""):
            return None
        # 고정 문구가 비슷해도 정확히 맞은 경우보다는 낮게 친다.
        return min(scores) * 0.9, {pat.slots[0]: value}
