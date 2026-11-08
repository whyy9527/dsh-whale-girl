"""Real DSH event → production native bubble → button → same-session answer/audio.

Only synthetic game data and bundled artwork appear in the window capture.
The child runs main.main(); hooks only observe its UI and press a native button.
"""
import base64
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))


def native():
    import main
    from PyObjCTools import AppHelper
    overlay, voice, logs, errors = [], [], [], []
    build, speaker = main.build_overlay, main.Speaker
    stage = [0]
    folder = Path(os.environ['DSH_HOME'])
    expected = json.loads((folder / 'expected.json').read_text())
    original_stop = AppHelper.stopEventLoop
    def stop(*args, **kwargs):
        import traceback
        (folder / 'native-stop.txt').write_text(''.join(traceback.format_stack(limit=8)))
        return original_stop(*args, **kwargs)
    AppHelper.stopEventLoop = stop

    def make_overlay(cfg):
        pet = build(cfg)
        overlay.append(pet)
        return pet

    def make_speaker(*args, **kwargs):
        logger = kwargs.get('log', print)
        def log(message):
            logs.append(message)
            logger(message)
        kwargs['log'] = log
        result = speaker(*args, **kwargs)
        voice.append(result)
        return result

    def inspect():
        try:
            pet = overlay[0]
            finished = sum('播放完成 (afplay exit=0)' in line for line in logs)
            assert not any('[tts] 失败' in line for line in logs), logs
            if stage[0] == 0 and pet._bubble._choices and finished >= 1:
                assert pet._bubble._choices == expected['choices'], pet._bubble._choices
                output = ROOT / '.local/interaction-question.png'
                subprocess.run(['screencapture', '-x', '-l', str(pet._window.windowNumber()), str(output)], check=True)
                print('Native question captured; clicking choice.', flush=True)
                pet._bubble._buttons[expected['index']].performClick_(None)
                assert not pet._bubble._choices
                stage[0] = 1
                print('Choice submitted through production handler.', flush=True)
            elif stage[0] == 1 and finished >= 2:
                lines = pet._controls._lines
                replies = [s for s in lines if s.startswith('鲸鱼娘：')]
                assert replies and '营地' in replies[-1] and '蓝鲸07' in replies[-1], replies
                assert any('我选“' + expected['choices'][expected['index']] + '”' in s for s in lines if s.startswith('你：')), lines
                print('Native button → production /chat → contextual answer:', replies[-1], flush=True)
                print('Question and answer both completed real Qwen/afplay playback.', flush=True)
                # NSApplication.terminate can exit without unwinding main.main().
                # The parent requires this receipt, not just a zero exit code.
                (folder / 'native-proof.json').write_text(json.dumps({'reply': replies[-1], 'playbacks': finished}))
                pet._dispatch('quit')
                return
        except BaseException as error:
            print('Native verification failed:', repr(error), flush=True)
            (folder / 'native-error.txt').write_text(repr(error))
            errors.append(error)
            overlay[0]._dispatch('quit')
            return
        AppHelper.callLater(.25, inspect)

    main.build_overlay, main.Speaker = make_overlay, make_speaker
    sys.argv = [str(ROOT / 'app/main.py')]
    AppHelper.callLater(.25, inspect)
    result = main.main()
    if errors:
        raise errors[0]
    assert stage[0] == 1 and result == 0


def run():
    from PIL import Image, ImageDraw
    from game import changes
    from smoke_memory import ask
    endpoint = 'http://127.0.0.1:8791'
    local = json.loads((Path.home() / '.dsh/whale-girl/config.json').read_text())
    with tempfile.TemporaryDirectory(prefix='whale-interaction-') as directory:
        first, _ = ask(endpoint, '/chat', {'cwd': directory, 'text':
            '本轮只回复“记住了”，不要调用工具或现在提问。请记住：我的角色代号是蓝鲸07，营地补给正在收集中。'
            '等下一轮画面显示补给收齐时，请问我先回营地还是继续采集，并给两个快捷选项；我回答后称呼我的代号接着回应。'})
        print('Synthetic goal context admitted in shared test session.', flush=True)
        before = {'zone': '风铃营地', 'selectedQuest': {'id': 7, 'title': '营地补给', 'objectives': ['1/8']},
                  'quests': [{'id': 7, 'complete': False}]}
        after = {**before, 'selectedQuest': {**before['selectedQuest'], 'objectives': ['8/8']},
                 'quests': [{'id': 7, 'complete': True}]}
        image = Image.new('RGB', (960, 540), '#243d4e')
        ImageDraw.Draw(image).text((60, 80), 'Supplies collected: 8 / 8. Quest complete.', fill='white', font_size=32)
        data = io.BytesIO()
        image.save(data, format='PNG')
        receipt, state = ask(endpoint, '/look', {'sessionId': first['sessionId'], 'cwd': directory,
            'events': changes(before, after), 'frames': [{'data': base64.b64encode(data.getvalue()).decode()}]})
        assert len(state.get('choices', [])) == 2, state
        index = next(i for i, c in enumerate(state['choices']) if '营地' in c)
        print('Real event-aware DSH question:', state['text'], state['choices'], flush=True)
        cfg = copy.deepcopy(local)
        cfg.update(watchEnabled=False)
        cfg['avatar'].update(expressionsPath=directory + '/empty-art', mode='portrait', x=300, y=320)
        cfg['tts']['enabled'] = True
        cfg['chat'] = {'sessionId': receipt['sessionId'], 'workspacePath': directory,
                       'pending': {**receipt, 'manual': True}}
        config_path = Path(directory) / 'whale-girl/config.json'
        config_path.parent.mkdir()
        config_path.write_text(json.dumps(cfg, ensure_ascii=False))
        config_path.chmod(0o600)
        (Path(directory) / 'expected.json').write_text(json.dumps({'choices': state['choices'], 'index': index}))
        env = {**os.environ, 'DSH_HOME': directory}
        subprocess.run([sys.executable, '-u', __file__, '--native'], env=env, check=True)
        proof = Path(directory) / 'native-proof.json'
        if not proof.exists():
            for name in ('native-error.txt', 'native-stop.txt'):
                path = Path(directory) / name
                if path.exists():
                    print(path.read_text(), flush=True)
            raise AssertionError('Native test exited without a completion receipt')
        print('Verified native receipt:', json.loads(proof.read_text()), flush=True)
        _, final = ask(endpoint, '/chat', {'sessionId': receipt['sessionId'],
            'text': '只确认：我刚才通过按钮选的是什么？我的角色代号是什么？不要调用工具。'})
        assert '营地' in final['text'] and '蓝鲸07' in final['text'], final
        print('Same-session choice/nickname recall:', final['text'], flush=True)


if __name__ == '__main__':
    native() if '--native' in sys.argv else run()
