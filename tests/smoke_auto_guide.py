"""Real automatic game observation calls the guide without a typed user question."""
import argparse
import base64
import io
import json
from pathlib import Path
import subprocess
import tempfile
import time
import requests

from PIL import Image, ImageDraw, ImageFont
from smoke_memory import ask, GUIDE_TOOLS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--endpoint', default='http://127.0.0.1:8791')
    args = parser.parse_args()
    while not requests.get(args.endpoint + '/health', timeout=10).json().get('gameGuideReady'):
        time.sleep(.5)
    image = Image.new('RGB', (960, 540), '#223341')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 28)
    draw.multiline_text((40, 60), 'World of Warcraft: Forever\nQuest log: quest 7 completed\nReady to turn in. Need the next destination.', font=font, fill='white', spacing=24)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    frame = {'data': base64.b64encode(buffer.getvalue()).decode()}
    with tempfile.TemporaryDirectory(prefix='whale-auto-guide-') as directory:
        receipt, state = ask(args.endpoint, '/look', {'cwd': directory, 'frames': [frame], 'cellCount': 1,
            'game': {'version': 1, 'sampledAt': time.time(), 'build': '70862', 'mapId': 1429, 'zone': '艾尔文森林',
                     'x': 48.9, 'y': 41.6, 'selectedQuest': {'id': 7, 'complete': True}, 'quests': [{'id': 7, 'complete': True}]}})
        assert receipt['requestId'].startswith('whale-guide:'), receipt
        assert state['text'], state
        silent, _ = ask(args.endpoint, '/look', {'sessionId': receipt['sessionId'], 'cwd': directory, 'frames': [frame],
            'game': None})
        journal = next((Path.home() / '.dsh/sessions').glob('*/' + receipt['sessionId'] + '/session.v4.jsonl.zstd'))
        events = [json.loads(line) for line in subprocess.check_output(['zstd', '-dc', str(journal)], text=True).splitlines()]
        turns, schemas, calls = {}, {}, {}
        current = None
        for event in events:
            data = event.get('data', {})
            if event['type'] == 'turn/start': current = data['turn']
            if event['type'] == 'user/message' and data.get('source', {}).get('rpcId'):
                turns[data['source']['rpcId']] = current
            if event['type'] == 'request/header': schemas.setdefault(current, []).append({t['name'] for t in data['header'].get('tools', [])})
            if event['type'] == 'tool/call': calls.setdefault(current, []).append(data['name'])
        guide_turn, screen_turn = turns[receipt['requestId']], turns[silent['requestId']]
        assert schemas[guide_turn] and all(names == GUIDE_TOOLS for names in schemas[guide_turn]), schemas
        assert 'mcp__wuxianwow__quests' in calls.get(guide_turn, []), calls
        assert set(calls[guide_turn]) <= GUIDE_TOOLS, calls
        assert all(not names for names in schemas[screen_turn]) and not calls.get(screen_turn), (schemas, calls)
        # Clean game UI: no pixel bridge and no typed question, only a visible task.
        visual, visual_state = ask(args.endpoint, '/look', {'cwd': directory, 'frames': [frame], 'cellCount': 1,
            'game': None, 'gameView': {'client': 'wow-forever', 'sampledAt': time.time()}})
        assert visual['requestId'].startswith('whale-guide:'), visual_state
        visual_journal = next((Path.home() / '.dsh/sessions').glob('*/' + visual['sessionId'] + '/session.v4.jsonl.zstd'))
        visual_events = [json.loads(line) for line in subprocess.check_output(['zstd', '-dc', str(visual_journal)], text=True).splitlines()]
        visual_calls = [e['data']['name'] for e in visual_events if e['type'] == 'tool/call']
        visual_schemas = [{t['name'] for t in e['data']['header'].get('tools', [])} for e in visual_events if e['type'] == 'request/header']
        assert visual_schemas and all(names == GUIDE_TOOLS for names in visual_schemas), visual_schemas
        assert set(visual_calls) <= GUIDE_TOOLS, visual_calls
        print('Automatic lookup without user text passed:', calls[guide_turn])
        print('Guide comment:', state['text'])
        print('Image-only guide schema/guard boundary passed; a synthetic text panel may correctly stay silent:', visual_calls)
        print('No-current-game observation: zero tool schemas/calls passed.')


if __name__ == '__main__':
    main()
