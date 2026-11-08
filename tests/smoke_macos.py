"""Real Cocoa restart/stop smoke. No screen capture, model call or private config."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    env = {**os.environ, 'DSH_HOME': directory}
    command = [sys.executable, str(root / 'app/main.py')]
    processes = []
    def launch(*args):
        proc = subprocess.Popen(command + list(args), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        processes.append(proc)
        return proc
    def wait_pid_change(old=None):
        path = Path(directory) / 'whale-girl/overlay.pid'
        for _ in range(100):
            if path.exists() and path.read_text().strip() not in ('', old):
                return path.read_text().strip()
            time.sleep(0.05)
        raise AssertionError('overlay did not claim instance lock')
    try:
        first = launch('--preview', '重启与退出自检')
        first_pid = wait_pid_change()
        time.sleep(1)
        duplicate = launch('--preview', 'duplicate')
        output = duplicate.communicate(timeout=10)[0]
        assert duplicate.returncode == 0 and '已经在跑' in output, output
        second = launch('--restart', '--preview', '重启成功')
        second_pid = wait_pid_change(first_pid)
        first_output = first.communicate(timeout=10)[0]
        assert first.returncode == 0 and "[lifecycle] stopped" in first_output, first_output
        # Bubble is now hidden; SIGTERM must work even when Cocoa is idle.
        time.sleep(14)
        stopper = launch('--stop')
        stop_output = stopper.communicate(timeout=10)[0]
        second_output = second.communicate(timeout=10)[0]
        assert stopper.returncode == second.returncode == 0, (stop_output, second_output)
        assert "[lifecycle] stopped" in second_output, second_output
        print(json.dumps({'single_instance': 'OK', 'restart': 'OK', 'idle_sigterm': 'OK', 'pids': [first_pid, second_pid]}))
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
            proc.communicate()
