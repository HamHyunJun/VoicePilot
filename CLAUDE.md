# CLAUDE.md

이 파일은 Claude Code가 VoicePilot 저장소에서 작업할 때 참고하는 안내서다.
사용자용 설명은 [README.md](README.md), 설계와 단계별 계획은 [docs/DESIGN.md](docs/DESIGN.md)에 있다.

## 프로젝트 한 줄 요약

마우스·키보드 없이 음성만으로 macOS를 조작하는 **로컬** 음성 제어 도우미(Python).
"파일럿"(웨이크워드) → 명령 → faster-whisper로 로컬 인식 → YAML 명령 사전 매칭 → OS 조작.

## 작업 규칙 (반드시 지킬 것)

- **모든 설명, 코드 주석, 커밋 메시지, 사용자 출력 문자열은 한국어로 작성한다.**
- 음성 인식은 인터넷 없이 로컬에서 동작해야 한다. 클라우드 STT/API를 추가하지 않는다.
- **명령 인식부와 OS 조작부를 분리한다.** OS 전용 코드(pyobjc 등)는 `voicepilot/platform/<os>.py`에만 둔다.
  `actions/`, `commands/`, `assistant.py` 등은 `platform/base.py`의 `DesktopController`와 데이터 타입만 import한다.
- 새 명령 문장은 코드가 아니라 `config/commands.yaml`에 추가한다. 코드 수정은 새 **동작(action)** 이 필요할 때만 한다.
- 무거운 의존성(sounddevice, faster_whisper, pyobjc)은 함수/생성자 안에서 지연 import 한다. 단위 테스트는 이것들 없이 돌아야 한다.
- 새 기능에는 `DummyController`를 이용한 단위 테스트를 함께 추가한다. 테스트는 마이크·모델·실제 화면 없이 통과해야 한다.
- 사용자 선호: 작업 시작 시 vibe-context 도구(`get_git_delta`, `search_past_memory`)로 변경 사항과 과거 결정을 확인하고,
  끝나면 `save_session_summary`로 결정사항·아키텍처 규칙을 저장한다. 프로젝트가 등록되어 있지 않으면 `register_project`로 먼저 등록한다.

## 실행·테스트 명령

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .                      # 전체 (macOS에서는 pyobjc 포함)
pip install -r requirements-dev.txt   # 테스트용 최소 의존성

python -m pytest                      # 단위 테스트 (현재 133개, macOS에서는 macOS 전용 1개 포함)
voicepilot --text --dry-run           # 키보드 입력 + 가짜 조작부로 전체 흐름 확인 (어느 OS든 가능)
voicepilot --text                     # 키보드 입력 + 실제 macOS 창 조작
voicepilot                            # 마이크 음성 모드
voicepilot --list-windows / --list-monitors / --list-devices / -v
voicepilot --install-login-item       # 로그인 시 자동 실행(LaunchAgent) 등록, --uninstall-login-item 으로 해제
```

CI: `.github/workflows/test.yml` — ubuntu, macos 러너에서 `pytest` 실행. macOS 러너는 `tests/test_macos.py`로 pyobjc 호출도 확인한다.

## 코드 구조와 데이터 흐름

```
마이크(audio/microphone.py)
  → SpeechSegmenter(audio/segmenter.py)   에너지 VAD, 발화 단위 float32 배열
  → WhisperRecognizer(stt/whisper_engine.py)   문장
  → Assistant.handle_text(assistant.py)   상태 기계 IDLE ⇄ LISTENING
      → WakeWordDetector.detect(wakeword.py)   호출어 + 나머지 명령 분리
      → CommandMatcher.match(commands/matcher.py)   Intent(action, args, score)
      → ActionExecutor.execute(actions/executor.py)   동작 이름 → 처리 함수
          → WindowResolver / resolve_monitor (actions/targets.py)
          → DesktopController (platform/base.py) → MacOSController(platform/macos.py)
  → Feedback(feedback.py)   콘솔 출력 + afplay 효과음
조립: app.py(build_assistant, run_text_loop, run_voice_loop), 진입점: __main__.py
설정: config.py가 config/settings.yaml을 읽음, 명령은 commands/loader.py가 config/commands.yaml을 읽음
```

| 파일 | 핵심 내용 |
|---|---|
| `textutil.py` | `normalize`/`compact`, 한글 자모 분해 `to_jamo`, 자모 기반 `similarity`, 조사 제거 `strip_particle`, 한국어 숫자 `parse_korean_number` |
| `wakeword.py` | 앞 1~2어절(감탄사 1개 허용)을 호출어 후보와 자모 유사도 비교. 임계값 기본 0.75 |
| `assistant.py` | 호출어+명령 한 번에 → 즉시 실행. 호출어만 → `listen_timeout`초 LISTENING. `clock` 주입으로 테스트 |
| `commands/matcher.py` | 패턴 `{slot}` → 정규식. 점수: 정확 일치 1.0 > 정규식 일치·포함 0.9~0.99(고정 문구 비율이 클수록 높음) > 자모 유사도. `index/number/count` 슬롯은 정수로 변환 |
| `actions/targets.py` | 창 해석: 별칭 → 앱 이름/제목 일치·포함·유사도, 동점이면 앞쪽 창. 모니터: x좌표 순 정렬, left/right/center/main/next/prev/번호 |
| `actions/executor.py` | `focus_window`(포커스 + 커서를 창 중앙, `position`/`index`가 있으면 그 모니터의 창만 후보), `focus_monitor`(해당 모니터 맨 앞 창 포커스 + 커서를 모니터 중앙), `hide_window`(앱 전체 숨김, `NSRunningApplication.hide()`. 닫기·종료는 만들지 않음), `launch_app`(별칭으로 얻은 이름을 차례로 `open -a`), `click`(button/count), `scroll`(direction, 10줄). `register()`로 동작 추가 |
| `platform/macos.py` | Quartz `CGWindowListCopyWindowInfo`(창), `CGGetActiveDisplayList`(모니터), AX API로 창 Raise, `NSRunningApplication.activateWithOptions_`, `CGWarpMouseCursorPosition` + 마우스 이동 이벤트, 클릭은 `CGEventCreateMouseEvent`(클릭 횟수 필드), 스크롤은 `CGEventCreateScrollWheelEvent`(양수가 위) |
| `platform/macos_login.py` | LaunchAgent plist 생성·`launchctl bootstrap/bootout`. 표준 라이브러리만 사용. 로그는 `~/Library/Logs/VoicePilot.log` |
| `platform/macos_overlay.py` | "파일럿" 호출 시 화면 가운데(커서가 있는 모니터)에 뜨는 3D 로고 애니메이션(윤곽선을 깊이 방향으로 겹쳐 쌓은 선 비행기 + 짐벌 고리 3개, Core Animation 3D만 사용). 환경 변수 `VOICEPILOT_OVERLAY_DEBUG_DIR`를 주면 장면을 PNG로 저장해 화면 기록 권한 없이도 모양을 확인할 수 있다(오프스크린 `renderInContext`는 3D를 그리지 못함). AppKit이 메인 스레드 이벤트 루프를 요구해서 **별도 프로세스**로 띄우고, `feedback.OverlayFeedback`이 stdin으로 `show 초`/`hide`를 보낸다. 포커스·마우스 입력은 가로채지 않는다. 설정 `overlay` |
| `platform/dummy.py` | 테스트용. 샘플 모니터 2개(1920x1080, 2560x1440), 창 3개(Code, Chrome, ClaudeBoard). 호출을 `calls`에 기록 |

좌표계: 주 모니터 왼쪽 위 (0,0), y는 아래로 증가하는 전역 좌표 (Quartz의 CG 좌표와 동일. NSScreen 좌표는 쓰지 않는다).

## 지금까지의 결정사항과 이유

- **웨이크워드는 STT 결과 텍스트에서 찾는다.** 공개 한국어 웨이크워드 모델이 거의 없어서. 대신 발화마다 Whisper가 돌아 CPU를 쓴다.
  `WakeWordDetector.detect()`의 반환 형식(`WakeResult`)만 맞추면 오디오 기반 탐지기(openWakeWord 사용자 모델 등)로 교체 가능.
- **Whisper `initial_prompt`에 호출어·대표 명령을 넣는다.** "파일럿"을 다른 단어로 적는 일을 줄이기 위해.
- **VAD는 numpy 에너지 기반**으로 직접 구현했다(소음 크기 자동 추적, pre-roll 300ms, 침묵 700ms면 종료, 최대 10초). 의존성을 줄이고 테스트를 쉽게 하려고.
- **유사도는 difflib + 한글 자모 분해**로 계산한다(외부 퍼지 라이브러리 미사용). "넘어가"≈"넘어와", "파일롯"≈"파일럿" 처리.
- **구체적인 패턴 우선:** "두 번째 화면으로 넘어와"가 `{target} 넘어와`가 아닌 `{index} 화면으로 넘어와`로 가도록 고정 문구 비율로 점수를 준다.
- **한글 이름 → 영어 앱 이름은 `aliases`로 연결**한다(로마자 변환 없음). 예: 클로드보드 → ClaudeBoard.
- 창 포커스는 AX로 대상 창을 먼저 Raise한 뒤 앱을 활성화한다(같은 앱의 여러 창 중 정확한 창을 앞으로 가져오기 위해). AX 창은 위치·크기·제목으로 CG 창과 대응시킨다.
- **매칭 동점 규칙:** 점수가 같으면 슬롯이 많은 패턴이 이긴다. 슬롯이 여럿인 패턴은 마지막 글자가 달라져도("열어주") 고정 문구에서 1글자를 뺀 점수로 허용한다. 점수 비교는 반올림(소수 3자리) 기준.
- **모니터 지정 창 열기:** `{position}`(왼쪽/오른쪽/가운데/중앙/메인 → left/right/center/main)과 `{index}` 슬롯. "화면에서/화면의/모니터에서" 같은 조사 변형은 패턴을 따로 적는다. 번호 명령(`focus_window_on_monitor_index`)은 position 명령보다 위에 둔다.
- **창 해석 보강:** 별칭 키와 자모 유사도 0.85 이상이면 같은 별칭으로 본다("클롬"→"크롬"). 유사도가 모자라는 오인식("기터브" 0.77)은 별칭으로 직접 추가한다. `우측/좌측`은 `{position}` 동의어. `window_match_threshold`는 0.7 (0.6이면 chrome이 code로 잘못 매칭됨).
- **LaunchAgent 권한:** 자동 실행 시 마이크·손쉬운 사용 권한은 터미널이 아니라 실제 실행 파일(`.../Python.framework/.../Python.app`)에 줘야 한다. `.venv/bin/python` 링크는 소용없다. 파이썬 버전이 바뀌면 경로가 달라지므로 권한을 다시 주고 `--install-login-item`을 다시 실행한다.
- **창 제목은 AX로 채운다.** 화면 기록 권한이 없으면 `kCGWindowName`이 비어서, `macos.py`가 손쉬운 사용(AX) API로 같은 위치·크기의 창 제목을 채운다(같은 위치 창이 여럿이면 앞쪽부터 순서대로 짝지움). 창 제목에는 현재 탭 제목만 보이므로 가려진 탭은 위의 탭 전환으로 찾는다.
- **브라우저 탭 전환:** 창 제목에서 못 찾은 이름은 `DesktopController.list_tabs/select_tab`(크롬 계열은 JXA `osascript -l JavaScript`, `macos.py`)으로 가려진 탭까지 제목·URL로 찾는다. **앱 이름이 아니라 pid로 지정한다(`Application(pid)`)** — ClaudeBoard가 `--headless` 크롬을 띄우는 동안 이름(`tell application "Google Chrome"`)으로 지정하면 다른 인스턴스가 응답해 창 1개짜리 about:blank가 돌아왔다. 탭 창과 CG 창은 위치·크기로 짝지운다. `select_tab`이 `set index of window … to 1`과 `activate`로 창도 앞으로 가져오므로 그 뒤에 `focus_window`를 부르지 않는다(launchd 환경에서 `NSRunningApplication`이 프로세스를 못 찾는 일이 있었음). 자동화 권한이 없으면(-1743) 안내 문구가 실패 메시지에 붙는다. Safari 미지원.
- **앱 안에서 창 고르기:** `{app}` 슬롯 명령("크롬 화면에서 npm 열어줘", "오른쪽 크롬 화면에서 …")은 앱을 먼저 정하고 그 앱의 창들 중 제목으로 target을 찾는다. 꺼진 앱을 실행하지 않는다. 한글 이름이 영어 제목과 다르면 `aliases`에 추가한다.
- **별칭 값은 유사도로 비교하지 않는다.** 말한 이름만 자모 유사도로 비교하고, 별칭 값은 정확히 일치·포함만 본다(`google.com/maps`가 앱 이름 `Google Chrome`과 0.72로 비슷하다고 판단돼 지도 탭 대신 엉뚱한 크롬 창으로 이동한 적이 있음). 앱을 정한 뒤 그 앱의 창을 고를 때는 `titles_only`로 제목만 본다. URL 형태 별칭은 도메인별로 적는다(`google.co.kr/maps`).
- **슬롯 규칙:** 슬롯 두 개 사이의 공백은 반드시 있어야 나뉜다("오른쪽 크롬"이 "오"+"른쪽크롬"으로 쪼개지지 않게). `{position}` 슬롯에 알 수 없는 말이 오면 그 패턴은 맞지 않은 것으로 본다. 점수가 같으면 yaml에서 먼저 적힌 명령이 이기므로 `{position}` 명령을 `{app}` 명령보다 위에 둔다.
- 저장소가 비어 있어서 `main`에 `.gitignore`만 있는 초기 커밋을 만들고, 기능은 PR #1(`claude/project-thread-n94tha`)로 올렸다.

## 검증 상태와 알려진 제한

- Linux 클라우드와 GitHub Actions(ubuntu, macos)에서 단위 테스트 통과. macOS 러너에서 pyobjc 모니터·창 목록 조회 확인.
- macOS 실기에서 확인함: 창·모니터 전환, 마이크 음성 인식(Whisper small), 로그인 항목 등록과 기동, 손쉬운 사용 권한 적용.
- **아직 macOS 실기에서 확인하지 않은 것:** 클릭·더블클릭·우클릭·스크롤의 실제 동작(스크롤 방향이 트랙패드 설정과 맞는지 포함), 재부팅 후 자동 시작, 효과음.
  실기에서 문제가 나면 `platform/macos.py`와 `config/settings.yaml`의 `audio`/`wake` 임계값부터 확인한다.
- `config.py`의 기본 경로(`PACKAGE_ROOT/config`)는 저장소에서 `pip install -e .`로 설치했을 때를 가정한다. 일반 설치(wheel)나 앱 번들로 배포하려면 설정 파일 위치를 `~/Library/Application Support/VoicePilot` 등으로 옮겨야 한다.
- "{앱} 열어줘/보여줘/실행해줘/켜줘" 등 창 전환 명령은 전부 `launch_if_missing`: 창이 있으면 이동하고, 어느 모니터에도 창이 없으면 앱을 실행한다(`launch_app`, `open -a`). 모니터를 지정해도 실행하지만 열리는 모니터는 macOS가 정한다. 다른 모니터에 창이 있으면 실행하지 않고 실패한다.
- Whisper가 앱 이름을 다르게 적으면("크롬"→"크롭") 실패한다. 로그(`🗣` 줄)를 보고 `aliases`에 추가한다.
- 다른 Space의 전체 화면 창은 `kCGWindowListOptionOnScreenOnly` 때문에 목록에 나오지 않는다.
- macOS 권한: 마이크, 손쉬운 사용(창 Raise), 화면 기록(다른 앱 창 제목). 권한은 실행하는 터미널 앱에 부여된다(LaunchAgent로 실행할 때는 `Python.app`, 위 결정사항 참고).

## 남은 작업 (우선순위 순)

1. **macOS 실기 검증과 수정** — `voicepilot --text`로 창/모니터 전환 확인 → 음성 모드에서 인식률·VAD 임계값 조정.
2. **기본 조작 동작 추가** (클릭·스크롤·앱 실행은 완료) (`actions/executor.py`에 처리 함수, `DesktopController`에 추상 메서드, `macos.py`·`dummy.py`에 구현, `commands.yaml`에 패턴):
   - 받아쓰기: "받아써" 후 다음 발화를 그대로 입력 (`CGEventKeyboardSetUnicodeString` 또는 클립보드 붙여넣기). 상태 기계에 DICTATION 상태 추가 필요
   - 엔터, 복사/붙여넣기/실행취소 등 단축키 (`CGEventCreateKeyboardEvent` + 수정키 플래그)
   - 창 최소화/최대화 (AX `AXMinimized`, 줌 버튼 또는 `AXFullScreen`)
3. **오버레이 확장** — 호출 애니메이션은 구현됨(화면 캡처 권한이 없어 모양은 사용자 눈으로만 확인). 인식한 명령/결과 문구를 잠깐 표시하는 것은 아직 없음.
4. **메뉴 막대(트레이) 아이콘** — 켜기/끄기, 종료. `rumps` 또는 AppKit `NSStatusItem`. 음성 루프는 별도 스레드로.
5. 경량 오디오 웨이크워드 탐지기, Windows/Linux `DesktopController` 구현.

## 새 동작을 추가하는 순서 (예시)

1. 필요한 OS 기능을 `platform/base.py`의 `DesktopController`에 추상 메서드로 추가 (OS 중립적인 이름·인자).
2. `platform/dummy.py`에 기록용 구현, `platform/macos.py`에 실제 구현.
3. `actions/executor.py`에 `_새동작(ex, args) -> ActionResult` 함수를 만들고 `_DEFAULT_HANDLERS`에 등록.
4. `config/commands.yaml`에 `id`, `action`, `patterns` 추가.
5. `tests/`에 매칭 테스트(test_matcher.py)와 동작 테스트(test_actions.py) 추가 후 `python -m pytest`.
6. README의 "할 수 있는 것" 표와 "현재 지원하는 동작" 목록, docs/DESIGN.md의 단계별 계획 상태를 갱신.
