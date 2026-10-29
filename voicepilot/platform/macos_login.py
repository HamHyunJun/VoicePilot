"""macOS 로그인 시 자동 실행 (LaunchAgent).

`~/Library/LaunchAgents/`에 plist를 두면 launchd가 로그인할 때 `python -m voicepilot`을 실행한다.
표준 라이브러리만 쓰므로 pyobjc 없이도 불러올 수 있다.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from .base import PlatformError

LABEL = "com.voicepilot.agent"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def log_path() -> Path:
    return Path.home() / "Library" / "Logs" / "VoicePilot.log"


def build_plist(config: str | None = None, python: str = sys.executable) -> dict:
    """설치할 plist 내용. 지금 쓰는 파이썬(가상환경 포함)으로 실행하도록 절대 경로를 박는다."""
    args = [python, "-m", "voicepilot"]
    if config:
        args += ["--config", str(Path(config).resolve())]
    return {
        "Label": LABEL,
        "ProgramArguments": args,
        "RunAtLoad": True,
        # 오류로 죽었을 때만 다시 띄운다. 모델 로딩이 계속 실패해도 30초 간격이라 폭주하지 않는다.
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 30,
        "StandardOutPath": str(log_path()),
        "StandardErrorPath": str(log_path()),
    }


def install(config: str | None = None) -> Path:
    _require_macos()
    path = plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    log_path().parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        plistlib.dump(build_plist(config), f)
    _launchctl("bootout", _domain_target())  # 이미 설치돼 있으면 먼저 내린다. 없으면 실패해도 무시한다.
    result = _launchctl("bootstrap", _domain(), str(path))
    if result.returncode != 0:
        raise PlatformError(f"launchctl 등록에 실패했습니다: {result.stderr.strip() or result.returncode}")
    return path


def uninstall() -> bool:
    """제거했으면 True, 설치된 적이 없으면 False."""
    _require_macos()
    path = plist_path()
    _launchctl("bootout", _domain_target())
    if not path.exists():
        return False
    path.unlink()
    return True


def _require_macos() -> None:
    if sys.platform != "darwin":
        raise PlatformError("로그인 시 자동 실행은 macOS에서만 지원합니다.")


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _domain_target() -> str:
    return f"{_domain()}/{LABEL}"


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)
