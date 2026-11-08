import base64
import io
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from PIL import Image
from frames import KeptFrame
from main import Brain
from lifecycle import InstanceLock
from tts import Speaker


class Overlay:
    def __init__(self):
        self.comments = []
    def _show_comment(self, *args):
        self.comments.append(args)


class Voice:
    def __init__(self):
        self.lines = []
    def speak_async(self, line):
        self.lines.append(line)
    def stop(self):
        pass


class DesktopTests(unittest.TestCase):
    def test_frames_are_decodable_jpegs(self):
        brain = Brain({'sendMode': 'frames'}, Overlay(), Voice())
        batch = [KeptFrame(Image.new('RGB', (32, 32), 'blue'), 0, '12:00:00')]
        payload = brain._payload(batch)
        with Image.open(io.BytesIO(base64.b64decode(payload['frames'][0]['data']))) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertEqual(image.size, (32, 32))

    def test_screen_batch_enters_shared_conversation_without_a_second_http_client(self):
        overlay, voice = Overlay(), Voice()
        brain = Brain({}, overlay, voice)
        delivered = []
        brain.submit_screen = lambda payload, generation: delivered.append((payload, generation))
        frame = KeptFrame(Image.new('RGB', (32, 32), 'white'), 0, '12:00:00')
        with patch('main.AppHelper.callAfter', side_effect=lambda callback, *args: callback(*args)):
            brain._send([frame], force=True)
        self.assertEqual(len(delivered), 1)
        self.assertFalse(delivered[0][0]['grid'])
        self.assertEqual(overlay.comments, [])
        self.assertEqual(voice.lines, [])

    def test_pause_discards_response_already_queued_for_main_thread(self):
        overlay, voice = Overlay(), Voice()
        brain = Brain({}, overlay, voice)
        generation = brain.pause_generation
        brain.toggle_pause()
        brain.toggle_pause()
        brain._deliver_comment('old', 'idle', generation)
        self.assertEqual(overlay.comments, [])
        self.assertEqual(voice.lines, [])
        brain._deliver_comment('new', 'happy', brain.pause_generation)
        self.assertEqual(voice.lines, ['new'])
        brain.stop()
        brain._deliver_comment('late', 'happy', brain.pause_generation)
        self.assertEqual(voice.lines, ['new'])

    def test_pause_blocks_automatic_reply_but_manual_look_can_still_reply(self):
        overlay, voice = Overlay(), Voice()
        brain = Brain({'watchEnabled': False}, overlay, voice)
        brain._deliver_comment('automatic', 'idle', 0)
        self.assertEqual(voice.lines, [])
        brain._deliver_comment('manual', 'idle', 0, manual=True)
        self.assertEqual(voice.lines, ['manual'])
        brain.pause_generation += 1
        brain._deliver_comment('stale manual', 'idle', 0, manual=True)
        self.assertEqual(voice.lines, ['manual'])

    def test_pause_captures_nothing_until_resumed(self):
        brain = Brain({}, Overlay(), Voice(), demo=True)
        brain.toggle_pause()
        with patch.object(brain, '_demo_frame') as capture:
            brain.start()
            time.sleep(0.4)
            brain.stop()
            brain.join()
            capture.assert_not_called()

    def test_instance_lock_released_without_removing_inode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'overlay.pid'
            first, second = InstanceLock(path), InstanceLock(path)
            self.assertTrue(first.acquire())
            first.claim()
            self.assertFalse(second.acquire())
            first.close()
            self.assertTrue(second.acquire())
            second.close()
            self.assertTrue(path.exists())

    def test_latest_speech_replaces_pending_and_drops_stale_synthesis(self):
        with tempfile.TemporaryDirectory() as directory:
            speaker = Speaker({'tts': {'engine': 'local'}}, '', Path(directory))
            entered, release = threading.Event(), threading.Event()
            synthesized, played = [], []
            def synth(text):
                synthesized.append(text)
                if text == 'first':
                    entered.set()
                    self.assertTrue(release.wait(3))
                return Path(directory) / f'{text}.wav'
            speaker._synth = synth
            speaker._start_playback = lambda path: played.append(path.stem)
            try:
                speaker.speak_async('first')
                self.assertTrue(entered.wait(3))
                speaker.speak_async('second')
                speaker.speak_async('third')
                release.set()
                speaker.wait_idle()
                self.assertEqual(synthesized, ['first', 'third'])
                self.assertEqual(played, ['third'])
                speaker.speak_async('cancelled')
                speaker.stop()
            finally:
                release.set()
                speaker.shutdown()
            self.assertFalse(speaker._thread.is_alive())


if __name__ == '__main__':
    unittest.main()
