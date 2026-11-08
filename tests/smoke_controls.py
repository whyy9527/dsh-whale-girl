"""Capture only synthetic native panel windows; never private desktop or artwork.

.venv/bin/python tests/smoke_controls.py
"""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from AppKit import NSApplication, NSAppearance, NSAppearanceNameAqua, NSAppearanceNameDarkAqua, NSMakePoint
from PyObjCTools import AppHelper
from controls import Controls
from overlay import activate_app

ROOT = Path(__file__).resolve().parents[1]
app = activate_app()
panel = Controls.alloc().initWithCallback_(lambda *_: None)
panel._configure(watch=True, voice=True, mode='fullbody', autostart=False)
panel._restore_history([
    {'name': '你', 'text': '帮我找任务的交付地点。'},
    {'name': 'DSH', 'text': '我先查一下这条任务的交付 NPC。'},
])
panel._window.setFrameOrigin_(NSMakePoint(500, 400))
states = iter([
    (NSAppearanceNameDarkAqua, 1, False, '就绪', ROOT / 'design/menu-settings.png'),
    (NSAppearanceNameDarkAqua, 0, False, '就绪', ROOT / 'design/menu-chat.png'),
    (NSAppearanceNameDarkAqua, 0, True, '正在看屏幕，可以先写好消息…', ROOT / '.local/menu-busy-dark.png'),
    (NSAppearanceNameAqua, 1, False, '就绪', ROOT / '.local/menu-settings-light.png'),
])
errors = []


def advance():
    try:
        appearance, page, busy, status, output = next(states)
    except StopIteration:
        panel._window.close()
        AppHelper.stopEventLoop()
        return
    app.setAppearance_(NSAppearance.appearanceNamed_(appearance))
    panel._select_page(page)
    panel._set_busy(busy, status, allow_draft=True)
    panel._input.setStringValue_('下一步怎么走？' if busy else '')
    panel._window.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)
    assert panel._window.effectiveAppearance().name() == NSAppearanceNameAqua
    assert panel._tabs.effectiveAppearance().name() == NSAppearanceNameAqua
    output.parent.mkdir(exist_ok=True)
    AppHelper.callLater(.4, capture, output)


def capture(output):
    try:
        subprocess.run(['screencapture', '-x', '-l', str(panel._window.windowNumber()), str(output)], check=True)
        print(output, flush=True)
        advance()
    except BaseException as error:
        errors.append(error)
        panel._window.close()
        AppHelper.stopEventLoop()


AppHelper.callAfter(advance)
AppHelper.runEventLoop()
if errors:
    raise errors[0]
print('Light/dark host appearances, both pages and editable busy draft captured.')
