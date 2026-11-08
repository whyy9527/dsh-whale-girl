"""One serialized transport for text and observations; DSH owns all conversation memory."""
import threading
import requests
from game import same_task, view as game_view


class Conversation:
    def __init__(self, endpoint, publish, game_context=None):
        self.endpoint = endpoint.rstrip('/')
        self.publish = publish
        self.game_context = game_context
        self.stop_event = threading.Event()
        self.busy = False

    def _start(self, path, payload):
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._run, args=(path, payload, None), daemon=True, name='whale-conversation').start()
        return True

    def send(self, text, session_id='', cwd=None):
        return self._start('/chat', {'text': text, 'sessionId': session_id, 'cwd': cwd})

    def look(self, payload, session_id='', cwd=None):
        return self._start('/look', {**payload, 'sessionId': session_id, 'cwd': cwd})

    def resume(self, pending):
        if not pending or self.busy:
            return
        self.busy = True
        threading.Thread(target=self._run, args=(None, None, pending), daemon=True, name='whale-resume').start()

    def restore(self, session_id, pending=None):
        if not session_id or self.busy:
            return False
        self.busy = True
        def load():
            try:
                params = {'sessionId': session_id}
                if pending:
                    params['excludeRequestId'] = pending['requestId']
                response = requests.get(self.endpoint + '/history', params=params, timeout=10)
                data = response.json()
                if not data.get('ok'):
                    raise RuntimeError(data.get('error', '历史读取失败'))
                event = ('history', data)
            except Exception as error:
                event = ('history_error', {'error': str(error)})
            if pending:
                self.publish(*event)
                self._run(None, None, pending)
            else:
                self.busy = False
                self.publish(*event)
        threading.Thread(target=load, daemon=True, name='whale-history').start()
        return True

    def _run(self, path, payload, pending):
        terminal = None
        try:
            if pending is None:
                if path == '/chat' and self.game_context is not None:
                    payload['game'] = self.game_context()
                response = requests.post(self.endpoint + path, json=payload, timeout=30)
                pending = response.json()
                if not pending.get('ok'):
                    raise RuntimeError(pending.get('error', '发送失败'))
                if path == '/look':
                    pending['manual'] = bool(payload.get('manual'))
                self.publish('accepted', pending)
            while not self.stop_event.is_set():
                try:
                    response = requests.get(self.endpoint + '/chat', params={key: pending[key] for key in ('sessionId', 'requestId')}, timeout=10)
                    state = response.json()
                except requests.RequestException:
                    self.publish('connection', {'error': '连接中断，正在重新读取任务状态…'})
                    self.stop_event.wait(2)
                    continue
                if not state.get('ok'):
                    raise RuntimeError(state.get('error', '读取会话失败'))
                if state['status'] in ('complete', 'failed'):
                    if state['status'] == 'complete' and pending['requestId'].startswith('whale-guide:'):
                        # Results stay in native DSH history, but do not speak stale advice.
                        current = self.game_context() if self.game_context else None
                        same = same_task(payload.get('game') if payload else None, current)
                        if payload and not payload.get('game') and payload.get('gameView'):
                            same = bool(game_view())
                        if not same and state.get('text'):
                            state['suppressed'] = 'game-context-changed'
                            state['text'] = ''
                    terminal = ('state', state)
                    return
                self.publish('state', state)
                self.stop_event.wait(0.8)
        except Exception as error:
            if not self.stop_event.is_set():
                terminal = ('error', {'error': str(error)})
        finally:
            self.busy = False
            if terminal is not None:
                self.publish(*terminal)

    def stop(self):
        self.stop_event.set()
