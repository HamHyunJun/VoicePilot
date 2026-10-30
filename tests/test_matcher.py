import pytest

from voicepilot.commands import CommandMatcher, CommandSpec
from voicepilot.commands.loader import parse_command_data


@pytest.mark.parametrize(
    "text, action, args",
    [
        ("클로드보드로 넘어와", "focus_window", {"launch_if_missing": True, "target": "클로드보드"}),
        ("크롬으로 넘어와", "focus_window", {"launch_if_missing": True, "target": "크롬"}),
        ("슬랙 보여줘", "focus_window", {"launch_if_missing": True, "target": "슬랙"}),
        ("클로드보드로넘어와", "focus_window", {"launch_if_missing": True, "target": "클로드보드"}),  # 띄어쓰기 없음
        ("클로드보드로 넘어와요", "focus_window", {"launch_if_missing": True, "target": "클로드보드"}),  # 어미가 조금 다름
        ("왼쪽 화면", "focus_monitor", {"position": "left"}),
        ("오른쪽 모니터로 넘어와", "focus_monitor", {"position": "right"}),
        ("왼쪽 화면으로 넘어와", "focus_monitor", {"position": "left"}),
        ("왼쪽 화면 좀 보여줘", "focus_monitor", {"position": "left"}),
        ("오른쪽 화면.", "focus_monitor", {"position": "right"}),
        ("2번 모니터", "focus_monitor", {"index": 2}),
        ("두 번째 화면으로 넘어와", "focus_monitor", {"index": 2}),
        ("다음 화면", "focus_monitor", {"position": "next"}),
        ("크롬 열어줘", "focus_window", {"launch_if_missing": True, "target": "크롬"}),
        ("크롬 보여줘", "focus_window", {"launch_if_missing": True, "target": "크롬"}),
        ("오른쪽 화면 크롬 열어줘", "focus_window", {"launch_if_missing": True, "position": "right", "target": "크롬"}),
        ("왼쪽 모니터 슬랙 열어줘", "focus_window", {"launch_if_missing": True, "position": "left", "target": "슬랙"}),
        ("오른쪽 화면에서 fork 열어줘", "focus_window", {"launch_if_missing": True, "position": "right", "target": "fork"}),
        ("왼쪽 모니터의 크롬 열어줘", "focus_window", {"launch_if_missing": True, "position": "left", "target": "크롬"}),
        ("2번 모니터에서 포크 열어줘", "focus_window", {"launch_if_missing": True, "index": 2, "target": "포크"}),
        ("오른쪽 화면에서 크롬 열어주", "focus_window", {"launch_if_missing": True, "position": "right", "target": "크롬"}),  # 끝 글자가 잘림
        ("크롬 실행해줘", "focus_window", {"launch_if_missing": True, "target": "크롬"}),
        ("사파리 켜줘", "focus_window", {"launch_if_missing": True, "target": "사파리"}),
        ("오른쪽 화면 켜줘", "focus_monitor", {"position": "right"}),  # 모니터 전환이 앱 실행보다 구체적
        ("포크 숨겨줘", "hide_window", {"target": "포크"}),
        ("포크숨겨줘", "hide_window", {"target": "포크"}),
        ("크롬 내려", "hide_window", {"target": "크롬"}),
        ("왼쪽 화면에서 크롬 숨겨줘", "hide_window", {"position": "left", "target": "크롬"}),
        ("오른쪽 크롬 화면에서 npm 열어줘", "focus_window", {"position": "right", "app": "크롬", "target": "npm"}),
        ("크롬 화면에서 구글지도 열어줘", "focus_window", {"app": "크롬", "target": "구글지도"}),
        ("크롬에서 npm 열어줘", "focus_window", {"app": "크롬", "target": "npm"}),
        ("우측 크롬 화면에서 깃허브 열어줘", "focus_window", {"position": "right", "app": "크롬", "target": "깃허브"}),
        ("좌측 화면에서 포크 열어줘", "focus_window", {"launch_if_missing": True, "position": "left", "target": "포크"}),
        ("클릭", "click", {}),
        ("클릭해줘", "click", {}),
        ("더블클릭", "click", {"count": 2}),
        ("우클릭", "click", {"button": "right"}),
        ("오른쪽 클릭", "click", {"button": "right"}),
        ("스크롤 내려", "scroll", {"direction": "down"}),
        ("위로 스크롤", "scroll", {"direction": "up"}),
        ("크롬 열어서 후쿠오카 여행지 추천 찾아줘", "web_search", {"app": "크롬", "query": "후쿠오카 여행지 추천"}),
        ("크롬 열어서 후쿠오카 여행지 추천 검색해줘", "web_search", {"app": "크롬", "query": "후쿠오카 여행지 추천"}),
        ("크롬에서 맛집 찾아줘", "web_search", {"app": "크롬", "query": "맛집"}),
        ("후쿠오카 날씨 검색해줘", "web_search", {"query": "후쿠오카 날씨"}),
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


@pytest.mark.parametrize(
    "text, args",
    [
        ("크롬 열어서 후쿠오카 여행지 추천 알아봐줘", {"app": "크롬", "query": "후쿠오카 여행지 추천"}),
        ("크롬 켜서 오사카 맛집 알려줘", {"app": "크롬", "query": "오사카 맛집"}),
        ("크롬으로 도쿄 날씨 검색해주세요", {"app": "크롬", "query": "도쿄 날씨"}),
        ("크롬 열고 부산 가볼만한 곳 찾아봐", {"app": "크롬", "query": "부산 가볼만한 곳"}),
        ("제주도 렌터카 서치해줘", {"query": "제주도 렌터카"}),
        ("우측 화면 크롬에서 후쿠오카 여행지 검색해줘", {"position": "right", "app": "크롬", "query": "후쿠오카 여행지"}),
        ("오른쪽 크롬 화면에서 후쿠오카 여행지 검색해줘", {"position": "right", "app": "크롬", "query": "후쿠오카 여행지"}),
        ("우측 화면에서 후쿠오카 여행지 검색해줘", {"position": "right", "query": "후쿠오카 여행지"}),
    ],
)
def test_search_verbs_and_openers(matcher, text, args):
    intent = matcher.match(text)
    assert intent is not None and intent.action == "web_search", text
    assert intent.args == args
