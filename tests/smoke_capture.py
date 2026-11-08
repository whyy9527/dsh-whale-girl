"""Opt-in real capture proof: two visible self-owned windows vanish only from sampled pixels."""
from pathlib import Path
import sys
import threading
import time
import subprocess
import tempfile
from PIL import Image
import numpy as np
import Quartz
from AppKit import NSBackingStoreBuffered, NSColor, NSMakeRect, NSWindow
from Foundation import NSDate, NSRunLoop
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from capture import grab
from overlay import activate_app

activate_app()
windows = []
colors = [(237, 17, 203), (19, 239, 123)]
for index, color in enumerate(colors):
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(NSMakeRect(400 + index * 180, 500, 140, 100), 0, NSBackingStoreBuffered, False)
    window.setReleasedWhenClosed_(False)
    window.setBackgroundColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(*(x / 255 for x in color), 1))
    window.setLevel_(26)
    window.orderFrontRegardless()
    windows.append(window)
result = []
def capture():
    try:
        time.sleep(.3)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'visible.png'
            subprocess.run(['screencapture', '-x', '-t', 'png', str(path)], check=True)
            visible = Image.open(path).convert('RGB')
        sampled = grab()
        assert visible.size == sampled.size, (visible.size, sampled.size)
        _, displays, _ = Quartz.CGGetActiveDisplayList(32, None, None)
        frames = [Quartz.CGDisplayBounds(display) for display in displays]
        left = min(frame.origin.x for frame in frames)
        top = min(frame.origin.y for frame in frames)
        width = max(frame.origin.x + frame.size.width for frame in frames) - left
        scale = visible.width / width
        info = {item['kCGWindowNumber']: item for item in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, 0)}
        for window, color in zip(windows, colors):
            bounds = info[window.windowNumber()]['kCGWindowBounds']
            point = (round((bounds['X'] + bounds['Width'] / 2 - left) * scale),
                     round((bounds['Y'] + bounds['Height'] / 2 - top) * scale))
            before = np.array(visible.getpixel(point), dtype=float)
            after = np.array(sampled.getpixel(point), dtype=float)
            # Display color management can transform nominal sRGB values.
            assert np.linalg.norm(before - color) < 100, (color, before)
            assert np.linalg.norm(before - after) > 80, (point, before, after)
        # More than a blank/transparent image must survive the exclusion.
        assert np.asarray(sampled).std() > 10
        result.append('Visible self-owned windows excluded; underlying desktop remains.')
    except BaseException as error:
        result.append(error)
thread = threading.Thread(target=capture, daemon=True)
thread.start()
while thread.is_alive():
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(.03))
for window in windows:
    window.close()
if isinstance(result[0], BaseException):
    raise result[0]
print(result[0])
