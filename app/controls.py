"""Readable native companion controls, implemented from design/menu-study.png."""
import objc
from objc import python_method
from AppKit import (
    NSApplication, NSAppearance, NSAppearanceNameAqua, NSBackingStoreBuffered,
    NSBezierPath, NSButton, NSColor, NSControlSizeLarge, NSFont, NSFontAttributeName,
    NSForegroundColorAttributeName, NSImage, NSImageView, NSImageLeft, NSImageRight, NSImageScaleProportionallyUpOrDown,
    NSMakePoint, NSMakeRect, NSMakeSize, NSPanel, NSParagraphStyleAttributeName,
    NSMutableParagraphStyle, NSScreen, NSScrollView, NSSegmentedControl,
    NSStatusWindowLevel, NSSwitch, NSTextField, NSTextView, NSView,
    NSWindowStyleMaskBorderless, NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
)
from Foundation import NSObject, NSAttributedString, NSMutableAttributedString
from glass import GlassView, color
from theme import PANEL_INK, PANEL_MUTED, PANEL_ACCENT, PANEL_DIVIDER

WIDTH, HEIGHT = 360, 488
INSET = 20
CONTENT_WIDTH = WIDTH - INSET * 2


class ControlWindow(NSPanel):
    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return False

    def cancelOperation_(self, _sender):
        self.orderOut_(None)


class PageView(NSView):
    def isFlipped(self):
        return True


class ControlCard(PageView):
    def drawRect_(self, _rect):
        bounds = self.bounds()
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(.5, .5, bounds.size.width - 1, bounds.size.height - 1), 10, 10)
        NSColor.whiteColor().setFill()
        path.fill()
        color(PANEL_DIVIDER).setStroke()
        path.setLineWidth_(.7)
        path.stroke()


class ControlDivider(PageView):
    def drawRect_(self, _rect):
        color(PANEL_DIVIDER).setFill()
        NSBezierPath.fillRect_(self.bounds())


class Controls(NSObject):
    def initWithCallback_(self, callback):
        self = objc.super(Controls, self).init()
        if self is None:
            return None
        self._callback = callback
        self._lines = []
        self._window = ControlWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIDTH, HEIGHT), NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False)
        # The opaque light surface and every native descendant share one appearance.
        # System DarkAqua must not put white labels on this light custom material.
        self._window.setAppearance_(NSAppearance.appearanceNamed_(NSAppearanceNameAqua))
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setHasShadow_(True)
        self._window.setLevel_(NSStatusWindowLevel + 1)
        self._window.setReleasedWhenClosed_(False)
        self._window.setTitle_('鲸鱼娘 · 对话与设置')
        self._window.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorFullScreenAuxiliary)
        self._view = GlassView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, HEIGHT))
        self._window.setContentView_(self._view)

        mark = NSImageView.alloc().initWithFrame_(NSMakeRect(INSET, 24, 28, 28))
        mark.setImage_(NSImage.imageWithSystemSymbolName_accessibilityDescription_('water.waves', None))
        mark.setContentTintColor_(color(PANEL_ACCENT))
        mark.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        mark.setAccessibilityElement_(False)
        self._view.addSubview_(mark)
        title = self._label('鲸鱼娘', 60, 17, 220, 25, 17)
        title.setFont_(NSFont.systemFontOfSize_weight_(17, .5))
        self._status = self._label('就绪', 60, 43, 240, 17, 11.5, muted=True)
        self._close = self._button('', WIDTH - INSET - 28, 17, 28, 28, b'close:', plain=True)
        self._close.setImage_(NSImage.imageWithSystemSymbolName_accessibilityDescription_('xmark', '关闭面板'))
        self._close.setAccessibilityLabel_('关闭面板')
        self._close.setToolTip_('关闭面板 · Esc')

        self._tabs = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(INSET - 2, 72, CONTENT_WIDTH + 4, 32))
        self._tabs.setSegmentCount_(2)
        self._tabs.setControlSize_(NSControlSizeLarge)
        self._tabs.setFont_(NSFont.systemFontOfSize_weight_(14, .35))
        self._tabs.setSelectedSegmentBezelColor_(color(PANEL_ACCENT))
        self._tabs.setAccessibilityLabel_('面板页面')
        for index, label in enumerate(('对话', '设置')):
            self._tabs.setLabel_forSegment_(label, index)
            self._tabs.setWidth_forSegment_(CONTENT_WIDTH / 2, index)
        self._tabs.setTarget_(self)
        self._tabs.setAction_(b'tabChanged:')
        self._view.addSubview_(self._tabs)

        self._chat_page = PageView.alloc().initWithFrame_(NSMakeRect(INSET, 118, CONTENT_WIDTH, 316))
        self._settings_page = PageView.alloc().initWithFrame_(NSMakeRect(INSET, 118, CONTENT_WIDTH, 316))
        self._view.addSubview_(self._chat_page)
        self._view.addSubview_(self._settings_page)

        self._card(self._chat_page, 0, 254)
        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(12, 12, CONTENT_WIDTH - 24, 230))
        scroll.setBorderType_(0)
        scroll.setDrawsBackground_(False)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        self._transcript = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, CONTENT_WIDTH - 39, 230))
        self._transcript.setEditable_(False)
        self._transcript.setDrawsBackground_(False)
        self._transcript.setFont_(NSFont.systemFontOfSize_(14))
        self._transcript.setTextColor_(color(PANEL_INK))
        self._transcript.setTextContainerInset_(NSMakeSize(0, 0))
        self._transcript.setString_('输入消息，开始对话。')
        self._transcript.setVerticallyResizable_(True)
        self._transcript.setHorizontallyResizable_(False)
        self._transcript.textContainer().setWidthTracksTextView_(True)
        self._transcript.setAccessibilityLabel_('对话记录')
        scroll.setDocumentView_(self._transcript)
        self._chat_page.addSubview_(scroll)

        self._input = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 280, CONTENT_WIDTH - 68, 30))
        self._input.setStringValue_('')
        self._input.setFont_(NSFont.systemFontOfSize_(13))
        self._input.setTextColor_(color(PANEL_INK))
        self._input.setBackgroundColor_(NSColor.whiteColor())
        self._input.setPlaceholderAttributedString_(NSAttributedString.alloc().initWithString_attributes_(
            '输入消息…', {NSForegroundColorAttributeName: color(PANEL_MUTED), NSFontAttributeName: NSFont.systemFontOfSize_(13)}))
        self._input.setBezelStyle_(1)
        self._input.setAccessibilityLabel_('消息')
        self._input.setTarget_(self)
        self._input.setAction_(b'send:')
        self._chat_page.addSubview_(self._input)
        self._send = self._button('发送', CONTENT_WIDTH - 60, 276, 60, 36, b'send:', parent=self._chat_page)
        self._send.setBezelColor_(color(PANEL_ACCENT))
        self._send.setContentTintColor_(NSColor.whiteColor())

        self._section('陪伴', 0)
        self._card(self._settings_page, 24, 96)
        self._watch = self._switch('陪看屏幕', '有新线索时轻声提醒', 24, b'watchChanged:')
        self._separator(self._settings_page, 12, 72, CONTENT_WIDTH - 24)
        self._voice = self._switch('朗读回复', '使用当前音色', 72, b'voiceChanged:')
        self._section('外观与启动', 136)
        self._card(self._settings_page, 160, 108)
        self._label('角色形象', 12, 168, 140, 20, parent=self._settings_page)
        self._mode = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(CONTENT_WIDTH - 152, 164, 140, 28))
        self._mode.setSegmentCount_(2)
        self._mode.setLabel_forSegment_('头像', 0)
        self._mode.setLabel_forSegment_('全身', 1)
        self._mode.setFont_(NSFont.systemFontOfSize_(13))
        self._mode.setSelectedSegmentBezelColor_(color(PANEL_ACCENT))
        self._mode.setAccessibilityLabel_('角色形象')
        self._mode.setTarget_(self)
        self._mode.setAction_(b'modeChanged:')
        self._settings_page.addSubview_(self._mode)
        self._separator(self._settings_page, 12, 196, CONTENT_WIDTH - 24)
        self._autostart = self._switch('登录时启动', '登录 Mac 时打开鲸鱼娘', 196, b'autostartChanged:')
        self._separator(self._settings_page, 12, 240, CONTENT_WIDTH - 24)
        self._label('角色素材', 12, 246, 140, 18, 12.5, parent=self._settings_page)
        assets = self._button('打开文件夹', CONTENT_WIDTH - 126, 240, 116, 28, b'assets:', parent=self._settings_page, plain=True)
        assets.setFont_(NSFont.systemFontOfSize_(11.5))
        assets.setImage_(NSImage.imageWithSystemSymbolName_accessibilityDescription_('chevron.right', None))
        assets.setImagePosition_(NSImageRight)
        assets.setAccessibilityLabel_('打开当前形象的素材文件夹')
        self._look = self._button('现在看一眼', 0, 280, CONTENT_WIDTH, 36, b'look:', parent=self._settings_page)
        self._look.setImage_(NSImage.imageWithSystemSymbolName_accessibilityDescription_('viewfinder', None))
        self._look.setImagePosition_(NSImageLeft)

        self._separator(self._view, INSET, 444, CONTENT_WIDTH)
        self._workbench = self._button('工作台', INSET - 6, 452, 100, 26, b'workbench:', plain=True)
        self._workbench.setImage_(NSImage.imageWithSystemSymbolName_accessibilityDescription_('arrow.up.forward.square', None))
        self._workbench.setImagePosition_(NSImageLeft)
        self._workbench.setAccessibilityLabel_('打开 DSH 工作台')
        self._quit = self._button('退出', WIDTH - INSET - 50, 452, 56, 26, b'quit:', plain=True)
        self._quit.setToolTip_('退出鲸鱼娘')
        self._select_page(1)
        return self

    @python_method
    def _label(self, text, x, y, width, height, size=14, muted=False, parent=None):
        label = NSTextField.labelWithString_(text)
        label.setFrame_(NSMakeRect(x, y, width, height))
        label.setFont_(NSFont.systemFontOfSize_(size))
        label.setTextColor_(color(PANEL_MUTED if muted else PANEL_INK))
        (parent if parent is not None else self._view).addSubview_(label)
        return label

    @python_method
    def _button(self, title, x, y, width, height, selector, parent=None, plain=False):
        button = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        button.setTitle_(title)
        button.setBezelStyle_(1)
        button.setFont_(NSFont.systemFontOfSize_(13))
        button.setImageHugsTitle_(True)
        button.setContentTintColor_(color(PANEL_INK))
        if plain:
            button.setBordered_(False)
        else:
            button.setControlSize_(NSControlSizeLarge)
        button.setTarget_(self)
        button.setAction_(selector)
        (parent if parent is not None else self._view).addSubview_(button)
        return button

    @python_method
    def _section(self, text, y):
        label = self._label(text, 2, y, CONTENT_WIDTH, 18, 11.5, muted=True, parent=self._settings_page)
        label.setFont_(NSFont.systemFontOfSize_weight_(11.5, .35))

    @python_method
    def _card(self, parent, y, height):
        card = ControlCard.alloc().initWithFrame_(NSMakeRect(0, y, CONTENT_WIDTH, height))
        parent.addSubview_(card)

    @python_method
    def _separator(self, parent, x, y, width):
        line = ControlDivider.alloc().initWithFrame_(NSMakeRect(x, y, width, .7))
        parent.addSubview_(line)

    @python_method
    def _switch(self, title, detail, y, selector):
        self._label(title, 12, y + 5, 226, 20, parent=self._settings_page)
        self._label(detail, 12, y + 26, 240, 16, 12, muted=True, parent=self._settings_page)
        switch = NSSwitch.alloc().initWithFrame_(NSMakeRect(CONTENT_WIDTH - 54, y + 10, 44, 28))
        switch.setTarget_(self)
        switch.setAction_(selector)
        switch.setAccessibilityLabel_(title)
        switch.setAccessibilityHelp_(detail)
        self._settings_page.addSubview_(switch)
        return switch

    @python_method
    def _select_page(self, index):
        self._tabs.setSelectedSegment_(index)
        self._chat_page.setHidden_(index != 0)
        self._settings_page.setHidden_(index != 1)
        self._send.setKeyEquivalent_('\r' if index == 0 else '')
        if index == 0 and self._input.isEnabled():
            self._window.makeFirstResponder_(self._input)
        else:
            self._window.makeFirstResponder_(None)

    @python_method
    def _configure(self, watch=True, voice=True, mode='portrait', autostart=False):
        self._watch.setState_(int(watch))
        self._voice.setState_(int(voice))
        self._mode.setSelectedSegment_(int(mode == 'fullbody'))
        self._autostart.setState_(int(autostart))

    @python_method
    def _toggle(self, anchor, screen=None):
        if self._window.isVisible():
            self._window.orderOut_(None)
            return
        screen = screen or NSScreen.mainScreen()
        bounds = screen.visibleFrame()
        x = anchor.origin.x + anchor.size.width + 14
        if x + WIDTH > bounds.origin.x + bounds.size.width:
            x = anchor.origin.x - WIDTH - 14
        x = max(bounds.origin.x, x)
        y = max(bounds.origin.y, min(anchor.origin.y + anchor.size.height - HEIGHT, bounds.origin.y + bounds.size.height - HEIGHT))
        self._window.setFrameOrigin_(NSMakePoint(x, y))
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self._window.makeKeyAndOrderFront_(None)
        self._select_page(self._tabs.selectedSegment())

    @python_method
    def _append(self, name, text):
        self._lines.append(f'{"鲸鱼娘" if name == "DSH" else name}：{text}')
        self._render_transcript()

    @python_method
    def _restore_history(self, entries):
        self._lines = [f"{'鲸鱼娘' if item['name'] == 'DSH' else item['name']}：{item['text']}" for item in entries]
        self._render_transcript()

    @python_method
    def _render_transcript(self):
        lines = self._lines[-12:]
        content = '\n\n'.join(lines)
        paragraph = NSMutableParagraphStyle.alloc().init()
        paragraph.setLineSpacing_(4)
        rich = NSMutableAttributedString.alloc().initWithString_attributes_(content, {
            NSFontAttributeName: NSFont.systemFontOfSize_(14),
            NSForegroundColorAttributeName: color(PANEL_INK),
            NSParagraphStyleAttributeName: paragraph,
        })
        offset = 0
        for line in lines:
            sender = line.partition('：')[0] + '：'
            units = len(sender.encode('utf-16-le')) // 2
            rich.addAttributes_range_({NSFontAttributeName: NSFont.systemFontOfSize_weight_(12, .45),
                NSForegroundColorAttributeName: color(PANEL_ACCENT)}, (offset, units))
            offset += len((line + '\n\n').encode('utf-16-le')) // 2
        self._transcript.textStorage().setAttributedString_(rich)
        length = len(str(self._transcript.string()).encode('utf-16-le')) // 2
        self._transcript.scrollRangeToVisible_((length, 0))

    @python_method
    def _set_busy(self, busy, status, allow_draft=False):
        self._send.setEnabled_(not busy)
        self._input.setEnabled_(not busy or allow_draft)
        self._status.setStringValue_(status)
        self._status.setToolTip_(status)

    def tabChanged_(self, _sender):
        self._select_page(self._tabs.selectedSegment())

    def send_(self, _sender):
        if self._chat_page.isHidden() or not self._send.isEnabled():
            return
        text = str(self._input.stringValue()).strip()
        if text:
            self._input.setStringValue_('')
            self._callback('send', text)

    def look_(self, _sender):
        self._callback('look', None)

    def close_(self, _sender):
        self._window.orderOut_(None)

    def watchChanged_(self, _sender):
        self._callback('watch', bool(self._watch.state()))

    def voiceChanged_(self, _sender):
        self._callback('voice', bool(self._voice.state()))

    def modeChanged_(self, _sender):
        self._callback('mode', 'fullbody' if self._mode.selectedSegment() == 1 else 'portrait')

    def autostartChanged_(self, _sender):
        self._callback('autostart', bool(self._autostart.state()))

    def assets_(self, _sender):
        self._callback('expressions', None)

    def workbench_(self, _sender):
        self._callback('workbench', None)

    def quit_(self, _sender):
        self._callback('quit', None)
