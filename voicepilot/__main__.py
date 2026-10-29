"""명령줄 진입점: `python -m voicepilot` 또는 `voicepilot`."""

from __future__ import annotations

import argparse
import logging
import sys

from .app import build_assistant, run_text_loop, run_voice_loop
from .config import load_settings
from .feedback import ConsoleFeedback, OverlayFeedback
from .platform import PlatformError, create_controller


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="voicepilot", description="로컬 음성 제어 데스크톱 도우미")
    p.add_argument("--config", help="설정 파일 경로 (기본: config/settings.yaml)")
    p.add_argument("--text", action="store_true", help="마이크 대신 키보드로 문장을 입력해 테스트")
    p.add_argument("--dry-run", action="store_true", help="실제 창을 움직이지 않는 가짜 조작부 사용")
    p.add_argument("--list-windows", action="store_true", help="인식 가능한 창 목록 출력")
    p.add_argument("--list-monitors", action="store_true", help="모니터 목록 출력 (왼쪽부터)")
    p.add_argument("--list-devices", action="store_true", help="마이크 장치 목록 출력")
    p.add_argument("--install-login-item", action="store_true", help="로그인할 때 자동으로 실행되도록 등록 (macOS)")
    p.add_argument("--uninstall-login-item", action="store_true", help="로그인 시 자동 실행 해제 (macOS)")
    p.add_argument("-v", "--verbose", action="store_true", help="자세한 로그 출력")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.list_devices:
        import sounddevice as sd

        print(sd.query_devices())
        return 0

    if args.install_login_item or args.uninstall_login_item:
        from .platform import macos_login

        try:
            if args.install_login_item:
                path = macos_login.install(args.config)
                print(f"등록했습니다: {path}\n로그는 {macos_login.log_path()} 에서 볼 수 있습니다.")
            elif macos_login.uninstall():
                print("자동 실행을 해제했습니다.")
            else:
                print("등록된 자동 실행이 없습니다.")
        except PlatformError as e:
            print(f"오류: {e}", file=sys.stderr)
            return 1
        return 0

    try:
        settings = load_settings(args.config)
        controller = create_controller(dry_run=args.dry_run)
    except (PlatformError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1

    if args.list_windows:
        for w in controller.list_windows():
            print(f"[{w.id}] {w.app_name} — {w.title or '(제목 없음)'}  {w.bounds}")
        return 0
    if args.list_monitors:
        from .actions.targets import sort_monitors

        for i, m in enumerate(sort_monitors(controller.list_monitors()), 1):
            print(f"{i}번 모니터{' (메인)' if m.is_main else ''}: {m.bounds}")
        return 0

    feedback = None
    if settings.overlay and not args.text and sys.platform == "darwin":
        feedback = OverlayFeedback(ConsoleFeedback(sound=settings.sound), timeout=settings.wake.listen_timeout)
    assistant = build_assistant(settings, controller, feedback)
    try:
        if args.text:
            run_text_loop(assistant)
        else:
            run_voice_loop(assistant, settings)
    except KeyboardInterrupt:
        print("\n종료합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
