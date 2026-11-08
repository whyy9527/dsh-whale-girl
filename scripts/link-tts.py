#!/usr/bin/env python3
"""Link user-owned resources; never copy model weights or reference audio."""
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--model', type=Path, required=True)
parser.add_argument('--reference-audio', type=Path, required=True)
parser.add_argument('--reference-text', type=Path, required=True)
args = parser.parse_args()
root = Path.home() / '.local/share/dsh-whale-girl'
root.mkdir(parents=True, exist_ok=True)
for name, source in [('tts-model', args.model), ('reference.wav', args.reference_audio), ('reference.txt', args.reference_text)]:
    source = source.expanduser().resolve(strict=True)
    target = root / name
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        raise SystemExit(f'{target} already exists and is not a symlink')
    target.symlink_to(source, target_is_directory=source.is_dir())
    print(f'{target} -> {source}')
