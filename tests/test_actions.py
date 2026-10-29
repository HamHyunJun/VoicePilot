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


def test_launch_app_tries_alias_names_before_spoken_name():
    ctl = DummyController()
    ex = ActionExecutor(ctl, WindowResolver({"크롬": ["Google Chrome", "Chrome"]}))
    result = ex.execute(_intent("launch_app", target="크롬"))
    assert result.ok and "Google Chrome" in result.message
    assert ctl.calls == [("launch_app", ("Google Chrome", "Chrome", "크롬"))]


def test_launch_app_reports_missing_app_and_empty_target():
    ex = ActionExecutor(DummyController())
    assert not ex.execute(_intent("launch_app", target="없는앱")).ok
    assert not ex.execute(_intent("launch_app")).ok


def test_open_launches_app_only_when_no_window_exists():
    ctl = DummyController()
    ex = ActionExecutor(ctl, WindowResolver({"크롬": ["Google Chrome"], "사파리": ["Safari"]}))
    # 크롬 창은 있으므로 이동만 한다.
    assert ex.execute(_intent("focus_window", target="크롬", launch_if_missing=True)).ok
    assert ctl.calls[0] == ("focus_window", 102)
    # 사파리 창은 없지만 설치돼 있으므로 실행한다.
    result = ex.execute(_intent("focus_window", target="사파리", launch_if_missing=True))
    assert result.ok and "실행" in result.message
    # 창도 앱도 없으면 실패한다.
    assert not ex.execute(_intent("focus_window", target="없는앱", launch_if_missing=True)).ok


def test_open_with_monitor_launches_only_when_no_window_on_any_monitor():
    ctl = DummyController()
    ex = ActionExecutor(ctl, WindowResolver({"크롬": ["Google Chrome"], "사파리": ["Safari"]}))
    # 사파리는 어느 모니터에도 창이 없으므로 실행한다.
    result = ex.execute(_intent("focus_window", target="사파리", position="right", launch_if_missing=True))
    assert result.ok and "모니터 위치" in result.message
    # 크롬 창은 오른쪽 모니터에 있으므로 왼쪽을 지정하면 다른 모니터에 있는 창이 있는 것이다. 실행하지 않고 실패한다.
    before = len(ctl.calls)
    assert not ex.execute(_intent("focus_window", target="크롬", position="left", launch_if_missing=True)).ok
    assert len(ctl.calls) == before


def test_focus_without_flag_does_not_launch():
    ctl = DummyController()
    ex = ActionExecutor(ctl, WindowResolver({"사파리": ["Safari"]}))
    assert not ex.execute(_intent("focus_window", target="사파리")).ok
    assert ctl.calls == []


def test_hide_window_hides_app_and_it_can_be_launched_again():
    ctl = DummyController()
    ex = ActionExecutor(ctl, WindowResolver({"크롬": ["Google Chrome"]}))
    assert ex.execute(_intent("hide_window", target="크롬")).ok
    assert ctl.calls == [("hide_app", 12)]
    assert ctl.list_windows() and all(w.pid != 12 for w in ctl.list_windows())
    # 숨긴 뒤에는 창이 없으므로 "열어줘"가 앱을 다시 실행한다.
    assert ex.execute(_intent("focus_window", target="크롬", launch_if_missing=True)).message.endswith("실행했습니다.")


def test_hide_window_respects_monitor_and_missing_target():
    ctl = DummyController()
    ex = ActionExecutor(ctl, WindowResolver({"크롬": ["Google Chrome"]}))
    assert not ex.execute(_intent("hide_window", target="크롬", position="left")).ok  # 크롬은 오른쪽 모니터
    assert not ex.execute(_intent("hide_window", target="없는앱")).ok
    assert not ex.execute(_intent("hide_window")).ok
    assert ctl.calls == []


def _chrome_windows():
    # 크롬 창 3개(오른쪽 모니터 2개, 왼쪽 1개)와 다른 앱 창 하나
    return [
        Window(1, "Google Chrome", "npm | Home - Google Chrome", 12, Rect(2000, 0, 800, 600)),
        Window(2, "Google Chrome", "Google 지도 - Google Chrome", 12, Rect(2100, 50, 800, 600)),
        Window(3, "Google Chrome", "Airbnb - Google Chrome", 12, Rect(100, 0, 800, 600)),
        Window(4, "Code", "npm-notes.md", 11, Rect(2200, 100, 800, 600)),
    ]


def _chrome_executor(ctl):
    aliases = {"크롬": ["Google Chrome"], "구글지도": ["Google Maps", "Google 지도"], "에어비앤비": ["Airbnb"]}
    return ActionExecutor(ctl, WindowResolver(aliases))


def test_focus_window_picks_chrome_window_by_title():
    ctl = DummyController(windows=_chrome_windows())
    ex = _chrome_executor(ctl)
    # npm은 코드(Code) 창 제목에도 있지만 "크롬에서"라고 했으므로 크롬 창만 본다.
    assert ex.execute(_intent("focus_window", app="크롬", target="npm")).ok
    assert ctl.calls[0] == ("focus_window", 1)
    assert ex.execute(_intent("focus_window", app="크롬", target="구글지도")).ok
    assert ctl.calls[2] == ("focus_window", 2)


def test_focus_window_with_app_and_monitor():
    ctl = DummyController(windows=_chrome_windows())
    ex = _chrome_executor(ctl)
    # 에어비앤비 창은 왼쪽 모니터에 있으므로 오른쪽을 지정하면 실패한다.
    assert not ex.execute(_intent("focus_window", position="right", app="크롬", target="에어비앤비")).ok
    assert ex.execute(_intent("focus_window", position="left", app="크롬", target="에어비앤비")).ok
    assert ctl.calls[0] == ("focus_window", 3)


def test_focus_window_with_app_never_launches_and_explains_failure():
    ctl = DummyController(windows=_chrome_windows())
    ex = _chrome_executor(ctl)
    result = ex.execute(_intent("focus_window", app="크롬", target="없는사이트", launch_if_missing=True))
    assert not result.ok and "찾지 못했습니다" in result.message
    assert ctl.calls == []
    # 앱 자체가 없을 때도 마찬가지
    assert not ex.execute(_intent("focus_window", app="사파리", target="npm")).ok


def test_focus_window_with_app_hints_when_titles_are_unreadable():
    windows = [Window(1, "Google Chrome", "", 12, Rect(0, 0, 800, 600))]
    result = _chrome_executor(DummyController(windows=windows)).execute(_intent("focus_window", app="크롬", target="npm"))
    assert not result.ok and "권한" in result.message
