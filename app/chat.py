"""Nonblocking explicit input client; DSH owns tools, history and approvals."""
import threading
import requests


class Conversation:
    def __init__(self, endpoint, publish):
        self.endpoint = endpoint.rstrip('/')
        self.publish = publish
        self.stop_event = threading.Event()
        self.busy = False

    def send(self, text, session_id='', cwd=None):
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._run, args=(text, session_id, cwd, None), daemon=True, name='whale-chat').start()
        return True

    def resume(self, pending):
        if not pending or self.busy:
            return
        self.busy = True
        threading.Thread(target=self._run, args=('', '', None, pending), daemon=True, name='whale-chat').start()

    def _run(self, text, session_id, cwd, pending):
        try:
            if pending is None:
                payload = {'text': text, 'sessionId': session_id}
                if not session_id and cwd is not None:
                    payload['cwd'] = cwd
                response = requests.post(self.endpoint + '/chat', json=payload, timeout=30)
                pending = response.json()
                if not pending.get('ok'):
                    raise RuntimeError(pending.get('error', '发送失败'))
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
                self.publish('state', state)
                if state['status'] in ('complete', 'failed'):
                    return
                self.stop_event.wait(0.8)
        except Exception as error:
            if not self.stop_event.is_set():
                self.publish('error', {'error': str(error)})
        finally:
            self.busy = False

    def stop(self):
        self.stop_event.set()
