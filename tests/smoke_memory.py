"""Opt-in real DSH text→image→text memory proof; no private screenshots or model timeout."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import requests
from PIL import Image, ImageDraw, ImageFont

GUIDE_TOOLS = {'mcp__wuxianwow__quests', 'mcp__wuxianwow__npcs', 'mcp__wuxianwow__atlas'}


def ask(endpoint, path, payload):
    response = requests.post(endpoint + path, json=payload, timeout=30)
    receipt = response.json()
    assert response.status_code == 202, receipt
    while True:
        state = requests.get(endpoint + '/chat', params={key: receipt[key] for key in ('sessionId', 'requestId')}, timeout=15).json()
        if not state.get('ok') or state['status'] in ('failed', 'approval'):
            raise RuntimeError(state)
        if state['status'] == 'complete':
            return receipt, state
        time.sleep(.8)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--endpoint', default='http://127.0.0.1:8791')
    parser.add_argument('--restart-signal', help='Optional marker path: pause after proof until caller restarts DSH and creates this file')
    args = parser.parse_args()
    nickname = 'Finch' + secrets.token_hex(3)
    number = str(secrets.randbelow(900000) + 100000)
    game_zone = 'Harbor' + secrets.token_hex(3)
    quest_id = str(secrets.randbelow(90000) + 10000)
    with tempfile.TemporaryDirectory(prefix='whale-memory-') as directory:
        first, _ = ask(args.endpoint, '/chat', {'cwd': directory, 'text': f'请记住我的游戏角色代号是 {nickname}。下一次屏幕观察请用这个代号称呼我，并读出图中 GATE 后的编号，短评同时包含这两个值。此要求只适用于之后一次观察；现在只回已记住，不用工具。'})
        image = Image.new('RGB', (960, 540), (28, 54, 72))
        draw = ImageDraw.Draw(image)
        draw.rectangle((160, 100, 800, 450), fill=(190, 176, 147))
        font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', 66)
        draw.text((210, 210), 'GATE ' + number, fill=(15, 24, 30), font=font)
        path = Path(directory) / 'synthetic-gate.png'
        image.save(path)
        look, observed = ask(args.endpoint, '/look', {'sessionId': first['sessionId'], 'cwd': directory, 'frames': [{'data': base64.b64encode(path.read_bytes()).decode(), 'ts': '12:00:00'}], 'cellCount': 1, 'grid': False,
            'game': {'version': 1, 'sampledAt': time.time(), 'zone': game_zone, 'selectedQuest': {'id': int(quest_id), 'title': 'Synthetic quest'}}})
        assert nickname.lower() in observed['text'].lower() and number in observed['text'], observed
        third, recalled = ask(args.endpoint, '/chat', {'sessionId': look['sessionId'], 'text': '我的角色代号是什么？刚才屏幕图里 GATE 后面的编号是什么？那次游戏快照的区域名和选中任务 ID 是什么（历史值，不是当前位置）？请将这四个值写入 memory-proof.txt，并在回复中给出。仅用文件写入工具，不要 shell，不改其他文件。'})
        assert nickname.lower() in recalled['text'].lower() and number in recalled['text'], recalled
        assert first['sessionId'] == look['sessionId'] == third['sessionId']
        saved = (Path(directory) / 'memory-proof.txt').read_text()
        assert nickname.lower() in saved.lower() and number in saved
        assert game_zone.lower() in saved.lower() and quest_id in saved, saved
        history = requests.get(args.endpoint + '/history', params={'sessionId': first['sessionId']}, timeout=15).json()
        assert any(item['name'] == '看屏' and number in item['text'] for item in history['entries']), history
        record = {'sessionId': first['sessionId'], 'lookRequestId': look['requestId'], 'textRequestId': third['requestId'], 'nickname': nickname, 'number': number}
        Path('/tmp/whale-shared-memory-receipt.json').write_text(json.dumps(record))
        home = Path(os.environ.get('DSH_HOME', Path.home() / '.dsh'))
        journal = next((home / 'sessions').glob('*/' + first['sessionId'] + '/session.v4.jsonl.zstd'))
        events = [json.loads(line) for line in subprocess.check_output(['zstd', '-dc', str(journal)], text=True).splitlines()]
        current_turn, tool_names = None, set()
        turns, requests_by_turn, calls = {}, {}, {}
        for event in events:
            data = event.get('data', {})
            if event['type'] == 'turn/start': current_turn = data['turn']
            if event['type'] == 'user/message' and data.get('source', {}).get('rpcId'):
                requests_by_turn[data['source']['rpcId']] = current_turn
            if event['type'] == 'request/header': tool_names = {t['name'] for t in data['header'].get('tools', [])}
            if event['type'] == 'tool/call': calls.setdefault(current_turn, []).append(data['name'])
            if event['type'] == 'turn/end': turns[data['turn']] = tool_names
        look_turn = requests_by_turn[look['requestId']]
        text_turn = requests_by_turn[third['requestId']]
        assert turns[look_turn] <= GUIDE_TOOLS and set(calls.get(look_turn, [])) <= GUIDE_TOOLS, (turns, calls)
        assert len(turns[text_turn]) > len(GUIDE_TOOLS), turns
        print('Real text→image + game context→text memory, history reload and native tool isolation passed:', first['sessionId'])

        if args.restart_signal:
            signal = Path(args.restart_signal)
            signal.with_suffix('.ready').write_text(json.dumps(record))
            print('Ready for DSH restart.', flush=True)
            while not signal.exists():
                time.sleep(.2)
            _, resumed = ask(args.endpoint, '/chat', {'sessionId': first['sessionId'], 'text': '请从之前历史告诉我角色代号及屏幕 GATE 编号，只回复这两个值，不用工具。'})
            assert nickname.lower() in resumed['text'].lower() and number in resumed['text'], resumed
            signal.unlink()
            signal.with_suffix('.ready').unlink()
            print('The same session recalled text and screenshot facts after DSH restart.')



if __name__ == '__main__':
    main()
