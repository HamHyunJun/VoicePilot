from voicepilot.actions import ActionExecutor, WindowResolver
from voicepilot.actions.targets import resolve_monitor, topmost_window_on
from voicepilot.commands import Intent
from voicepilot.platform import DummyController, Monitor, Rect, Window


def _intent(action, **args):
    return Intent("test", action, args, 1.0, "")


MONITORS = [
    Monitor(2, Rect(1920, 0, 2560, 1440)),
    Monitor(1, Rect(0, 0, 1920, 1080), is_main=True),
    Monitor(3, Rect(-1440, 0, 1440, 900)),
]


def test_resolve_monitor_by_position_sorts_left_to_right():
    assert resolve_monitor(MONITORS, position="left").id == 3
    assert resolve_monitor(MONITORS, position="right").id == 2
    assert resolve_monitor(MONITORS, position="center").id == 1
    assert resolve_monitor(MONITORS, position="main").id == 1
    assert resolve_monitor(MONITORS, index=1).id == 3
    assert resolve_monitor(MONITORS, index=9) is None


def test_resolve_monitor_next_wraps_around():
    right = resolve_monitor(MONITORS, position="right")
    assert resolve_monitor(MONITORS, position="next", current=right).id == 3
    assert resolve_monitor(MONITORS, position="prev", current=right).id == 1


def test_window_resolver_uses_aliases_and_fuzzy_match():
    windows = DummyController().list_windows()
    resolver = WindowResolver({"클로드보드": ["ClaudeBoard"], "크롬": ["Google Chrome"]})
    assert resolver.resolve("클로드보드", windows).id == 103
    assert resolver.resolve("크롬", windows).id == 102
    assert resolver.resolve("chrome", windows).id == 102  # 앱 이름 일부
    assert resolver.resolve("github", windows).id == 102  # 창 제목
    assert resolver.resolve("없는앱", windows) is None
    assert resolver.resolve("클롬", windows).id == 102  # 인식기가 "크롬"을 다르게 적은 경우


def test_window_resolver_prefers_front_window_on_tie():
    windows = [
        Window(1, "Google Chrome", "A", 1, Rect(0, 0, 100, 100)),
        Window(2, "Google Chrome", "B", 1, Rect(0, 0, 100, 100)),
    ]
    assert WindowResolver().resolve("Google Chrome", windows).id == 1


def test_focus_window_focuses_and_moves_cursor_to_center():
    ctl = DummyController()
    ex = ActionExecutor(ctl, WindowResolver({"클로드보드": ["ClaudeBoard"]}))
    result = ex.execute(_intent("focus_window", target="클로드보드"))
    assert result.ok
    assert ctl.calls == [("focus_window", 103), ("move_cursor", 2800.0, 650.0)]


def test_focus_window_reports_missing_window():
    ctl = DummyController()
    result = ActionExecutor(ctl).execute(_intent("focus_window", target="없는앱"))
    assert not result.ok
    assert ctl.calls == []


def test_focus_monitor_moves_cursor_and_focuses_top_window_there():
    ctl = DummyController()
    result = ActionExecutor(ctl).execute(_intent("focus_monitor", position="right"))
    assert result.ok
    # 오른쪽 모니터(1920~4480)에서 가장 앞쪽 창은 크롬(102)
    assert ctl.calls == [("focus_window", 102), ("move_cursor", 3200.0, 720.0)]


def test_focus_empty_monitor_only_moves_cursor():
    ctl = DummyController(windows=[])
    result = ActionExecutor(ctl).execute(_intent("focus_monitor", index=1))
    assert result.ok
    assert ctl.calls == [("move_cursor", 960.0, 540.0)]


def test_topmost_window_on_monitor():
    windows = DummyController().list_windows()
    assert topmost_window_on(MONITORS[1], windows).id == 101


def test_unknown_action_and_custom_registration():
    ex = ActionExecutor(DummyController())
    assert not ex.execute(_intent("dance")).ok
    from voicepilot.actions import ActionResult

    ex.register("dance", lambda _ex, args: ActionResult(True, "춤"))
    assert ex.execute(_intent("dance")).message == "춤"


def test_click_passes_button_and_count_to_controller():
    ctl = DummyController()
    ex = ActionExecutor(ctl)
    assert ex.execute(_intent("click")).ok
    assert ex.execute(_intent("click", count=2)).ok
    assert ex.execute(_intent("click", button="right")).ok
    assert ctl.calls == [("click", "left", 1), ("click", "left", 2), ("click", "right", 1)]


def test_scroll_down_is_negative_and_up_is_positive():
    ctl = DummyController()
    ex = ActionExecutor(ctl)
    assert ex.execute(_intent("scroll", direction="down")).ok
    assert ex.execute(_intent("scroll", direction="up")).ok
    assert ctl.calls == [("scroll", -10), ("scroll", 10)]


def test_scroll_without_direction_fails():
    ctl = DummyController()
    assert not ActionExecutor(ctl).execute(_intent("scroll")).ok
    assert ctl.calls == []


def test_focus_window_with_position_only_searches_that_monitor():
    # 크롬(102)은 오른쪽 모니터, 코드(101)는 왼쪽 모니터에 있다.
    ctl = DummyController()
    ex = ActionExecutor(ctl, WindowResolver({"크롬": ["Google Chrome"], "코드": ["Code"]}))
    assert ex.execute(_intent("focus_window", target="크롬", position="right")).ok
    assert ctl.calls[0] == ("focus_window", 102)

    result = ex.execute(_intent("focus_window", target="크롬", position="left"))
    assert not result.ok
    assert len(ctl.calls) == 2  # 실패한 명령은 아무것도 하지 않는다


def test_focus_window_with_unknown_position_fails():
    ctl = DummyController()
    result = ActionExecutor(ctl).execute(_intent("focus_window", target="크롬", position="옆쪽"))
    assert not result.ok
    assert ctl.calls == []


def test_focus_window_with_monitor_index():
    ctl = DummyController()
    ex = ActionExecutor(ctl, WindowResolver({"크롬": ["Google Chrome"]}))
    assert ex.execute(_intent("focus_window", target="크롬", index=2)).ok
    assert ctl.calls[0] == ("focus_window", 102)
    assert not ex.execute(_intent("focus_window", target="크롬", index=1)).ok
