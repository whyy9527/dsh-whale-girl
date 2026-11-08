"""The companion's input and controls, matching the generated material study."""
import objc
from objc import python_method
from AppKit import (
    NSApplication, NSBackingStoreBuffered, NSButton, NSColor, NSFont,
    NSMakePoint, NSMakeRect, NSPanel, NSScreen, NSScrollView, NSSegmentedControl,
    NSStatusWindowLevel, NSSwitch, NSTextField, NSImage, NSTextView, NSWindowStyleMaskBorderless,
    NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowCollectionBehaviorFullScreenAuxiliary,
)
from Foundation import NSObject
from glass import GlassView

WIDTH, HEIGHT = 350, 520


class ControlWindow(NSPanel):
    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return False

    def cancelOperation_(self, _sender):
        self.orderOut_(None)


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
        self._window.setLevel_(NSStatusWindowLevel)
        self._window.setReleasedWhenClosed_(False)
        self._window.setTitle_('鲸鱼娘 · 对话与设置')
        self._window.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorFullScreenAuxiliary)
        view = GlassView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, HEIGHT))
        self._window.setContentView_(view)
        self._view = view

        self._label('鲸鱼娘', 20, 17, 270, 23, 16)
        self._status = self._label('想说什么，直接告诉我。', 20, 43, 305, 18, 11)
        self._button('看一眼', 234, 14, 68, 28, b'look:')
        close = self._button('', 305, 14, 28, 28, b'close:')
        close.setBordered_(False)
        close.setImage_(NSImage.imageWithSystemSymbolName_accessibilityDescription_('xmark', '关闭面板'))

        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(20, 72, 310, 130))
        scroll.setBorderType_(0)
        scroll.setDrawsBackground_(False)
        scroll.setHasVerticalScroller_(True)
        self._transcript = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 295, 130))
        self._transcript.setEditable_(False)
        self._transcript.setDrawsBackground_(False)
        self._transcript.setFont_(NSFont.systemFontOfSize_(12.5))
        self._transcript.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(.16, .23, .31, 1))
        self._transcript.setString_('输入文字，让我帮你处理文件、搜索网页，或使用已安装的技能。')
        self._transcript.setVerticallyResizable_(True)
        self._transcript.setHorizontallyResizable_(False)
        self._transcript.textContainer().setWidthTracksTextView_(True)
        scroll.setDocumentView_(self._transcript)
        view.addSubview_(scroll)

        self._input = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 213, 248, 32))
        self._input.setStringValue_('')
        self._input.setPlaceholderString_('想说什么…')
        self._input.setFont_(NSFont.systemFontOfSize_(13))
        self._input.setTarget_(self)
        self._input.setAction_(b'send:')
        view.addSubview_(self._input)
        self._send = self._button('发送', 276, 212, 56, 34, b'send:')
        self._send.setBezelColor_(NSColor.systemBlueColor())
        self._send.setContentTintColor_(NSColor.whiteColor())
        self._send.setKeyEquivalent_('\r')
        self._line(261)

        self._watch = self._switch('陪看', 278, b'watchChanged:')
        self._voice = self._switch('声音', 320, b'voiceChanged:')
        self._label('形象', 20, 364, 130, 23)
        self._mode = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(166, 358, 165, 30))
        self._mode.setSegmentCount_(2)
        self._mode.setLabel_forSegment_('头像', 0)
        self._mode.setLabel_forSegment_('全身', 1)
        self._mode.setTarget_(self)
        self._mode.setAction_(b'modeChanged:')
        view.addSubview_(self._mode)
        self._autostart = self._switch('登录时启动', 402, b'autostartChanged:')
        self._line(446)
        self._button('打开素材', 16, 465, 94, 31, b'assets:')
        self._button('DSH 工作台', 115, 465, 111, 31, b'workbench:')
        self._button('退出', 268, 465, 66, 31, b'quit:')
        return self

    @python_method
    def _label(self, text, x, y, width, height, size=13):
        label = NSTextField.labelWithString_(text)
        label.setFrame_(NSMakeRect(x, y, width, height))
        label.setFont_(NSFont.systemFontOfSize_(size))
        label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(.16, .23, .31, 1))
        self._view.addSubview_(label)
        return label

    @python_method
    def _button(self, title, x, y, width, height, selector):
        button = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        button.setTitle_(title)
        button.setBezelStyle_(1)
        button.setTarget_(self)
        button.setAction_(selector)
        self._view.addSubview_(button)
        return button

    @python_method
    def _switch(self, title, y, selector):
        self._label(title, 20, y + 1, 235, 23)
        switch = NSSwitch.alloc().initWithFrame_(NSMakeRect(286, y - 4, 44, 28))
        switch.setTarget_(self)
        switch.setAction_(selector)
        self._view.addSubview_(switch)
        return switch

    @python_method
    def _line(self, y):
        line = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y, 310, 1))
        line.setEditable_(False)
        line.setBezeled_(False)
        line.setDrawsBackground_(True)
        line.setBackgroundColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(.62, .73, .83, .38))
        self._view.addSubview_(line)

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
        self._window.makeFirstResponder_(self._input)

    @python_method
    def _append(self, name, text):
        self._lines.append(f'{name}：{text}')
        self._transcript.setString_('\n\n'.join(self._lines[-12:]))
        self._transcript.scrollRangeToVisible_((len(self._transcript.string()), 0))

    @python_method
    def _set_busy(self, busy, status):
        self._send.setEnabled_(not busy)
        self._input.setEnabled_(not busy)
        self._status.setStringValue_(status)

    def send_(self, _sender):
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
