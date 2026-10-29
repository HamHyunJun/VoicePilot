"""말로 지정한 대상을 실제 창·모니터로 해석한다."""

from __future__ import annotations

from ..platform.base import Monitor, Rect, Window
from ..textutil import compact, similarity, strip_particle

_ALIAS_SIMILARITY = 0.85


class WindowResolver:
    """"클로드보드" 같은 이름을 열린 창 하나로 해석한다.

    1. 별칭 사전으로 실제 앱 이름/창 제목 후보를 얻는다.
    2. 각 창의 앱 이름과 제목에 대해 포함 여부·자모 유사도로 점수를 매긴다.
    3. 점수가 같으면 앞쪽(최근에 쓴) 창을 고른다.
    """

    def __init__(self, aliases: dict[str, list[str]] | None = None, threshold: float = 0.7):
        self.aliases = {compact(k): v for k, v in (aliases or {}).items()}
        self.threshold = threshold

    def candidates_for(self, spoken: str) -> list[str]:
        return [name for name, _ in self._names(spoken)]

    def _names(self, spoken: str) -> list[tuple[str, bool]]:
        """(이름, 유사도 비교 허용 여부). 말한 이름만 유사도로 비교하고, 별칭 값은 정확히 일치·포함만 본다.

        별칭 값까지 유사도로 비교하면 "google.com/maps"가 앱 이름 "Google Chrome"과 비슷하다고 판단되는 식으로 엉뚱한 창이 뽑힌다.
        """
        spoken_names = {spoken, strip_particle(spoken)}
        aliased: set[str] = set()
        for name in spoken_names:
            aliased.update(self.aliases.get(compact(name), []))
            # 인식기가 살짝 다르게 적은 이름도 별칭으로 본다 ("클롬" → "크롬").
            for key, values in self.aliases.items():
                if similarity(compact(name), key) >= _ALIAS_SIMILARITY:
                    aliased.update(values)
        names = [(n, True) for n in spoken_names] + [(n, False) for n in aliased - spoken_names]
        return [(n, fuzzy) for n, fuzzy in names if compact(n)]

    def best_title(self, spoken: str, titles: list[str]) -> int | None:
        """제목 목록에서 말한 이름과 가장 비슷한 제목의 위치. 점수가 같으면 앞쪽이 이긴다."""
        names = self._names(spoken)
        best, best_score = None, 0.0
        for i, title in enumerate(titles):
            score = max(_score(name, _title_only(title), fuzzy) for name, fuzzy in names)
            if score > best_score:
                best, best_score = i, score
        return best if best_score >= self.threshold else None

    def resolve(self, spoken: str, windows: list[Window], titles_only: bool = False) -> Window | None:
        """titles_only면 앱 이름은 보지 않고 창 제목만 비교한다 (이미 앱을 정한 뒤 그 앱의 창을 고를 때)."""
        names = self._names(spoken)
        best: Window | None = None
        best_score = 0.0
        for window in windows:  # 앞쪽 창부터 보므로 동점이면 먼저 본 창이 남는다.
            score = max(_score(name, window, fuzzy, use_app=not titles_only) for name, fuzzy in names)
            if score > best_score:
                best, best_score = window, score
        return best if best_score >= self.threshold else None


def _title_only(title: str) -> Window:
    return Window(0, "", title, 0, Rect(0, 0, 0, 0))


def _score(name: str, window: Window, fuzzy: bool = True, use_app: bool = True) -> float:
    needle = compact(name)
    scores = []
    for hay, weight in ((window.app_name if use_app else "", 1.0), (window.title, 0.95)):
        h = compact(hay)
        if not h:
            continue
        if needle == h:
            scores.append(1.0 * weight)
        elif len(needle) >= 2 and needle in h:
            # 제목 일부만 말한 경우 ("깃허브" 별칭 → "GitHub - Chrome")
            scores.append(0.85 * weight)
        elif fuzzy:
            scores.append(similarity(needle, h) * weight)
    return max(scores, default=0.0)


def sort_monitors(monitors: list[Monitor]) -> list[Monitor]:
    """왼쪽에서 오른쪽, 같은 x면 위에서 아래 순으로 정렬한다."""
    return sorted(monitors, key=lambda m: (m.bounds.x, m.bounds.y))


def monitor_of_point(monitors: list[Monitor], x: float, y: float) -> Monitor | None:
    for m in monitors:
        if m.bounds.contains(x, y):
            return m
    return None


def resolve_monitor(
    monitors: list[Monitor],
    position: str | None = None,
    index: int | None = None,
    current: Monitor | None = None,
) -> Monitor | None:
    """위치("left", "right", "center", "main", "next", "prev") 또는 1부터 시작하는 번호로 모니터를 고른다."""
    ordered = sort_monitors(monitors)
    if not ordered:
        return None
    if index is not None:
        return ordered[index - 1] if 1 <= index <= len(ordered) else None

    if position == "left":
        return ordered[0]
    if position == "right":
        return ordered[-1]
    if position == "center":
        return ordered[len(ordered) // 2]
    if position == "main":
        return next((m for m in ordered if m.is_main), ordered[0])
    if position in ("next", "prev"):
        if current is None or current not in ordered:
            return ordered[0]
        step = 1 if position == "next" else -1
        return ordered[(ordered.index(current) + step) % len(ordered)]
    return None


def topmost_window_on(monitor: Monitor, windows: list[Window]) -> Window | None:
    """창 중심이 해당 모니터 안에 있는 창 중 가장 앞쪽 창."""
    for w in windows:
        if monitor.bounds.contains(*w.bounds.center):
            return w
    return None
