"""macOS 조작부 연기 테스트. macOS에서만 실행된다 (CI의 macos 러너 포함).

창 포커스·커서 이동은 권한과 실제 화면이 필요해 자동 테스트하지 않고, pyobjc 호출이 올바른지만 확인한다.
"""

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS 전용")


def test_macos_controller_lists_monitors_and_windows():
    from voicepilot.platform.macos import MacOSController

    ctl = MacOSController()
    monitors = ctl.list_monitors()
    assert monitors, "모니터가 하나 이상 있어야 합니다"
    assert any(m.is_main for m in monitors)
    for w in ctl.list_windows():
        assert w.bounds.width >= 50
