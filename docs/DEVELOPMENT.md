# Runtime and development

## Environment

Supported and verified: Apple Silicon macOS, Python 3.13.15, Node 24.13.1,
DSH 0.2.1-rc.2, uv 0.13.6, mlx-audio 0.5.0. Python and Node versions are in
`.python-version` / `.node-version`; all Python dependencies are in `uv.lock`.
`./scripts/setup.sh` runs `uv sync --frozen --extra tts` into this project's own
`.venv`. No other project's environment is required. The overlay launch script
prepares the environment if it does not yet exist; `uv` must be installed.

Install into the web profile with `dsh plugin --profile web add "$PWD"`. Restart
`dsh web` after changing loaded Node plugin code. The plugin's successful HTTP
listen starts one detached overlay; the overlay owns a `flock` instance lock.
The normal UI exposes two startup choices: DSH startup and macOS login startup.
`scripts/run.sh` development flags remain available for diagnosis and tests only.

## Local TTS

Model weights are not bundled. Download the pinned model snapshot:

```bash
.venv/bin/hf download mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16 \
  --revision a6eb4f68e4b056f1215157bb696209bc82a6db48
```

Provide a permitted clean short reference WAV and its exact UTF-8 transcript,
then use `scripts/link-tts.py --model <absolute snapshot path>
--reference-audio <absolute wav path> --reference-text <absolute txt path>`.
The script only creates symlinks at `~/.local/share/dsh-whale-girl/tts-model`,
`reference.wav` and `reference.txt`. Keep those source files available.

The Base model supplies synthesis; the reference audio conditions speaker
identity and prosody. `mood` currently chooses artwork, not TTS emotional control.
Cloud TTS is opt-in, has a different voice, and takes an explicit setting or
`DASHSCOPE_API_KEY`. Defaults and actual settings fields belong to `app/config.py`.

## Artwork and display modes

Local artwork lives outside the repository:

```text
$DSH_HOME/whale-girl/expressions/
  portrait/
    idle.png  smug.png  shock.png  happy.png  bored.png  angry.png
  fullbody/
    idle.png
    # Optional whole-body poses with the same six state names
```

When upgrading a pre-mode local pack, move its root-level mood images into
`portrait/` before launch; the old root layout is retired rather than kept as a
parallel reader. PNG wins over WebP. Each mode resolves separately. A full-body mood without its
own local image uses the local full-body `idle` pose; otherwise the built-in
series supplies missing images. The renderer never substitutes a portrait image
for a full-body image. The menu opens the active mode's folder.

Use true transparent RGBA art for popout/full-body display. Portrait crops tuck
their lower cut edge into the disk; full-body mode preserves the complete image
without a pedestal. Each state replaces the entire pose, including gestures and tail,
and aligns the complete silhouette to a common bottom baseline. Opaque portrait images remain circular photographs;
background removal is not performed at runtime. Files refresh while running;
dragging defers image/layout updates until release. Only the character frame owns
click/drag actions; the speech bubble and the gap beside it do not open controls. The cache key includes mode,
source identity, nanosecond mtime, size and renderer version.

The current personal originals and derived artwork are not publicly licensed.
Do not add them to Git. The bundled chibi set retains its own source attribution
and CC BY-NC-SA conditions. Public screenshots and previews must use bundled art.

## UI material and controls

`design/surface-study.png` is the built-in image-generation study.
Material: icy-blue frosted glass, near-white highlights, subtle blue edge,
hairline slate-blue border, small soft shadow, dark slate text. The portrait base, speech
bubble and control panel share the palette. Native drawing is implemented with Cocoa gradients. The exact creative input is
[design/prompt.txt](../design/prompt.txt); the [current native controls](../design/implemented-controls.png)
are an implementation capture, not the generated study.

The control panel separates conversation and settings into two tabs. It opens on
settings initially and retains the selected tab, draft and task state while running.
Its gradient is opaque inside rounded corners to keep underlying text out, and its
window level stays above the character/bubble window even when a comment refreshes.
The panel owns input, reply history, watch/voice switches, display mode,
login startup, active asset folder and DSH workbench actions. The macOS status
item and avatar both open the same panel. Text and screen observations share one DSH session and restore readable recent
history on launch. Input transport is nonblocking; task execution continues in DSH
if the desktop window exits. Approvals stay in the DSH UI.

## Permissions, sampling and process lifecycle

Quartz excludes this process’s windows (character, bubble and controls)
before sampling, so moving or opening the companion does not become model input.
The application stays visible to other screen recorders. The system window list retains its front-to-back order; desktop windows remain
included in the composed desktop image. There is no unfiltered
screenshot fallback.

macOS must grant Screen Recording to the program launching the overlay (for
auto-start, check the program launching DSH). The sampler compares 64×36 gray
fingerprints against the last accepted frame; it batches changes into one image.
The first frame only establishes a baseline. Both mean grayscale difference and
the changed-area threshold must pass before a frame is kept; compare against the
last accepted frame so small accumulated changes can eventually count. Only a full
batch is sent automatically: there is no timeout or forced comment on an idle
screen. Manual look and partial diagnostic batches send actual images directly,
never an almost-empty nine-cell grid. Model requests block sampling, and minimum-interval batches may be skipped.
This is sampled screen understanding, not a video recording.

Pause stops automatic capture and speech and discards stale replies. Text and image admissions are serialized into the same DSH session; pending work
suspends further sampling. The native session owns shared history and automatic
compaction. Ordinary observations have zero tools; game-guide observations may
use only the three read-only tools in `lib/game.js`. Before speaking a structured
game-guide reply, the desktop reads the current panel again: changed task, zone,
combat or missing data suppresses stale advice. Image-only help instead rechecks
that Forever is still in the foreground; it cannot track hidden task/position
changes during the query and must avoid live distance/direction claims.
Pending guide replies restored after a
restart lack that original comparison snapshot and stay silent; their results
remain in DSH history. Speech has one consumer and replaces pending old text.
Termination cleanup belongs to `applicationWillTerminate:` because AppKit can
exit without returning from `runEventLoop`; the repeating Python timer lets
SIGTERM be handled while Cocoa idles. Stop the worker before joining its thread.

## Diagnostics

`GET /health` on the configured plugin endpoint reports shared-session ownership and the DSH
workbench URL. Runtime logs/cache and the instance lock live below the user
configuration directory. Never print full configuration or resolved keys.

Run the checks in AGENTS.md. Internal flags `--check`, `--preview`, `--demo
--once`, `--stop`, and `--restart` support local verification. They do not replace
plugin startup. A real test should exercise text input, both display modes,
dragging, permission waits, restart/exit, and a local TTS synthesis.
