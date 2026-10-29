"""설정 파일(settings.yaml) 로딩.

설정 파일에 없는 항목은 아래 기본값을 쓴다. 상대 경로는 설정 파일이 있는 폴더 기준이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

from .audio.segmenter import SegmenterConfig

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS = PACKAGE_ROOT / "config" / "settings.yaml"


@dataclass
class WakeConfig:
    words: list[str] = field(default_factory=lambda: ["파일럿", "파일롯", "pilot"])
    threshold: float = 0.75
    listen_timeout: float = 6.0


@dataclass
class STTConfig:
    model: str = "small"
    language: str = "ko"
    device: str = "auto"
    compute_type: str = "int8"
    beam_size: int = 1
    local_files_only: bool = False
    initial_prompt: str = "파일럿, 왼쪽 화면, 오른쪽 모니터, 클로드보드로 넘어와."


@dataclass
class Settings:
    wake: WakeConfig = field(default_factory=WakeConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    audio: SegmenterConfig = field(default_factory=SegmenterConfig)
    input_device: int | str | None = None
    commands_file: Path = PACKAGE_ROOT / "config" / "commands.yaml"
    match_threshold: float = 0.72
    window_match_threshold: float = 0.7
    sound: bool = True


def _build(cls, data: dict[str, Any] | None):
    data = data or {}
    known = {f.name for f in fields(cls)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"{cls.__name__}에 알 수 없는 설정이 있습니다: {sorted(unknown)}")
    return cls(**data)


def load_settings(path: str | Path | None = None) -> Settings:
    path = Path(path) if path else DEFAULT_SETTINGS
    raw: dict[str, Any] = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    settings = Settings(
        wake=_build(WakeConfig, raw.pop("wake", None)),
        stt=_build(STTConfig, raw.pop("stt", None)),
        audio=_build(SegmenterConfig, raw.pop("audio", None)),
    )
    commands_file = raw.pop("commands_file", None)
    if commands_file:
        p = Path(commands_file).expanduser()
        settings.commands_file = p if p.is_absolute() else (path.parent / p).resolve()
    for key, value in raw.items():
        if not hasattr(settings, key):
            raise ValueError(f"알 수 없는 설정 항목입니다: {key}")
        setattr(settings, key, value)
    return settings
