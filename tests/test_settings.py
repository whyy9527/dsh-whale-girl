import plistlib
from pathlib import Path
import sys,tempfile,threading,unittest
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import autostart
from chat import Conversation


class SettingsTests(unittest.TestCase):
    def test_login_startup_runs_dsh_not_python(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'login.plist'
            with patch.object(autostart,'PLIST',path),patch.object(autostart.shutil,'which',return_value='/test/bin/dsh'):
                autostart.configure(True)
                data=plistlib.loads(path.read_bytes())
                self.assertEqual(data['ProgramArguments'],['/test/bin/dsh','web','--no-open'])
                self.assertTrue(autostart.enabled())
                autostart.configure(False)
                self.assertFalse(path.exists())

    def test_resuming_receipt_polls_without_resending_user_mutation(self):
        finished=threading.Event()
        state={'ok':True,'status':'complete','text':'done'}
        response=Mock();response.json.return_value=state
        client=Conversation('http://127.0.0.1:1',lambda kind,data: finished.set() if kind=='state' else None)
        with patch('chat.requests.get',return_value=response) as get,patch('chat.requests.post') as post:
            client.resume({'sessionId':'exact-session','requestId':'exact-request'})
            self.assertTrue(finished.wait(3))
            post.assert_not_called()
            self.assertEqual(get.call_args.kwargs['params'],{'sessionId':'exact-session','requestId':'exact-request'})
            client.stop()

    def test_observation_is_serialized_with_text_and_restores_without_reposting(self):
        accepted, release, done = threading.Event(), threading.Event(), threading.Event()
        pending = {'ok': True, 'sessionId': 'shared', 'requestId': 'whale-look:one', 'kind': 'look'}
        post_response = Mock(); post_response.json.return_value = pending
        state_response = Mock(); state_response.json.return_value = {'ok': True, 'status': 'complete', 'text': '', 'kind': 'look'}
        def state(*args, **kwargs):
            release.wait(3)
            return state_response
        def publish(kind, data):
            if kind == 'accepted': accepted.set()
            if kind == 'state':
                self.assertFalse(client.busy)
                done.set()
        client = Conversation('http://127.0.0.1:1', publish)
        with patch('chat.requests.post', return_value=post_response) as post, patch('chat.requests.get', side_effect=state):
            self.assertTrue(client.look({'frames': ['fixture']}, 'shared'))
            self.assertTrue(accepted.wait(3))
            self.assertFalse(client.send('do not overlap', 'shared'))
            self.assertTrue(post.call_args.args[0].endswith('/look'))
            release.set()
            self.assertTrue(done.wait(3))
        restored = threading.Event()
        history_response = Mock(); history_response.json.return_value = {'ok': True, 'entries': [{'name': '看屏', 'text': 'arrived'}]}
        def replay(kind, data):
            if kind == 'state': restored.set()
        client = Conversation('http://127.0.0.1:1', replay)
        with patch('chat.requests.get', side_effect=[history_response, state_response]) as get, patch('chat.requests.post') as post:
            self.assertTrue(client.restore('shared', pending))
            self.assertTrue(restored.wait(3))
            post.assert_not_called()
            self.assertEqual(get.call_args.kwargs['params']['requestId'], 'whale-look:one')


if __name__=='__main__': unittest.main()
