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


if __name__=='__main__': unittest.main()
