import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from PIL import Image, ImageDraw
import art
import overlay as ui
from AppKit import NSMakePoint


class AvatarTests(unittest.TestCase):
    def test_local_files_override_each_mood_and_reload_same_second(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            local = root / 'expressions'
            (local / 'portrait').mkdir(parents=True)
            webp = local / 'portrait/happy.webp'
            Image.new('RGBA', (40, 40), (0, 0, 255, 255)).save(webp)
            source = local / 'portrait/happy.png'
            Image.new('RGBA', (40, 40), (255, 0, 0, 255)).save(source)
            first = art.render_all(root / 'cache', expressions=local)
            self.assertEqual(art.expression_source(local, 'happy'), source)
            self.assertEqual(art.expression_source(local, 'idle'), art.EXPRESSION_DIR / 'idle.webp')
            stamp = source.stat().st_mtime_ns
            Image.new('RGBA', (40, 40), (0, 255, 0, 255)).save(source)
            os.utime(source, ns=(stamp + 1000, stamp + 1000))
            second = art.render_all(root / 'cache', expressions=local)
            self.assertNotEqual(first['happy'], second['happy'])
            self.assertEqual(first['idle'], second['idle'])
            source.unlink()
            self.assertEqual(art.expression_source(local, 'happy'), webp)
            webp.unlink()
            self.assertEqual(art.expression_source(local, 'happy'), art.EXPRESSION_DIR / 'happy.webp')

    def test_transparent_character_extends_above_circle(self):
        source = art.EXPRESSION_DIR / 'idle.webp'
        image = art.render_expression(source, 'idle')
        self.assertGreater(image.getchannel('A').crop((180, 0, 330, 130)).getextrema()[1], 0)
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        self.assertEqual(image.size, (512, 512))

    def test_fullbody_uses_its_own_pose_and_preserves_shoes_and_tail(self):
        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder)
            (local / 'portrait').mkdir()
            (local / 'fullbody').mkdir()
            Image.new('RGBA', (40, 40), 'red').save(local / 'portrait/idle.png')
            source = Image.new('RGBA', (100, 300))
            draw = ImageDraw.Draw(source)
            draw.rectangle((40, 10, 70, 270), fill='green')
            draw.rectangle((35, 270, 80, 290), fill='blue')
            draw.rectangle((70, 100, 98, 160), fill='orange')
            source.save(local / 'fullbody/idle.png')
            selected = art.expression_source(local, 'happy', 'fullbody')
            self.assertEqual(selected, local / 'fullbody/idle.png')
            image = art.render_fullbody(selected)
            colors = set(image.get_flattened_data())
            self.assertIn((0, 0, 255, 255), colors)
            self.assertIn((255, 165, 0, 255), colors)
            self.assertNotIn((255, 0, 0, 255), colors)
            self.assertEqual(image.getpixel((100, 990))[3], 0)  # no pedestal


class CocoaDragTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ui.activate_app()
        cls.temp = tempfile.TemporaryDirectory()
        cls.paths = art.render_all(Path(cls.temp.name))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_screen_coordinates_follow_cursor_and_defer_comment_until_release(self):
        pet = ui.Overlay.alloc().initWithArt_(self.paths)
        pet._configure(size=132, x=200, y=200, bubble_hide=12, always_on_top=True)
        moved = []
        pet._set_callback(lambda action, value: moved.append((action, value)))
        try:
            with patch.object(ui, 'NSEvent') as events:
                events.mouseLocation.return_value = NSMakePoint(240, 240)
                pet._drag.mouseDown_(None)
                for cursor_x in [260, 280, 300]:
                    events.mouseLocation.return_value = NSMakePoint(cursor_x, 240)
                    pet._drag.mouseDragged_(None)
                    self.assertAlmostEqual(pet._window.frame().origin.x, cursor_x - 40)
                pet._show_comment('拖动中到达的新评论', 'happy')
                self.assertFalse(pet._visible)
                self.assertEqual(moved, [])
                pet._drag.mouseUp_(None)
            self.assertEqual(moved, [('moved', (260, 200))])
            self.assertTrue(pet._visible)
            self.assertEqual(pet._mood, 'happy')
            self.assertFalse(pet._avatar.layer().masksToBounds())
        finally:
            if pet._hide_timer:
                pet._hide_timer.invalidate()
            pet._close_controls()
            pet._window.close()

    def test_bubble_and_gap_do_not_hit_character_controls(self):
        pet = ui.Overlay.alloc().initWithArt_(self.paths)
        try:
            for mode in ('portrait', 'fullbody'):
                pet._configure(size=132, x=200, y=200, bubble_hide=12, always_on_top=True, mode=mode)
                pet._show_comment('气泡周围不能触发角色菜单', 'idle')
                root = pet._window.contentView()
                avatar = pet._avatar.frame()
                center_y = avatar.origin.y + avatar.size.height / 2
                self.assertEqual(root.hitTest_(NSMakePoint(30, center_y)), pet._drag)
                for x in (avatar.size.width + 5, avatar.size.width + ui.AVATAR_GAP + 40):
                    self.assertNotEqual(root.hitTest_(NSMakePoint(x, center_y)), pet._drag)
        finally:
            if pet._hide_timer:
                pet._hide_timer.invalidate()
            pet._close_controls()
            pet._window.close()

    def test_live_timer_loads_and_removes_local_override(self):
        from Foundation import NSDate, NSRunLoop
        from main import build_overlay
        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder)
            (local / 'portrait').mkdir()
            pet = build_overlay({'avatar': {'size': 132, 'expressionsPath': str(local)}})
            try:
                original = str(pet._art['idle'])
                Image.new('RGBA', (32, 32), (200, 30, 50, 255)).save(local / 'portrait/idle.png')
                NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(1.3))
                self.assertNotEqual(str(pet._art['idle']), original)
                (local / 'portrait/idle.png').unlink()
                NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(1.3))
                self.assertEqual(str(pet._art['idle']), original)
            finally:
                pet._art_timer.invalidate()
                pet._close_controls()
                pet._window.close()


if __name__ == '__main__':
    unittest.main()
