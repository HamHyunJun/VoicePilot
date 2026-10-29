import io
import subprocess

from voicepilot.feedback import ConsoleFeedback, OverlayFeedback
from voicepilot.platform.macos_overlay import parse_command


class FakeProc:
    def __init__(self):
        self.stdin = io.StringIO()
        self.returncode = None

    def poll(self):
        return self.returncode


def _feedback(spawn=None, **kw):
    out = io.StringIO()
    proc = FakeProc()
    fb = OverlayFeedback(ConsoleFeedback(sound=False, out=out), spawn=spawn or (lambda: proc), **kw)
    return fb, proc, out


def test_wake_shows_overlay_and_heard_or_timeout_hides_it():
    fb, proc, out = _feedback(timeout=6.0)
    fb.on_wake()
    fb.on_heard("크롬 보여줘")
    fb.on_wake()
    fb.on_timeout()
    assert proc.stdin.getvalue() == "show 6.0\nhide\nshow 6.0\nhide\n"
    assert "듣고 있어요" in out.getvalue()  # 안쪽 피드백도 그대로 동작한다


def test_result_does_not_touch_overlay():
    fb, proc, _ = _feedback()
    fb.on_result(True, "ok")
    assert proc.stdin.getvalue() == ""


def test_respawns_when_overlay_process_died():
    procs = []

    def spawn():
        procs.append(FakeProc())
        return procs[-1]

    fb, _, _ = _feedback(spawn=spawn)
    fb.on_wake()
    procs[0].returncode = 1
    fb.on_wake()
    assert len(procs) == 2 and procs[1].stdin.getvalue() == "show 6.0\n"


def test_overlay_failure_disables_overlay_but_keeps_feedback():
    def spawn():
        raise OSError("실행 불가")

    fb, _, out = _feedback(spawn=spawn)
    fb.on_wake()
    fb.on_wake()  # 한 번 실패하면 다시 시도하지 않는다
    assert fb._disabled
    assert out.getvalue().count("듣고 있어요") == 2


def test_parse_overlay_commands():
    assert parse_command("show 6.0\n") == ("show", 6.0)
    assert parse_command("show") == ("show", 6.0)
    assert parse_command("hide") == ("hide", 0.0)
    assert parse_command("show abc") is None
    assert parse_command("") is None
    assert parse_command("dance") is None
