import numpy as np

from voicepilot.app import transcribe_segment

RATE = 16000


class FakeStt:
    def __init__(self, text):
        self.text, self.calls = text, 0

    def transcribe(self, audio):
        self.calls += 1
        return self.text


def _audio(seconds):
    return np.zeros(int(RATE * seconds), dtype=np.float32)


def test_short_wake_only_uses_quick_model_only(assistant):
    stt, quick = FakeStt("정확한 결과"), FakeStt("파일럿.")
    assert transcribe_segment(assistant, stt, quick, _audio(0.6), RATE) == "파일럿."
    assert (stt.calls, quick.calls) == (0, 1)


def test_command_after_wake_is_retranscribed_with_accurate_model(assistant):
    stt, quick = FakeStt("파일럿 구글지도 열어줘"), FakeStt("파일럿 구글 지도 열어줘")
    assert transcribe_segment(assistant, stt, quick, _audio(2.0), RATE) == "파일럿 구글지도 열어줘"
    assert (stt.calls, quick.calls) == (1, 1)


def test_missed_wake_falls_back_to_accurate_model(assistant):
    stt, quick = FakeStt("파일럿"), FakeStt("")
    assert transcribe_segment(assistant, stt, quick, _audio(0.6), RATE) == "파일럿"
    assert stt.calls == 1


def test_long_wake_only_is_not_trusted(assistant):
    # 작은 모델이 "파일럿"만 들었어도 발화가 길면 뒤의 명령을 놓쳤을 수 있다.
    stt, quick = FakeStt("파일럿 크롬 열어줘"), FakeStt("파일럿")
    assert transcribe_segment(assistant, stt, quick, _audio(3.0), RATE) == "파일럿 크롬 열어줘"
    assert stt.calls == 1


def test_listening_state_and_missing_quick_model_use_accurate_model(assistant):
    stt = FakeStt("크롬 열어줘")
    assistant.handle_text("파일럿")  # 듣는 중으로 바뀐다
    quick = FakeStt("파일럿")
    assert transcribe_segment(assistant, stt, quick, _audio(0.6), RATE) == "크롬 열어줘"
    assert quick.calls == 0
    assert transcribe_segment(assistant, stt, None, _audio(0.6), RATE) == "크롬 열어줘"
