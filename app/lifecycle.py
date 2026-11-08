"""An advisory lock owns the overlay instance; the PID file is never unlinked."""
import fcntl
import os
import signal
import time
from pathlib import Path


class InstanceLock:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open('a+')
        self.owned = False

    def acquire(self) -> bool:
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        self.owned = True
        return True

    def claim(self):
        self.file.seek(0)
        self.file.truncate()
        self.file.write(str(os.getpid()))
        self.file.flush()

    def stop_existing(self):
        if self.acquire():
            return
        self.file.seek(0)
        pid = int(self.file.read().strip())
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        while not self.acquire():
            time.sleep(0.05)

    def close(self):
        self.file.close()
        self.owned = False
