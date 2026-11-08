"""浮在所有窗口上的鲸鱼娘：圆形底座 + 透明出框人物 + 一个气泡。

用 Cocoa 而不是 tkinter，是因为需要一个"真·逐像素透明"的无边框窗口：
tkinter 在 macOS 上只能整窗调 alpha，做不到圆形头像旁边只有气泡、其余全透。
"""

from __future__ import annotations

import math

import objc
from objc import python_method
from AppKit import (
    NSAttributedString,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSImage,
    NSImageScaleProportionallyUpOrDown,
    NSImageView,
    NSLineBreakByWordWrapping,
    NSMakePoint,
    NSMakeRect,
    NSMakeSize,
    NSEvent,
    NSMutableParagraphStyle,
    NSParagraphStyleAttributeName,
    NSShadow,
    NSStatusWindowLevel,
    NSStatusBar,
    NSVariableStatusItemLength,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSStringDrawingUsesLineFragmentOrigin,
)
from Foundation import NSString, NSTimer, NSObject
from glass import paint_glass
from controls import Controls

BUBBLE_PADDING = 14
BUBBLE_RADIUS = 16
BUBBLE_TAIL = 10
AVATAR_GAP = 18  # 气泡小尖角伸出来的距离
MAX_BUBBLE_WIDTH = 300
FONT_SIZE = 13.5
BUBBLE_TEXT = (0.14, 0.21, 0.31, 1.0)


def _color(r: float, g: float, b: float, a: float = 1.0) -> NSColor:
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, a)


def _paragraph_style() -> NSMutableParagraphStyle:
    style = NSMutableParagraphStyle.alloc().init()
    style.setLineSpacing_(2.0)
    return style


class WhaleWindow(NSWindow):
    """无边框浮窗：不抢焦点，但会跟着你切 Space。"""

    def canBecomeKeyWindow(self) -> bool:
        return False

    def canBecomeMainWindow(self) -> bool:
        return False


class BubbleView(NSView):
    """圆角气泡，左边一个小尖角指向头像。"""

    def initWithFrame_(self, frame):
        self = objc.super(BubbleView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._label = NSTextField.alloc().initWithFrame_(NSMakeRect(BUBBLE_PADDING, BUBBLE_PADDING, 10, 10))
        self._label.setBezeled_(False)
        self._label.setDrawsBackground_(False)
        self._label.setEditable_(False)
        self._label.setSelectable_(False)
        self._label.setTextColor_(_color(*BUBBLE_TEXT))
        self._label.setFont_(NSFont.systemFontOfSize_(FONT_SIZE))
        cell = self._label.cell()
        cell.setWraps_(True)
        cell.setLineBreakMode_(NSLineBreakByWordWrapping)
        self.addSubview_(self._label)
        return self

    def setText_(self, text: str) -> None:
        self._text = text or ''
        attributes = {
            NSFontAttributeName: NSFont.systemFontOfSize_(FONT_SIZE),
            NSForegroundColorAttributeName: _color(*BUBBLE_TEXT),
            NSParagraphStyleAttributeName: _paragraph_style(),
        }
        attributed = NSAttributedString.alloc().initWithString_attributes_(self._text, attributes)
        self._label.setAttributedStringValue_(attributed)

    def text(self) -> str:
        return getattr(self, '_text', '')

    def drawRect_(self, _rect):
        bounds = self.bounds()

        shadow = NSShadow.alloc().init()
        shadow.setShadowColor_(_color(0.10, 0.18, 0.25, 0.18))
        shadow.setShadowBlurRadius_(16.0)
        shadow.setShadowOffset_(NSMakeSize(0, -3))
        shadow.set()

        # One closed contour gives the body and curved tail a continuous rim and fill.
        left, right, bottom, top = BUBBLE_TAIL + 1, bounds.size.width - 1, 1, bounds.size.height - 1
        radius, mid = min(BUBBLE_RADIUS, (top - bottom) / 2), bounds.size.height / 2
        k = radius * .55228475
        tail_half = min(7, (top - bottom) / 2 - radius - 1)
        path = NSBezierPath.bezierPath()
        path.moveToPoint_(NSMakePoint(left + radius, bottom))
        path.lineToPoint_(NSMakePoint(right - radius, bottom))
        path.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(right, bottom + radius), NSMakePoint(right - radius + k, bottom), NSMakePoint(right, bottom + radius - k))
        path.lineToPoint_(NSMakePoint(right, top - radius))
        path.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(right - radius, top), NSMakePoint(right, top - radius + k), NSMakePoint(right - radius + k, top))
        path.lineToPoint_(NSMakePoint(left + radius, top))
        path.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(left, top - radius), NSMakePoint(left + radius - k, top), NSMakePoint(left, top - radius + k))
        path.lineToPoint_(NSMakePoint(left, mid + tail_half))
        path.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(2, mid - 1), NSMakePoint(left, mid + 2), NSMakePoint(left - 5, mid))
        path.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(2, mid - 3), NSMakePoint(.5, mid - 1), NSMakePoint(.5, mid - 3))
        path.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(left, mid - tail_half), NSMakePoint(left - 3, mid - 3), NSMakePoint(left, mid - 5))
        path.lineToPoint_(NSMakePoint(left, bottom + radius))
        path.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(left + radius, bottom), NSMakePoint(left, bottom + radius - k), NSMakePoint(left + radius - k, bottom))
        path.closePath()
        paint_glass(bounds, outline=path)
        NSShadow.alloc().init().set()

    @python_method
    def _layout_label(self, width: float, height: float) -> None:
        self._label.setFrame_(
            NSMakeRect(
                BUBBLE_PADDING + BUBBLE_TAIL,
                BUBBLE_PADDING,
                max(10.0, width - BUBBLE_PADDING * 2 - BUBBLE_TAIL),
                max(10.0, height - BUBBLE_PADDING * 2),
            )
        )


class DragView(NSView):
    """Only the character is interactive: drag to move; click/right-click for controls."""

    def initWithOverlay_(self, overlay):
        self = objc.super(DragView, self).initWithFrame_(NSMakeRect(0, 0, 10, 10))
        if self is None:
            return None
        self._overlay = overlay
        self._drag_start = None
        self._window_origin = None
        self._moved = False
        return self

    def acceptsFirstMouse_(self, _event) -> bool:
        return True

    def mouseDown_(self, event) -> None:
        self._drag_start = NSEvent.mouseLocation()
        self._window_origin = self.window().frame().origin
        self._moved = False

    def mouseDragged_(self, event) -> None:
        if self._drag_start is None:
            return
        current = NSEvent.mouseLocation()
        dx = current.x - self._drag_start.x
        dy = current.y - self._drag_start.y
        if abs(dx) > 2 or abs(dy) > 2:
            self._moved = True
        if self._moved:
            self.window().setFrameOrigin_(NSMakePoint(self._window_origin.x + dx, self._window_origin.y + dy))

    def mouseUp_(self, event) -> None:
        moved = self._moved
        if moved:
            self.mouseDragged_(event)
        self._drag_start = None
        if moved:
            origin = self.window().frame().origin
            self._overlay._notify_moved(int(origin.x), int(origin.y))
        else:
            self._overlay._popup_menu()
        self._overlay._finish_drag()

    def rightMouseDown_(self, _event) -> None:
        self._overlay._popup_menu()


class Overlay(NSObject):
    """窗口 + 头像 + 气泡的控制器。所有方法都必须在主线程调用。"""

    def initWithArt_(self, art_paths):
        self = objc.super(Overlay, self).init()
        if self is None:
            return None
        self._art = dict(art_paths)
        self._images = {mood: NSImage.alloc().initWithContentsOfFile_(str(path)) for mood, path in art_paths.items()}
        self._art_timer = None
        self._avatar_size = 132
        self._avatar_height = 132
        self._visible = False
        self._hide_timer = None
        self._origin = (48, 240)
        self._bubble_hide_after = 12.0
        self._on_menu = None
        self._mood = 'idle'
        self._pending_comment = None
        self._hide_pending = False

        self._window = WhaleWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, self._avatar_size, self._avatar_size),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setLevel_(NSStatusWindowLevel)
        self._window.setHasShadow_(False)
        self._window.setReleasedWhenClosed_(False)
        self._window.setIgnoresMouseEvents_(False)
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorStationary
        )

        container = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, self._avatar_size, self._avatar_size))
        container.setWantsLayer_(True)
        self._window.setContentView_(container)

        self._avatar = NSImageView.alloc().initWithFrame_(NSMakeRect(0, 0, self._avatar_size, self._avatar_size))
        self._avatar.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        self._avatar.setWantsLayer_(True)
        layer = self._avatar.layer()
        layer.setMasksToBounds_(False)
        layer.setShadowColor_(_color(0, 0, 0, 0.55).CGColor())
        layer.setShadowOpacity_(1.0)
        layer.setShadowRadius_(14.0)
        layer.setShadowOffset_(NSMakeSize(0, -3))
        container.addSubview_(self._avatar)

        self._bubble = BubbleView.alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
        self._bubble.setHidden_(True)
        container.addSubview_(self._bubble)

        self._drag = DragView.alloc().initWithOverlay_(self)
        container.addSubview_(self._drag)

        self._controls = Controls.alloc().initWithCallback_(self._dispatch)
        self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self._status_item.button().setTitle_('鲸')
        self._status_item.button().setTarget_(self)
        self._status_item.button().setAction_(b'statusClicked:')
        self._set_mood('idle')
        return self

    # ---------- 对外 ----------

    @python_method
    def _configure(self, *, size, x, y, bubble_hide, always_on_top, mode="portrait", fullbody_size=360):
        self._avatar_size = round(fullbody_size * .75) if mode == "fullbody" else int(size)
        self._avatar_height = int(fullbody_size) if mode == "fullbody" else int(size)
        self._bubble_hide_after = float(bubble_hide)
        self._avatar.setFrame_(NSMakeRect(0, 0, self._avatar_size, self._avatar_height))
        self._window.setLevel_(NSStatusWindowLevel if always_on_top else 0)
        self._resize_to_avatar()
        self._window.setFrameOrigin_(NSMakePoint(int(x), int(y)))
        self._window.orderFrontRegardless()

    @python_method
    def _show_comment(self, text, mood='idle'):
        """在气泡里显示一句话；已经显示着就原地换字。"""
        text = str(text or '').strip()
        if text == '':
            return
        if self._drag._drag_start is not None:
            self._pending_comment = (text, mood)
            return
        self._set_mood(mood)
        self._bubble.setText_(text)
        self._bubble.setHidden_(False)
        self._bubble.setNeedsDisplay_(True)
        total_width, total_height, bubble_height = self._measure(text)
        self._apply_layout(total_width, total_height, bubble_height)
        self._window.orderFrontRegardless()
        self._visible = True
        self._schedule_hide()

    @python_method
    def _hide_comment(self):
        if self._drag._drag_start is not None:
            self._hide_pending = True
            return
        if not self._visible:
            return
        self._visible = False
        self._bubble.setHidden_(True)
        self._resize_to_avatar()

    @python_method
    def _notify_moved(self, x, y):
        y += int(self._avatar.frame().origin.y)
        self._origin = (x, y)
        if self._on_menu:
            self._on_menu('moved', (x, y))

    @python_method
    def _finish_drag(self):
        pending, self._pending_comment = self._pending_comment, None
        hide, self._hide_pending = self._hide_pending, False
        if pending:
            self._show_comment(*pending)
        elif hide:
            self._hide_comment()

    @python_method
    def _set_callback(self, handler):
        self._on_menu = handler

    # ---------- 布局 ----------

    @python_method
    def _measure(self, text):
        style = _paragraph_style()
        attributes = {NSFontAttributeName: NSFont.systemFontOfSize_(FONT_SIZE), NSParagraphStyleAttributeName: style}
        rect = NSString.stringWithString_(text).boundingRectWithSize_options_attributes_(
            NSMakeSize(MAX_BUBBLE_WIDTH - BUBBLE_PADDING * 2, 10000.0),
            NSStringDrawingUsesLineFragmentOrigin,
            attributes,
        )
        text_height = math.ceil(rect.size.height) + 2
        bubble_height = text_height + BUBBLE_PADDING * 2
        bubble_width = min(MAX_BUBBLE_WIDTH, math.ceil(rect.size.width) + BUBBLE_PADDING * 2 + 6) + BUBBLE_TAIL
        total_height = max(self._avatar_height, bubble_height)
        total_width = self._avatar_size + AVATAR_GAP + bubble_width
        return total_width, total_height, bubble_height

    @python_method
    def _apply_layout(self, total_width, total_height, bubble_height):
        frame = self._window.frame()
        anchor_y = frame.origin.y + self._avatar.frame().origin.y
        avatar_y = (total_height - self._avatar_height) / 2.0
        self._window.setFrame_display_(
            NSMakeRect(frame.origin.x, anchor_y - avatar_y, total_width, total_height), True
        )
        container = self._window.contentView()
        container.setFrame_(NSMakeRect(0, 0, total_width, total_height))

        self._avatar.setFrame_(NSMakeRect(0, avatar_y, self._avatar_size, self._avatar_height))

        bubble_width = total_width - self._avatar_size - AVATAR_GAP
        bubble_y = (total_height - bubble_height) / 2.0
        self._bubble.setFrame_(NSMakeRect(self._avatar_size + AVATAR_GAP, bubble_y, bubble_width, bubble_height))
        self._bubble._layout_label(bubble_width, bubble_height)

        self._drag.setFrame_(self._avatar.frame())

    @python_method
    def _resize_to_avatar(self):
        frame = self._window.frame()
        anchor_y = frame.origin.y + self._avatar.frame().origin.y
        size = self._avatar_size
        self._window.setFrame_display_(NSMakeRect(frame.origin.x, anchor_y, size, self._avatar_height), True)
        self._window.contentView().setFrame_(NSMakeRect(0, 0, size, self._avatar_height))
        self._avatar.setFrame_(NSMakeRect(0, 0, size, self._avatar_height))
        self._drag.setFrame_(NSMakeRect(0, 0, size, self._avatar_height))
        self._bubble.setHidden_(True)

    # ---------- 表情 / 定时 ----------

    @python_method
    def _set_mood(self, mood):
        self._mood = mood if mood in self._art else 'idle'
        image = self._images.get(self._mood)
        if image is not None:
            self._avatar.setImage_(image)

    @python_method
    def _reload_art(self, paths):
        if paths == self._art:
            return
        images = dict(self._images)
        for mood, path in paths.items():
            if path != self._art.get(mood):
                image = NSImage.alloc().initWithContentsOfFile_(str(path))
                if image is None:
                    raise OSError(f"Cannot load avatar: {path}")
                images[mood] = image
        self._images, self._art = images, dict(paths)
        self._set_mood(self._mood)

    @python_method
    def _schedule_hide(self):
        if self._hide_timer is not None:
            self._hide_timer.invalidate()
        self._hide_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            max(4.0, self._bubble_hide_after), self, b'timerFired:', None, False
        )

    def timerFired_(self, _timer):
        self._hide_timer = None
        self._hide_comment()

    # ---------- 菜单 ----------

    @python_method
    def _popup_menu(self):
        frame = self._window.frame()
        avatar = self._avatar.frame()
        anchor = NSMakeRect(frame.origin.x + avatar.origin.x, frame.origin.y + avatar.origin.y, avatar.size.width, avatar.size.height)
        self._controls._toggle(anchor, self._window.screen())

    @python_method
    def _dispatch(self, action, value=None):
        if self._on_menu:
            self._on_menu(action, value)

    def statusClicked_(self, _sender):
        self._popup_menu()

    @python_method
    def _close_controls(self):
        self._controls._window.close()
        NSStatusBar.systemStatusBar().removeStatusItem_(self._status_item)


def activate_app():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    return app
