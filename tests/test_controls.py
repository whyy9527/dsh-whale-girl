"""Native page changes preserve drafts and busy state without hidden Return actions."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from AppKit import NSStatusWindowLevel
from controls import Controls
from overlay import activate_app


class ControlsTests(unittest.TestCase):
    def test_pages_preserve_draft_busy_state_and_route_actions(self):
        activate_app()
        actions = []
        panel = Controls.alloc().initWithCallback_(lambda *args: actions.append(args))
        try:
            self.assertGreater(panel._window.level(), NSStatusWindowLevel)
            self.assertTrue(panel._chat_page.isHidden())
            panel._input.setStringValue_('读取这个文件 🐳')
            panel.send_(None)
            self.assertEqual(actions, [])
            panel._select_page(0)
            panel._set_busy(True, '需要确认，请打开 DSH 工作台。')
            panel._select_page(1)
            panel._select_page(0)
            panel.send_(None)
            self.assertEqual(actions, [])
            self.assertEqual(panel._input.stringValue(), '读取这个文件 🐳')
            panel._set_busy(False, '就绪')
            panel.send_(None)
            self.assertEqual(actions, [('send', '读取这个文件 🐳')])
            panel._append('DSH', '已读取 🐳')
            self.assertIn('已读取 🐳', panel._transcript.string())
            panel._set_busy(True, '正在观察…', allow_draft=True)
            self.assertTrue(panel._input.isEnabled())
            self.assertFalse(panel._send.isEnabled())
            panel._restore_history([{'name': '看屏', 'text': '到了城门'}, {'name': '你', 'text': '这是哪？'}])
            self.assertIn('看屏：到了城门', panel._transcript.string())
            panel._select_page(1)
            panel.workbench_(None)
            self.assertEqual(actions[-1], ('workbench', None))
        finally:
            panel._window.close()


if __name__ == '__main__':
    unittest.main()
