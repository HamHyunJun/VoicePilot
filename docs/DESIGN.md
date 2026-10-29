# VoicePilot 설계 문서

마우스·키보드 없이 음성만으로 macOS를 조작하는 로컬 음성 제어 도우미의 설계와 단계별 계획을 정리한다.
모든 음성 처리는 인터넷 없이 로컬에서 동작한다.

## 1. 전체 구조

```
 마이크 ─▶ [audio] 발화 구간 분리(VAD)
              │  float32 PCM 조각
              ▼
          [stt] 로컬 음성 인식 (faster-whisper, 한국어)
              │  "파일럿 클로드보드로 넘어와"
              ▼
          [assistant] 상태 기계 ── 대기(IDLE) ⇄ 명령 듣는 중(LISTENING)
              │  웨이크워드 검사 → 나머지 문장 = 명령
              ▼
          [commands] 명령 사전(YAML) + 유사 문장 매칭
              │  Intent(action="focus_window", args={"target": "클로드보드"})
              ▼
          [actions] 동작 실행기 (동작 이름 → 처리 함수)
              │  OS 독립적인 요청: "이 창에 포커스", "커서를 (x, y)로"
              ▼
          [platform] OS 조작부  ── macos.py (pyobjc) / dummy.py (테스트·리눅스)

          [feedback] 인식 결과를 효과음·콘솔(추후 오버레이)로 알림
```

핵심 원칙은 **명령 인식부(audio·stt·assistant·commands)와 OS 조작부(platform)를 완전히 분리**하는 것이다.
인식부는 `DesktopController` 추상 인터페이스만 알고, macOS 전용 코드는 `voicepilot/platform/macos.py` 한 곳에만 있다.
Windows/Linux 지원은 같은 인터페이스를 구현한 파일을 추가하면 된다.

## 2. 모듈별 역할

| 모듈 | 역할 | 비고 |
|---|---|---|
| `audio/segmenter.py` | 에너지 기반 VAD로 발화 단위 분리 | 주변 소음에 맞춰 임계값 자동 보정, numpy만 사용 |
| `audio/microphone.py` | `sounddevice`로 16kHz 모노 입력 | 콜백 → 큐 |
| `stt/whisper_engine.py` | faster-whisper 로컬 인식 | `initial_prompt`에 웨이크워드·앱 이름을 넣어 인식률 향상 |
| `wakeword.py` | 문장 앞부분에서 "파일럿" 계열 호출어 탐지 | 자모 단위 유사도로 "파일롯", "파이럿"도 허용 |
| `assistant.py` | 대기/듣기 상태 전환, 시간 초과 처리 | 시계를 주입받아 단위 테스트 가능 |
| `commands/` | YAML 명령 사전 로딩, 패턴·슬롯 매칭, 유사도 매칭 | 코드 수정 없이 명령 추가 |
| `actions/` | 동작 이름 → 처리 함수 등록·실행 | 창 대상 해석(별칭 + 퍼지 매칭), 모니터 위치 해석 |
| `platform/` | `DesktopController` 인터페이스와 OS별 구현 | macOS: Quartz + Accessibility API |
| `feedback.py` | 효과음(`afplay`)·콘솔 출력 | 추후 오버레이 창 |

## 3. 웨이크워드 방식

공개된 한국어 웨이크워드 모델이 거의 없어서, 최소 버전은 **STT 결과에서 호출어를 찾는 방식**을 쓴다.

1. VAD가 발화 하나를 잘라 내면 Whisper로 인식한다.
2. 문장 앞 1~3어절이 "파일럿"과 충분히 비슷하면 호출로 본다.
3. 같은 문장에 명령이 이어지면("파일럿, 왼쪽 화면") 바로 실행하고, 호출어만 있으면 `listen_timeout`초 동안 다음 발화를 명령으로 받는다.

장점은 추가 모델·학습이 필요 없다는 것이고, 단점은 말할 때마다 Whisper를 돌리므로 CPU를 더 쓴다는 것이다.
그래서 짧은 발화는 작은 모델로 처리하고, 이후 단계에서 openWakeWord 사용자 정의 모델 같은 경량 탐지기로 교체할 수 있도록 `WakeWordDetector`를 분리해 두었다.

## 4. 명령 사전(YAML)

```yaml
commands:
  - id: focus_window
    action: focus_window
    patterns:
      - "{target} 넘어와"
      - "{target} 전환"
  - id: monitor_left
    action: focus_monitor
    args: {position: left}
    patterns: ["왼쪽 화면", "왼쪽 모니터"]
```

- `{이름}`은 슬롯이다. 슬롯 값 끝의 조사("로", "으로", "에" 등)는 자동으로 떼어 낸다.
- `{index}` 슬롯은 "1번", "두 번째" 같은 숫자 표현을 정수로 바꾼다.
- 패턴과 정확히 맞지 않아도 한글을 자모 단위로 나눈 뒤 유사도를 계산해 가장 비슷한 명령을 고른다("넘어가" ≈ "넘어와").
- 창 별칭(`aliases`)으로 "클로드보드" → `ClaudeBoard`, `Claude` 같은 실제 앱 이름을 연결한다.

## 5. macOS 창·모니터 제어

- 창 목록: `CGWindowListCopyWindowInfo` (앞쪽 창부터 정렬됨, 일반 창 레이어 0만 사용)
- 모니터 목록: `CGGetActiveDisplayList` + `CGDisplayBounds` (창 좌표와 같은 전역 좌표계)
- 포커스: `NSRunningApplication.activateWithOptions_` 로 앱 활성화 후, 손쉬운 사용(AX) API로 해당 창을 `AXRaise`
- 커서 이동: `CGWarpMouseCursorPosition` 으로 대상 창 또는 모니터의 중앙으로 이동
- "왼쪽/오른쪽/가운데 화면"은 모니터를 x 좌표 순으로 정렬해 고른다. 해당 모니터 위의 맨 앞 창에도 포커스를 준다.

필요한 권한: 마이크, 손쉬운 사용(창 포커스), 화면 기록(다른 앱의 창 제목 읽기).

## 6. 단계별 계획

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 프로젝트 골격, 설정 로딩, 플랫폼 인터페이스 | 최소 버전에 포함 |
| 2 | 마이크 입력 + VAD + faster-whisper 로컬 인식 | 최소 버전에 포함 |
| 3 | 웨이크워드 + 상태 기계 | 최소 버전에 포함 |
| 4 | YAML 명령 사전 + 유사 문장 매칭 | 최소 버전에 포함 |
| 5 | 창 전환·모니터 전환 (macOS) + 효과음 피드백 | 최소 버전에 포함 |
| 6 | 기본 조작: 클릭, 스크롤(구현됨), 받아쓰기, 엔터, 복사/붙여넣기, 최소화/최대화, 앱 실행 | 다음 단계 |
| 7 | 오버레이 피드백 창 | 다음 단계 |
| 8 | 메뉴 막대(트레이) 아이콘 켜기/끄기, 로그인 시 자동 실행(LaunchAgent, 구현됨) | 다음 단계 |
| 9 | 경량 웨이크워드 탐지기, Windows/Linux 플랫폼 구현 | 이후 |
