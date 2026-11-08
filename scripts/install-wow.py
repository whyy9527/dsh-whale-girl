#!/usr/bin/env python3
"""Install our own read-only addon into an explicitly selected Forever client."""
import argparse
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--client', type=Path, default=Path('/Applications/World of Warcraft/_forever_'))
    args = parser.parse_args()
    addons = args.client / 'Interface' / 'AddOns'
    if not addons.is_dir() or not (args.client / 'World of Warcraft.app').is_dir():
        parser.error('请指定含 World of Warcraft.app 和 Interface/AddOns 的 Forever 客户端目录')
    source = Path(__file__).resolve().parents[1] / 'addons' / 'WhaleBridge'
    target = addons / 'WhaleBridge'
    target.mkdir(exist_ok=True)
    for name in ('WhaleBridge.toc', 'Protocol.lua', 'WhaleBridge.lua'):
        shutil.copy2(source / name, target / name)
    print('Installed:', target)
    print('首次新增插件后请完全退出并重开游戏，在插件列表启用 Whale Bridge。/whale off 可隐藏并停用数据输出。')


if __name__ == '__main__':
    main()
