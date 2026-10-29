import pytest

from voicepilot.commands import CommandMatcher, CommandSpec
from voicepilot.commands.loader import parse_command_data


@pytest.mark.parametrize(
    "text, action, args",
    [
        ("클로드보드로 넘어와", "focus_window", {"target": "클로드보드"}),
        ("크롬으로 넘어와", "focus_window", {"target": "크롬"}),
        ("슬랙 보여줘", "focus_window", {"target": "슬랙"}),
        ("클로드보드로넘어와", "focus_window", {"target": "클로드보드"}),  # 띄어쓰기 없음
        ("클로드보드로 넘어와요", "focus_window", {"target": "클로드보드"}),  # 어미가 조금 다름
        ("왼쪽 화면", "focus_monitor", {"position": "left"}),
        ("오른쪽 모니터로 넘어와", "focus_monitor", {"position": "right"}),
        ("왼쪽 화면으로 넘어와", "focus_monitor", {"position": "left"}),
        ("왼쪽 화면 좀 보여줘", "focus_monitor", {"position": "left"}),
        ("오른쪽 화면.", "focus_monitor", {"position": "right"}),
        ("2번 모니터", "focus_monitor", {"index": 2}),
        ("두 번째 화면으로 넘어와", "focus_monitor", {"index": 2}),
        ("다음 화면", "focus_monitor", {"position": "next"}),
        ("크롬 열어줘", "focus_window", {"target": "크롬"}),
        ("오른쪽 화면 크롬 열어줘", "focus_window", {"position": "right", "target": "크롬"}),
        ("왼쪽 모니터 슬랙 열어줘", "focus_window", {"position": "left", "target": "슬랙"}),
        ("오른쪽 화면에서 fork 열어줘", "focus_window", {"position": "right", "target": "fork"}),
        ("왼쪽 모니터의 크롬 열어줘", "focus_window", {"position": "left", "target": "크롬"}),
        ("2번 모니터에서 포크 열어줘", "focus_window", {"index": 2, "target": "포크"}),
        ("오른쪽 화면에서 크롬 열어주", "focus_window", {"position": "right", "target": "크롬"}),  # 끝 글자가 잘림
        ("클릭", "click", {}),
        ("클릭해줘", "click", {}),
        ("더블클릭", "click", {"count": 2}),
        ("우클릭", "click", {"button": "right"}),
        ("오른쪽 클릭", "click", {"button": "right"}),
        ("스크롤 내려", "scroll", {"direction": "down"}),
        ("위로 스크롤", "scroll", {"direction": "up"}),
    ],
)
def test_matches_default_commands(matcher, text, action, args):
    intent = matcher.match(text)
    assert intent is not None, text
    assert intent.action == action
    assert intent.args == args


@pytest.mark.parametrize("text", ["", "오늘 날씨 어때", "점심 뭐 먹지"])
def test_unknown_sentences_do_not_match(matcher, text):
    assert matcher.match(text) is None


def test_exact_pattern_beats_slot_pattern():
    matcher = CommandMatcher(
        [
            CommandSpec("window", "focus_window", ["{target} 넘어와"]),
            CommandSpec("left", "focus_monitor", ["왼쪽으로 넘어와"], args={"position": "left"}),
        ]
    )
    assert matcher.match("왼쪽으로 넘어와").command_id == "left"
    assert matcher.match("크롬으로 넘어와").command_id == "window"


def test_new_command_can_be_added_without_code():
    data = {
        "commands": [{"id": "hello", "action": "say_hello", "patterns": ["안녕 파일럿", "반가워"]}],
        "aliases": {"크롬": "Google Chrome"},
    }
    parsed = parse_command_data(data)
    intent = CommandMatcher(parsed.commands).match("안녕 파일럿")
    assert intent.action == "say_hello"
    assert parsed.aliases == {"크롬": ["Google Chrome"]}


def test_invalid_command_definitions_are_rejected():
    with pytest.raises(ValueError):
        parse_command_data({"commands": [{"id": "x", "patterns": ["a"]}]})  # action 없음
    with pytest.raises(ValueError):
        CommandSpec("x", "y", [])
    with pytest.raises(ValueError):
        CommandMatcher([CommandSpec("x", "a", ["가"]), CommandSpec("x", "b", ["나"])])
