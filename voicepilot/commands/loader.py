"""YAML 명령 사전 파일을 읽어 `CommandSpec` 목록과 창 별칭으로 바꾼다."""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .matcher import CommandSpec


@dataclass
class CommandFile:
    commands: list[CommandSpec]
    # 말로 부르는 이름 → 실제 앱 이름/창 제목 후보 목록
    aliases: dict[str, list[str]]


_ALT_RE = re.compile(r"\(([^()]*\|[^()]*)\)")


def expand_patterns(pattern: str) -> list[str]:
    """패턴 속 "(찾아줘|검색해줘)" 같은 선택지를 풀어 문장 여러 개로 만든다. {슬롯}은 건드리지 않는다."""
    parts = _ALT_RE.split(pattern)  # 짝수 칸은 고정 문구, 홀수 칸은 "a|b" 선택지
    choices = [[p] if i % 2 == 0 else p.split("|") for i, p in enumerate(parts)]
    return ["".join(c) for c in itertools.product(*choices)]


def parse_command_data(data: dict[str, Any]) -> CommandFile:
    if not isinstance(data, dict):
        raise ValueError("명령 사전 최상위는 매핑이어야 합니다.")

    commands: list[CommandSpec] = []
    for i, item in enumerate(data.get("commands") or []):
        if not isinstance(item, dict):
            raise ValueError(f"commands[{i}] 항목이 매핑이 아닙니다.")
        try:
            commands.append(
                CommandSpec(
                    id=str(item["id"]),
                    action=str(item["action"]),
                    patterns=[e for p in item.get("patterns") or [] for e in expand_patterns(str(p))],
                    args=dict(item.get("args") or {}),
                )
            )
        except KeyError as e:
            raise ValueError(f"commands[{i}]에 필수 항목 {e}가 없습니다.") from None

    aliases: dict[str, list[str]] = {}
    for name, targets in (data.get("aliases") or {}).items():
        if isinstance(targets, str):
            targets = [targets]
        aliases[str(name)] = [str(t) for t in targets]

    return CommandFile(commands=commands, aliases=aliases)


def load_command_file(path: str | Path) -> CommandFile:
    with open(path, encoding="utf-8") as f:
        return parse_command_data(yaml.safe_load(f) or {})
