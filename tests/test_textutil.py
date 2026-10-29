import pytest

from voicepilot.textutil import compact, normalize, parse_korean_number, similarity, strip_particle, to_jamo


def test_normalize_removes_punctuation_and_spaces():
    assert normalize("  파일럿,   왼쪽 화면!! ") == "파일럿 왼쪽 화면"
    assert compact("클로드 보드") == "클로드보드"


def test_to_jamo_decomposes_hangul():
    assert to_jamo("각") == "ㄱㅏㄱ"
    assert to_jamo("A가") == "Aㄱㅏ"


def test_similarity_tolerates_small_differences():
    assert similarity("넘어와", "넘어와") == 1.0
    assert similarity("넘어가", "넘어와") > 0.65
    assert similarity("파일롯", "파일럿") > 0.8
    assert similarity("파일럿", "크롬") < 0.3


@pytest.mark.parametrize(
    "word, expected",
    [("클로드보드로", "클로드보드"), ("크롬으로", "크롬"), ("슬랙에", "슬랙"), ("로", "로"), ("크롬", "크롬")],
)
def test_strip_particle(word, expected):
    assert strip_particle(word) == expected


@pytest.mark.parametrize(
    "text, expected",
    [("1번", 1), ("2", 2), ("두 번째", 2), ("첫번째", 1), ("삼번", 3), ("세 번째로", 3), ("크롬", None)],
)
def test_parse_korean_number(text, expected):
    assert parse_korean_number(text) == expected
