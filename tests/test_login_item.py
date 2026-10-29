import plistlib
import subprocess
import sys

import pytest

from voicepilot.platform import PlatformError, macos_login


@pytest.fixture
def fake_launchctl(tmp_path, monkeypatch):
    """홈 디렉터리를 임시 폴더로 바꾸고 launchctl 호출을 기록만 한다."""
    monkeypatch.setattr(macos_login.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "platform", "darwin")
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd[1:])
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(macos_login.subprocess, "run", run)
    return calls


def test_build_plist_uses_given_python_and_config(tmp_path):
    cfg = tmp_path / "내설정.yaml"
    data = macos_login.build_plist(str(cfg), python="/venv/bin/python")
    assert data["ProgramArguments"] == ["/venv/bin/python", "-m", "voicepilot", "--config", str(cfg.resolve())]
    assert data["RunAtLoad"] is True
    assert macos_login.build_plist(python="/p")["ProgramArguments"] == ["/p", "-m", "voicepilot"]


def test_install_writes_plist_and_registers_with_launchctl(fake_launchctl):
    path = macos_login.install()
    assert plistlib.loads(path.read_bytes())["Label"] == macos_login.LABEL
    assert [c[0] for c in fake_launchctl] == ["bootout", "bootstrap"]


def test_uninstall_removes_plist_and_reports_missing(fake_launchctl):
    assert macos_login.uninstall() is False
    macos_login.install()
    assert macos_login.uninstall() is True
    assert not macos_login.plist_path().exists()


def test_install_fails_with_message_when_launchctl_fails(fake_launchctl, monkeypatch):
    monkeypatch.setattr(
        macos_login.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 5, "", "Bootstrap failed")
    )
    with pytest.raises(PlatformError, match="Bootstrap failed"):
        macos_login.install()


def test_non_macos_is_rejected(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(PlatformError):
        macos_login.install()
