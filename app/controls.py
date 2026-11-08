"""Separate conversation and settings pages in a readable native companion panel."""
import objc
from objc import python_method
from AppKit import (
    NSApplication, NSBackingStoreBuffered, NSButton, NSColor, NSFont,
    NSMakePoint, NSMakeRect, NSPanel, NSScreen, NSScrollView, NSSegmentedControl,
    NSStatusWindowLevel, NSSwitch, NSTextField, NSImage, NSTextView, NSView,
    NSWindowStyleMaskBorderless, NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
)
from Foundation import NSObject
from glass import GlassView

WIDTH, HEIGHT = 344, 404
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


class Controls(NSObject):
    def initWithCallback_(self, callback):
        self = objc.super(Controls, self).init()
        if self is None:
            return None
        self._callback = callback
        self._lines = []
        self._window = ControlWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIDTH, HEIGHT), NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setHasShadow_(True)
        self._window.setLevel_(NSStatusWindowLevel + 1)
        self._window.setReleasedWhenClosed_(False)
        self._window.setTitle_('鲸鱼娘 · 对话与设置')
        self._window.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorFullScreenAuxiliary)
        self._view = GlassView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, HEIGHT))
        self._window.setContentView_(self._view)

        title = self._label('鲸鱼娘', INSET, 15, 240, 24, 16)
        title.setFont_(NSFont.boldSystemFontOfSize_(16))
        self._status = self._label('就绪', INSET, 42, CONTENT_WIDTH, 16, 11, muted=True)
        close = self._button('', WIDTH - INSET - 24, 14, 24, 26, b'close:')
        close.setBordered_(False)
        close.setImage_(NSImage.imageWithSystemSymbolName_accessibilityDescription_('xmark', '关闭面板'))
        self._tabs = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(INSET - 2, 68, CONTENT_WIDTH + 4, 28))
        self._tabs.setSegmentCount_(2)
        for index, label in enumerate(('对话', '设置')):
            self._tabs.setLabel_forSegment_(label, index)
            self._tabs.setWidth_forSegment_(CONTENT_WIDTH / 2, index)
        self._tabs.setTarget_(self)
        self._tabs.setAction_(b'tabChanged:')
        self._view.addSubview_(self._tabs)

        self._chat_page = PageView.alloc().initWithFrame_(NSMakeRect(INSET, 108, CONTENT_WIDTH, 230))
        self._settings_page = PageView.alloc().initWithFrame_(NSMakeRect(INSET, 108, CONTENT_WIDTH, 230))
        self._view.addSubview_(self._chat_page)
        self._view.addSubview_(self._settings_page)

        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, CONTENT_WIDTH, 188))
        scroll.setBorderType_(0)
        scroll.setDrawsBackground_(False)
        scroll.setHasVerticalScroller_(True)
        self._transcript = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, CONTENT_WIDTH - 15, 188))
        self._transcript.setEditable_(False)
        self._transcript.setDrawsBackground_(False)
        self._transcript.setFont_(NSFont.systemFontOfSize_(12.5))
        self._transcript.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(.16, .23, .31, 1))
        self._transcript.setString_('发送消息，交给 DSH 处理。')
        self._transcript.setVerticallyResizable_(True)
        self._transcript.setHorizontallyResizable_(False)
        self._transcript.textContainer().setWidthTracksTextView_(True)
        scroll.setDocumentView_(self._transcript)
        self._chat_page.addSubview_(scroll)

        self._input = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 202, CONTENT_WIDTH - 66, 26))
        self._input.setStringValue_('')
        self._input.setPlaceholderString_('输入消息…')
        self._input.setFont_(NSFont.systemFontOfSize_(13))
        self._input.setBezelStyle_(1)
        self._input.setFocusRingType_(1)
        self._input.setTarget_(self)
        self._input.setAction_(b'send:')
        self._chat_page.addSubview_(self._input)
        self._send = self._button('发送', CONTENT_WIDTH - 56, 199, 56, 30, b'send:', parent=self._chat_page)
        self._send.setBezelColor_(NSColor.systemBlueColor())
        self._send.setContentTintColor_(NSColor.whiteColor())

        self._watch = self._switch('陪看屏幕', '自动观察屏幕并回应', 0, b'watchChanged:')
        self._voice = self._switch('朗读回复', '使用当前音色说话', 46, b'voiceChanged:')
        self._label('角色形象', 0, 94, 120, 20, parent=self._settings_page)
        self._label('头像或完整姿态', 0, 115, 150, 16, 11, muted=True, parent=self._settings_page)
        self._mode = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(156, 99, 148, 28))
        self._mode.setSegmentCount_(2)
        self._mode.setLabel_forSegment_('头像', 0)
        self._mode.setLabel_forSegment_('全身', 1)
        self._mode.setTarget_(self)
        self._mode.setAction_(b'modeChanged:')
        self._settings_page.addSubview_(self._mode)
        self._autostart = self._switch('登录时启动', '同时启动 DSH 与桌宠', 138, b'autostartChanged:')
        self._button('打开角色素材', -4, 199, 146, 30, b'assets:', parent=self._settings_page)
        self._button('现在看一眼', 164, 199, 144, 30, b'look:', parent=self._settings_page)
        self._line(350)
        self._button('DSH 工作台', INSET - 4, 363, 112, 28, b'workbench:')
        self._button('退出桌宠', WIDTH - INSET - 84, 363, 88, 28, b'quit:')
        self._select_page(1)
        return self

    @python_method
    def _label(self, text, x, y, width, height, size=13, muted=False, parent=None):
        label = NSTextField.labelWithString_(text)
        label.setFrame_(NSMakeRect(x, y, width, height))
        label.setFont_(NSFont.systemFontOfSize_(size))
        rgb = (.40, .48, .55) if muted else (.16, .23, .31)
        label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(*rgb, 1))
        (parent if parent is not None else self._view).addSubview_(label)
        return label

    @python_method
    def _button(self, title, x, y, width, height, selector, parent=None):
        button = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        button.setTitle_(title)
        button.setBezelStyle_(1)
        button.setTarget_(self)
        button.setAction_(selector)
        (parent if parent is not None else self._view).addSubview_(button)
        return button

    @python_method
    def _switch(self, title, detail, y, selector):
        self._label(title, 0, y + 2, 220, 20, parent=self._settings_page)
        self._label(detail, 0, y + 23, 240, 16, 11, muted=True, parent=self._settings_page)
        switch = NSSwitch.alloc().initWithFrame_(NSMakeRect(CONTENT_WIDTH - 44, y + 7, 44, 28))
        switch.setTarget_(self)
        switch.setAction_(selector)
        self._settings_page.addSubview_(switch)
        return switch

    @python_method
    def _line(self, y):
        line = NSTextField.alloc().initWithFrame_(NSMakeRect(INSET, y, CONTENT_WIDTH, 1))
        line.setEditable_(False)
        line.setBezeled_(False)
        line.setDrawsBackground_(True)
        line.setBackgroundColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(.62, .73, .83, .38))
        self._view.addSubview_(line)

    @python_method
    def _select_page(self, index):
        self._tabs.setSelectedSegment_(index)
        self._chat_page.setHidden_(index != 0)
        self._settings_page.setHidden_(index != 1)
        self._send.setKeyEquivalent_('\r' if index == 0 else '')
        if index == 0 and self._input.isEnabled():
            self._window.makeFirstResponder_(self._input)
        else:
            self._window.makeFirstResponder_(self._tabs)

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
        self._lines.append(f'{name}：{text}')
        self._transcript.setString_('\n\n'.join(self._lines[-12:]))
        # AppKit ranges use UTF-16 code units, including supplementary emoji.
        length = len(str(self._transcript.string()).encode('utf-16-le')) // 2
        self._transcript.scrollRangeToVisible_((length, 0))

    @python_method
    def _set_busy(self, busy, status):
        self._send.setEnabled_(not busy)
        self._input.setEnabled_(not busy)
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
