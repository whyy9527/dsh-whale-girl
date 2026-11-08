import json
from pathlib import Path
import struct
import sys
import time
import unittest
import zlib

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from game import decode, MARKER


def panel(state, scale=4, offset=(19, 23), corrupt=False):
    body = json.dumps(state, ensure_ascii=False).encode()
    packet = b'WGB1' + struct.pack('>HII', len(body), 7, zlib.adler32(body)) + body
    if corrupt:
        packet = packet[:-1] + bytes([packet[-1] ^ 1])
    bits = np.unpackbits(np.frombuffer(packet, dtype=np.uint8))
    bits = np.pad(bits, (0, -len(bits) % 6)).reshape(-1, 6)
    values = bits @ (2 ** np.arange(5, -1, -1))
    palette = np.array([24, 93, 162, 231])
    colors = np.zeros((2048, 3), dtype=np.uint8)
    colors[:8] = MARKER
    chart = np.arange(64)
    colors[8:72] = palette[np.array([chart // 16, chart // 4 % 4, chart % 4]).T]
    colors[72:72 + len(values)] = palette[np.array([values // 16, values // 4 % 4, values % 4]).T]
    cells = Image.fromarray(colors.reshape(32, 64, 3)).resize((64 * scale, 32 * scale), Image.Resampling.NEAREST)
    image = Image.new('RGB', (cells.width + offset[0] + 20, cells.height + offset[1] + 20), (38, 42, 56))
    image.paste(cells, offset)
    return image


class GameTests(unittest.TestCase):
    def test_unicode_snapshot_survives_scale_position_and_gamma(self):
        state = {'version': 1, 'sampledAt': 100, 'zone': '艾尔文森林', 'selectedQuest': {'id': 7, 'title': '找“人”\\新线索'}}
        for scale in (2, 3, 4, 6, 8):
            image = panel(state, scale=scale)
            # Calibration follows the same per-channel display transform as data.
            pixels = np.asarray(image).astype(float) / 255
            pixels = pixels @ np.array([[.9, .05, .03], [.07, .9, .07], [.03, .05, .9]])
            image = Image.fromarray(np.round(pixels ** np.array([1.3, .8, 1.1]) * 255).astype(np.uint8))
            self.assertEqual(decode(image, now=102), {**state, 'sequence': 7})

    def test_corruption_occlusion_staleness_and_absence_never_reuse_a_position(self):
        state = {'version': 1, 'sampledAt': 100, 'x': 42, 'y': 31}
        self.assertIsNone(decode(panel(state, corrupt=True), now=101))
        self.assertIsNone(decode(panel(state), now=106))
        self.assertIsNone(decode(panel(state), now=95))
        self.assertIsNone(decode(panel(state).crop((0, 0, 100, 100)), now=101))
        self.assertIsNone(decode(Image.new('RGB', (500, 300), 'white'), now=101))


if __name__ == '__main__':
    unittest.main()
