import pytest

from voicepilot.app import build_assistant
from voicepilot.config import DEFAULT_SETTINGS, load_settings
from voicepilot.platform import DummyController


def test_default_settings_file_loads():
    s = load_settings(DEFAULT_SETTINGS)
    assert "파일럿" in s.wake.words
    assert s.stt.language == "ko"
    assert s.commands_file.exists()


def test_relative_commands_file_is_resolved_from_settings_dir(tmp_path):
    (tmp_path / "my.yaml").write_text("commands: []\n", encoding="utf-8")
    cfg = tmp_path / "settings.yaml"
    cfg.write_text("commands_file: my.yaml\nwake:\n  listen_timeout: 3\n", encoding="utf-8")
    s = load_settings(cfg)
    assert s.commands_file == (tmp_path / "my.yaml").resolve()
    assert s.wake.listen_timeout == 3


def test_unknown_setting_is_rejected(tmp_path):
    cfg = tmp_path / "settings.yaml"
    cfg.write_text("wake:\n  wordz: [a]\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(cfg)


def test_build_assistant_end_to_end():
    ctl = DummyController()

    class Silent:
        def __getattr__(self, name):
            return lambda *a, **k: None

    a = build_assistant(load_settings(), ctl, feedback=Silent())
    assert a.handle_text("파일럿 클로드보드로 넘어와").result.ok
    assert a.handle_text("파일럿 왼쪽 화면").result.ok
    assert ctl.cursor == (960.0, 540.0)
