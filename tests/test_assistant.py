from voicepilot.assistant import State


def test_wake_word_with_command_runs_immediately(assistant, controller):
    outcome = assistant.handle_text("파일럿, 클로드보드로 넘어와")
    assert outcome.kind == "executed"
    assert outcome.result.ok
    assert controller.calls[0] == ("focus_window", 103)
    assert assistant.state is State.IDLE


def test_speech_without_wake_word_is_ignored(assistant, controller):
    assert assistant.handle_text("클로드보드로 넘어와").kind == "ignored"
    assert controller.calls == []


def test_wake_then_command(assistant, controller, feedback):
    assert assistant.handle_text("파일럿").kind == "wake"
    assert assistant.state is State.LISTENING
    outcome = assistant.handle_text("왼쪽 화면")
    assert outcome.kind == "executed"
    assert outcome.intent.args == {"position": "left"}
    assert assistant.state is State.IDLE
    assert feedback.events[0] == ("wake",)


def test_listening_times_out(assistant, clock, feedback, controller):
    assistant.handle_text("파일럿")
    clock.now = 6.0
    assistant.tick()
    assert assistant.state is State.IDLE
    assert ("timeout",) in feedback.events
    # 시간 초과 후에는 호출어 없이 말한 명령을 무시한다.
    assert assistant.handle_text("왼쪽 화면").kind == "ignored"
    assert controller.calls == []


def test_unknown_command_gives_feedback(assistant, feedback):
    outcome = assistant.handle_text("파일럿 점심 뭐 먹지")
    assert outcome.kind == "unknown"
    assert feedback.events[-1][0:2] == ("result", False)
    assert assistant.state is State.IDLE


def test_repeating_wake_word_while_listening(assistant):
    assistant.handle_text("파일럿")
    assert assistant.handle_text("파일럿 오른쪽 모니터").intent.args == {"position": "right"}


def test_unknown_fragment_is_joined_with_next_utterance_without_wake_word(assistant, clock):
    assert assistant.handle_text("파일럿 크롬에서").kind == "unknown"
    out = assistant.handle_text("후쿠오카 맛집 찾아줘")
    assert out.kind == "executed" and out.intent.args == {"app": "크롬", "query": "후쿠오카 맛집"}
    assert assistant.handle_text("후쿠오카 맛집 찾아줘").kind == "ignored"  # 이어 붙이기는 한 번뿐
    assistant.handle_text("파일럿 크롬에서")
    clock.now += 100
    assert assistant.handle_text("후쿠오카 맛집 찾아줘").kind == "ignored"  # 시간이 지나면 버린다


def test_hold_keeps_listening_while_user_speaks_long_sentence(assistant, clock):
    assistant.handle_text("파일럿")
    for _ in range(3):  # 말하고 인식하는 동안 시간이 흘러도 hold가 시간 초과를 미룬다
        clock.now += 4.0
        assistant.hold()
        assistant.tick()
    assert assistant.state is State.LISTENING
    clock.now += 100
    assistant.tick()
    assert assistant.state is State.IDLE
