import pytest

from voicepilot.wakeword import WakeWordDetector


@pytest.fixture
def detector():
    return WakeWordDetector(["파일럿", "파일롯", "pilot"])


@pytest.mark.parametrize(
    "text, command",
    [
        ("파일럿", ""),
        ("파일럿, 클로드보드로 넘어와", "클로드보드로 넘어와"),
        ("파일롯 왼쪽 화면", "왼쪽 화면"),
        ("파이럿 오른쪽 모니터", "오른쪽 모니터"),  # 인식 오류로 한 글자 틀린 경우
        ("Pilot. 크롬 보여줘", "크롬 보여줘"),
        ("헤이 파일럿 왼쪽 화면", "왼쪽 화면"),
    ],
)
def test_detects_wake_word_and_returns_rest(detector, text, command):
    result = detector.detect(text)
    assert result.detected
    assert result.command == command


@pytest.mark.parametrize("text", ["", "안녕하세요", "오늘 날씨 어때", "크롬 보여줘", "시청해 주셔서 감사합니다"])
def test_ignores_other_speech(detector, text):
    assert not detector.detect(text).detected


def test_requires_words():
    with pytest.raises(ValueError):
        WakeWordDetector([])
