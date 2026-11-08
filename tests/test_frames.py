"""Prove that time alone cannot produce screen commentary or empty grid tiles."""
import base64
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from PIL import Image, ImageDraw
from frames import FramePicker, KeptFrame
from main import Brain


class FrameTests(unittest.TestCase):
    def test_startup_and_hours_of_static_screen_never_send(self):
        picker = FramePicker(batch_size=2)
        frame = Image.new('RGB', (640, 360), 'white')
        with patch('frames.time.monotonic', return_value=0):
            self.assertIsNone(picker.offer(frame))
        with patch('frames.time.monotonic', return_value=7200):
            for _ in range(20):
                self.assertIsNone(picker.offer(frame))
        self.assertEqual(picker.kept, [])

    def test_small_high_contrast_patch_is_not_a_scene_change(self):
        picker = FramePicker(batch_size=2)
        frame = Image.new('RGB', (640, 360), 'white')
        picker.offer(frame)
        changed = frame.copy()
        ImageDraw.Draw(changed).rectangle((0, 0, 110, 100), fill='black')
        for _ in range(20):
            self.assertIsNone(picker.offer(changed))
        self.assertEqual(picker.kept, [])

    def test_accepted_change_does_not_repeat_and_incomplete_batch_never_times_out(self):
        picker = FramePicker(batch_size=2)
        white = Image.new('RGB', (640, 360), 'white')
        black = Image.new('RGB', (640, 360), 'black')
        picker.offer(white)
        self.assertIsNone(picker.offer(black))
        with patch('frames.time.monotonic', return_value=999999999):
            self.assertIsNone(picker.offer(black))
        self.assertEqual(len(picker.kept), 1)
        batch = picker.offer(white)
        self.assertEqual(len(batch), 2)
        self.assertIsNone(picker.offer(white))
        picker.reset()
        self.assertIsNone(picker.offer(black))  # resume establishes a fresh baseline

    def test_manual_single_frame_and_partial_batches_have_no_blank_grid(self):
        brain = Brain({}, None, None)
        for count in (1, 3):
            batch = [KeptFrame(Image.new('RGB', (64, 36), 'white'), i, '12:00:00') for i in range(count)]
            payload = brain._payload(batch)
            self.assertFalse(payload['grid'])
            self.assertEqual(len(payload['frames']), count)
            with Image.open(io.BytesIO(base64.b64decode(payload['frames'][0]['data']))) as image:
                self.assertEqual(image.size, (64, 36))
        batch = [KeptFrame(Image.new('RGB', (64, 36), 'white'), i, '12:00:00') for i in range(9)]
        self.assertTrue(brain._payload(batch)['grid'])


if __name__ == '__main__':
    unittest.main()
