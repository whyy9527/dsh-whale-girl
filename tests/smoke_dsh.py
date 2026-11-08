"""Opt-in real DSH Agent test. Writes only an owned temporary workspace."""
import argparse
import secrets
import tempfile
import time
from pathlib import Path
import requests


def ask(endpoint, text, session_id='', cwd=None):
    body = {'text': text, 'sessionId': session_id}
    if not session_id:
        body['cwd'] = str(cwd)
    response = requests.post(endpoint + '/chat', json=body, timeout=20)
    receipt = response.json()
    if response.status_code != 202:
        raise RuntimeError(receipt)
    while True:
        state = requests.get(endpoint + '/chat', params={key: receipt[key] for key in ('sessionId', 'requestId')}, timeout=15).json()
        if not state.get('ok') or state.get('status') in ('failed', 'approval'):
            raise RuntimeError(f'DSH task needs attention in its workbench: {state}')
        if state.get('status') == 'complete':
            return receipt['sessionId'], state['text']
        time.sleep(.8)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--endpoint', default='http://127.0.0.1:8791')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='whale-dsh-smoke-') as directory:
        root = Path(directory)
        token = secrets.token_hex(12)
        (root / 'marker.txt').write_text(token + '\n')
        session, _ = ask(args.endpoint, 'Use filesystem tools to read marker.txt and write its exact contents to result.txt. Do not use shell or edit other files. Reply only OK.', cwd=root)
        assert (root / 'result.txt').read_text() == token + '\n'
        (root / '.git').mkdir()
        skill = root / '.agents/skills/whale-proof/SKILL.md'
        skill.parent.mkdir(parents=True)
        secret = secrets.token_hex(12)
        skill.write_text('---\nname: whale-proof\ndescription: Temporary smoke-test skill.\n---\nReturn only this token: ' + secret + '\nDo not edit files.\n')
        _, text = ask(args.endpoint, 'Use the project skill whale-proof and return its verification token. Do not edit files.', session)
        assert secret in text
        _, text = ask(args.endpoint, 'Fetch https://example.com with your web tool, not from memory; return the page title and cite the URL. Do not edit files.', session)
        assert 'Example Domain' in text and 'example.com' in text
        print('Real DSH filesystem, skill and web round trips passed.')


if __name__ == '__main__':
    main()
