"""The login job starts DSH; the DSH plugin owns desktop startup."""
import os
from pathlib import Path
import plistlib
import shutil
import sys

LABEL = 'com.dsh.whale-girl'
PLIST = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')


def enabled():
    return PLIST.exists()


def configure(enable):
    if not enable:
        if PLIST.exists():
            PLIST.unlink()
        return
    dsh = shutil.which('dsh')
    if dsh is None:
        raise RuntimeError('找不到 dsh；请先安装 DeepSeek Harness')
    root = Path(__file__).resolve().parent.parent
    log = Path(os.environ.get('DSH_HOME', Path.home() / '.dsh')) / 'whale-girl'
    log.mkdir(parents=True, exist_ok=True)
    logfile = log / 'dsh-startup.log'
    logfile.touch(mode=0o600, exist_ok=True)
    logfile.chmod(0o600)
    payload = {
        'Label': LABEL,
        'ProgramArguments': [dsh, 'web', '--no-open'],
        'WorkingDirectory': str(root),
        'EnvironmentVariables': {'PATH': os.environ['PATH'], 'DSH_HOME': str(log.parent)},
        'RunAtLoad': True,
        'StandardOutPath': str(log / 'dsh-startup.log'),
        'StandardErrorPath': str(log / 'dsh-startup.log'),
    }
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(plistlib.dumps(payload))
    # Register for the next login. Do not launch a competing DSH while the current one owns its ports.


if __name__ == '__main__':
    configure('--disable' not in sys.argv)
    print('登录时启动已' + ('开启' if enabled() else '关闭'))
