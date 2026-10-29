"""macOS 오버레이: "파일럿" 호출 뒤 화면 가운데에 뜨는 3D 로고 애니메이션.

AppKit은 메인 스레드의 이벤트 루프가 필요해서 음성 루프와 분리된 별도 프로세스로 띄운다.
부모(`OverlayFeedback`)가 표준 입력으로 한 줄씩 명령을 보낸다.

    show [초]   나타난다. 초가 지나면 스스로 사라진다(부모가 hide를 못 보내도 화면에 남지 않도록).
    hide        사라진다
    (입력 끝)   프로세스를 끝낸다 (부모가 죽으면 파이프가 닫혀 같이 끝난다)

배경 틀 없이 로고만 보이고, 포커스를 가져가지 않으며 마우스 입력도 받지 않는다.
마우스 커서가 있는 모니터의 가운데에 뜬다.

로고: 입체감 있는 선 비행기(윤곽선을 깊이 방향으로 겹쳐 쌓음)를 3개의 회전하는 고리(짐벌)가 감싼다.
Core Animation의 3D 변환(원근 + CATransformLayer)만 쓰므로 추가 의존성이 없다.
디버깅: 환경 변수 VOICEPILOT_OVERLAY_DEBUG_DIR가 있으면 나타난 뒤 몇 장면을 그 폴더에 PNG로 저장한다.
"""

from __future__ import annotations

import math
import os
import sys

_DEFAULT_SECONDS = 6.0
_SIZE = 340.0
_TAU = 2 * math.pi

# 로고 색 (어두운 배경과 밝은 배경 모두에서 보이도록 채도 있는 푸른색 계열)
_CYAN = (0.36, 0.78, 1.0)
_INDIGO = (0.50, 0.56, 1.0)
_VIOLET = (0.80, 0.48, 1.0)

# 위에서 본 비행기 윤곽(0~1 좌표, 코가 위). 한 줄로 이어서 그린다.
_PLANE_OUTLINE = [
    (0.50, 0.98), (0.58, 0.72), (0.56, 0.66), (0.98, 0.30), (0.98, 0.20), (0.57, 0.40), (0.56, 0.22),
    (0.76, 0.07), (0.76, 0.02), (0.53, 0.10), (0.50, 0.05),
    (0.47, 0.10), (0.24, 0.02), (0.24, 0.07), (0.44, 0.22), (0.43, 0.40), (0.02, 0.20), (0.02, 0.30),
    (0.44, 0.66), (0.42, 0.72),
]
_PLANE_SIZE = 104.0
_SLAB_LAYERS = 7  # 윤곽선을 몇 장 겹쳐 두께를 만들지
_SLAB_GAP = 3.2  # 겹 사이 간격(깊이)
# (반지름, 색, 기울기(rad), 뒤집히는 축, 한 바퀴 도는 시간(초, 음수면 반대 방향), 위성이 한 바퀴 도는 시간(초))
_GIMBAL = [
    (66.0, _CYAN, 0.0, "x", 7.0, 3.2),
    (80.0, _INDIGO, math.radians(60), "y", -9.0, 4.4),
    (94.0, _VIOLET, math.radians(-35), "x", 11.0, 5.6),
]


def parse_command(line: str) -> tuple[str, float] | None:
    """한 줄을 (명령, 초)로 해석한다. 모르는 줄은 None."""
    parts = line.split()
    if not parts:
        return None
    if parts[0] == "hide":
        return "hide", 0.0
    if parts[0] == "show":
        try:
            return "show", float(parts[1]) if len(parts) > 1 else _DEFAULT_SECONDS
        except ValueError:
            return None
    return None


class _Scene:  # pragma: no cover - macOS 화면에서만 확인 가능
    """로고 레이어 묶음. `start()`로 애니메이션을 시작하고 `stop()`으로 멈춘다."""

    def __init__(self, size: float = _SIZE):
        from AppKit import NSColor
        from Quartz import (
            CALayer,
            CAShapeLayer,
            CATransformLayer,
            CATransform3DMakeRotation,
            CATransform3DMakeTranslation,
            CGPathAddArc,
            CGPathAddEllipseInRect,
            CGPathAddLineToPoint,
            CGPathCloseSubpath,
            CGPathCreateMutable,
            CGPathMoveToPoint,
            CGRectMake,
        )

        self.animated_strokes: list = []  # 그려지는 애니메이션을 줄 선
        self.spinners: list = []  # (레이어, 한 바퀴 시간)
        self.tumblers: list = []  # (레이어, 키 경로, 한 바퀴 시간)
        self.slab: list = []  # (레이어, 최종 z)
        self.ripples: list = []

        def rgb(color, alpha: float = 1.0):
            return NSColor.colorWithSRGBRed_green_blue_alpha_(color[0], color[1], color[2], alpha).CGColor()

        def holder(layer_cls=CATransformLayer):
            layer = layer_cls.layer()
            layer.setBounds_(CGRectMake(0, 0, 0, 0))  # 크기 0: 회전 중심이 정확히 가운데가 된다
            return layer

        def stroke(path, bounds_size: float, color, width: float, alpha: float = 1.0, glow: float = 0.0):
            layer = CAShapeLayer.layer()
            layer.setBounds_(CGRectMake(0, 0, bounds_size, bounds_size))
            layer.setPosition_((0, 0))
            layer.setPath_(path)
            layer.setFillColor_(None)
            layer.setStrokeColor_(rgb(color, alpha))
            layer.setLineWidth_(width)
            layer.setLineCap_("round")
            layer.setLineJoin_("round")
            if glow:
                layer.setShadowColor_(rgb(color))
                layer.setShadowRadius_(glow)
                layer.setShadowOpacity_(0.9)
                layer.setShadowOffset_((0, 0))
            return layer

        # 원근: 가까운 것은 크게, 먼 것은 작게
        self.stage = CALayer.layer()
        self.stage.setBounds_(CGRectMake(0, 0, size, size))
        self.stage.setPosition_((size / 2, size / 2))
        perspective = CATransform3DMakeTranslation(0, 0, 0)
        perspective.m34 = -1.0 / 650.0
        self.stage.setSublayerTransform_(perspective)

        world = holder()
        world.setPosition_((size / 2, size / 2))
        self.stage.addSublayer_(world)
        self.world = world

        # 화면 평면으로 퍼져 나가는 얇은 파동 (듣고 있다는 느낌)
        for _ in range(2):
            path = CGPathCreateMutable()
            CGPathAddEllipseInRect(path, None, CGRectMake(0, 0, 120, 120))
            ripple = stroke(path, 120, _CYAN, 1.5, 0.8, glow=5.0)
            ripple.setOpacity_(0.0)
            ripple.setZPosition_(-30.0)
            world.addSublayer_(ripple)
            self.ripples.append(ripple)

        # 짐벌 고리 3개: 기울어진 채로 뒤집히며 돌고, 고리 위의 위성이 고리를 따라 돈다
        for radius, color, tilt, axis, flip_seconds, orbit_seconds in _GIMBAL:
            base = holder()
            base.setPosition_((0, 0))
            base.setTransform_(CATransform3DMakeRotation(tilt, 0, 0, 1))
            world.addSublayer_(base)
            tumble = holder()
            tumble.setPosition_((0, 0))
            base.addSublayer_(tumble)
            self.tumblers.append((tumble, f"transform.rotation.{axis}", flip_seconds))

            spin = holder(CALayer)
            spin.setPosition_((0, 0))
            tumble.addSublayer_(spin)
            self.spinners.append((spin, orbit_seconds))

            path = CGPathCreateMutable()
            CGPathAddArc(path, None, radius, radius, radius - 1.5, math.pi / 2, math.pi / 2 - _TAU, True)
            ring = stroke(path, radius * 2, color, 2.2, 0.95, glow=6.0)
            spin.addSublayer_(ring)
            self.animated_strokes.append(ring)

            dot_path = CGPathCreateMutable()
            CGPathAddEllipseInRect(dot_path, None, CGRectMake(0, 0, 9, 9))
            dot = CAShapeLayer.layer()
            dot.setBounds_(CGRectMake(0, 0, 9, 9))
            dot.setPosition_((radius - 1.5, 0))  # 고리 오른쪽 끝
            dot.setPath_(dot_path)
            dot.setFillColor_(rgb((1, 1, 1)))
            dot.setShadowColor_(rgb(color))
            dot.setShadowRadius_(7.0)
            dot.setShadowOpacity_(1.0)
            dot.setShadowOffset_((0, 0))
            spin.addSublayer_(dot)

        # 가운데 비행기: 윤곽선을 깊이 방향으로 겹쳐 쌓아 두께를 만든다. 좌우로 기울고 위아래로 떠다닌다.
        self.float_holder = holder()
        self.float_holder.setPosition_((0, 0))
        world.addSublayer_(self.float_holder)
        self.tilt = holder()
        self.tilt.setPosition_((0, 0))
        self.float_holder.addSublayer_(self.tilt)
        self.roll = holder()
        self.roll.setPosition_((0, 0))
        self.tilt.addSublayer_(self.roll)

        path = CGPathCreateMutable()
        for i, (px, py) in enumerate(_PLANE_OUTLINE):
            (CGPathMoveToPoint if i == 0 else CGPathAddLineToPoint)(path, None, px * _PLANE_SIZE, py * _PLANE_SIZE)
        CGPathCloseSubpath(path)
        mid = (_SLAB_LAYERS - 1) / 2
        for i in range(_SLAB_LAYERS):
            z = (i - mid) * _SLAB_GAP
            outer = i in (0, _SLAB_LAYERS - 1)
            layer = stroke(
                path, _PLANE_SIZE, _CYAN, 3.2 if outer else 1.6, 1.0 if outer else 0.38, glow=6.0 if outer else 0.0
            )
            if i == _SLAB_LAYERS - 1:
                layer.setFillColor_(rgb(_CYAN, 0.12))  # 앞면은 살짝 채워 유리처럼 보이게 한다
            layer.setZPosition_(z)
            self.roll.addSublayer_(layer)
            self.slab.append((layer, z))
            if outer:
                self.animated_strokes.append(layer)

    def start(self) -> None:
        from Quartz import (
            CAAnimationGroup,
            CABasicAnimation,
            CACurrentMediaTime,
            CAMediaTimingFunction,
            CASpringAnimation,
        )

        inf = float("inf")

        def basic(key: str, a: float, b: float, seconds: float, *, repeat: float = inf, reverse: bool = False,
                  timing: str = "linear", begin: float = 0.0):
            anim = CABasicAnimation.animationWithKeyPath_(key)
            anim.setFromValue_(a)
            anim.setToValue_(b)
            anim.setDuration_(seconds)
            anim.setRepeatCount_(repeat)
            anim.setAutoreverses_(reverse)
            anim.setTimingFunction_(CAMediaTimingFunction.functionWithName_(timing))
            if begin:
                anim.setBeginTime_(CACurrentMediaTime() + begin)
                anim.setFillMode_("backwards")  # 시작 전에는 처음 상태로 둔다
            return anim

        # 비행기: 좌우로 기울고(roll), 앞뒤로 살짝 끄덕이고(tilt), 위아래로 떠다닌다. 주기가 달라 반복해도 단조롭지 않다.
        self.roll.addAnimation_forKey_(basic("transform.rotation.y", -0.95, 0.95, 2.8, reverse=True, timing="easeInEaseOut"), "roll")
        self.tilt.addAnimation_forKey_(basic("transform.rotation.x", -0.30, 0.30, 3.9, reverse=True, timing="easeInEaseOut"), "tilt")
        self.float_holder.addAnimation_forKey_(basic("position.y", -5.0, 5.0, 2.3, reverse=True, timing="easeInEaseOut"), "float")

        # 고리: 각자 다른 축으로 뒤집히며 돌고, 위성은 고리를 따라 돈다
        for layer, key, seconds in self.tumblers:
            layer.addAnimation_forKey_(basic(key, 0.0, math.copysign(_TAU, seconds), abs(seconds)), "tumble")
        for layer, seconds in self.spinners:
            layer.addAnimation_forKey_(basic("transform.rotation.z", 0.0, _TAU, seconds), "spin")

        # 등장: 선이 그려지고, 겹쳐 쌓인 윤곽이 하나로 모인 상태에서 깊이 방향으로 펼쳐진다
        for i, layer in enumerate(self.animated_strokes):
            layer.addAnimation_forKey_(basic("strokeEnd", 0.0, 1.0, 0.9, repeat=1, timing="easeInEaseOut", begin=0.12 * i), "draw")
        for layer, z in self.slab:
            layer.addAnimation_forKey_(basic("zPosition", 0.0, z, 0.9, repeat=1, timing="easeOut", begin=0.5), "unfold")

        # 화면 평면으로 퍼지는 파동 (선이 다 그려진 뒤부터)
        for i, ripple in enumerate(self.ripples):
            group = CAAnimationGroup.animation()
            group.setAnimations_([basic("transform.scale", 1.0, 2.4, 2.6, repeat=1), basic("opacity", 0.7, 0.0, 2.6, repeat=1)])
            group.setDuration_(2.6)
            group.setRepeatCount_(inf)
            group.setBeginTime_(CACurrentMediaTime() + 1.1 + i * 1.3)
            group.setFillMode_("backwards")
            ripple.addAnimation_forKey_(group, "ripple")

        pop = CASpringAnimation.animationWithKeyPath_("transform.scale")
        pop.setFromValue_(0.6)
        pop.setToValue_(1.0)
        pop.setMass_(1.0)
        pop.setStiffness_(170.0)
        pop.setDamping_(12.0)
        pop.setDuration_(pop.settlingDuration())
        self.world.addAnimation_forKey_(pop, "pop")

    def stop(self) -> None:
        for layer in (
            [self.world, self.roll, self.tilt, self.float_holder]
            + [t[0] for t in self.tumblers]
            + [s[0] for s in self.spinners]
            + self.animated_strokes
            + [s[0] for s in self.slab]
            + self.ripples
        ):
            layer.removeAllAnimations()


def run() -> int:  # pragma: no cover - macOS 화면에서만 확인 가능
    from AppKit import (
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSBackingStoreBuffered,
        NSColor,
        NSEvent,
        NSMakeRect,
        NSPanel,
        NSScreen,
        NSView,
    )
    from PyObjCTools import AppHelper

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # Dock 아이콘 없음

    # 스타일: 테두리 없음(0) | 활성화하지 않는 패널(1 << 7)
    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, _SIZE, _SIZE), (1 << 7), NSBackingStoreBuffered, False
    )
    panel.setOpaque_(False)
    panel.setBackgroundColor_(NSColor.clearColor())  # 틀 없이 로고만 보이게 한다
    panel.setHasShadow_(False)
    panel.setIgnoresMouseEvents_(True)
    panel.setLevel_(25)  # NSStatusWindowLevel: 다른 창 위
    panel.setCollectionBehavior_((1 << 0) | (1 << 4) | (1 << 8))  # 모든 Space, 고정, 전체 화면 앱 위에서도
    panel.setAlphaValue_(0.0)

    root = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, _SIZE, _SIZE))
    root.setWantsLayer_(True)
    panel.setContentView_(root)
    scene = _Scene()
    root.layer().addSublayer_(scene.stage)

    state = {"generation": 0}

    def center_on_cursor_screen() -> None:
        mouse = NSEvent.mouseLocation()
        screens = NSScreen.screens()
        screen = next(
            (s for s in screens if _contains(s.frame(), mouse.x, mouse.y)),
            NSScreen.mainScreen() or screens[0],
        )
        f = screen.frame()
        panel.setFrameOrigin_((f.origin.x + (f.size.width - _SIZE) / 2, f.origin.y + (f.size.height - _SIZE) / 2))

    def show(seconds: float) -> None:
        state["generation"] += 1
        generation = state["generation"]
        center_on_cursor_screen()
        scene.stop()
        scene.start()
        panel.orderFrontRegardless()
        panel.animator().setAlphaValue_(1.0)
        AppHelper.callLater(seconds, lambda: hide() if state["generation"] == generation else None)
        debug_dir = os.environ.get("VOICEPILOT_OVERLAY_DEBUG_DIR")
        if debug_dir:
            for i, delay in enumerate((0.4, 1.0, 1.8, 2.8)):
                AppHelper.callLater(delay, lambda i=i: _snapshot(panel, os.path.join(debug_dir, f"frame{i}.png")))

    def hide() -> None:
        state["generation"] += 1
        generation = state["generation"]
        panel.animator().setAlphaValue_(0.0)

        def finish() -> None:
            if state["generation"] == generation:  # 그 사이 다시 나타났다면 건드리지 않는다
                panel.orderOut_(None)
                scene.stop()

        AppHelper.callLater(0.3, finish)

    def read_commands() -> None:
        for line in sys.stdin:
            command = parse_command(line)
            if command is None:
                continue
            name, seconds = command
            AppHelper.callAfter(show if name == "show" else hide, *([seconds] if name == "show" else []))
        AppHelper.callAfter(app.terminate_, None)  # 부모가 끝남

    import threading

    threading.Thread(target=read_commands, daemon=True).start()
    app.run()
    return 0


def _snapshot(panel, path: str) -> None:  # pragma: no cover - 디버깅용
    """이 프로세스가 가진 창은 화면 기록 권한 없이도 캡처할 수 있다. 배경은 투명하게 저장된다."""
    from AppKit import NSBitmapImageRep
    from Quartz import (
        CGRectNull,
        CGWindowListCreateImage,
        kCGWindowImageBoundsIgnoreFraming,
        kCGWindowListOptionIncludingWindow,
    )

    image = CGWindowListCreateImage(
        CGRectNull, kCGWindowListOptionIncludingWindow, panel.windowNumber(), kCGWindowImageBoundsIgnoreFraming
    )
    if image is not None:
        rep = NSBitmapImageRep.alloc().initWithCGImage_(image)
        rep.representationUsingType_properties_(4, None).writeToFile_atomically_(path, True)


def _contains(frame, x: float, y: float) -> bool:  # pragma: no cover
    return frame.origin.x <= x < frame.origin.x + frame.size.width and frame.origin.y <= y < frame.origin.y + frame.size.height


if __name__ == "__main__":
    sys.exit(run())
