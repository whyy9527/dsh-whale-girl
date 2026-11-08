# dsh-whale-girl — AI maintenance entry

This is a macOS desktop companion. Keep `README.md` short and human-facing: a
plain introduction, plugin startup, login startup, and a link here. Technical
instructions belong here or in the relevant linked document, without parallel
copies of configuration defaults.

## Ownership and working paths

- `lib/host.js`: DSH plugin, HTTP bridge and automatic overlay launch.
- `lib/core.js`: screen-comment prompts and image payload contract.
- `lib/chat.js`: explicit input through DSH Session Controller; request-to-turn projection.
- `app/`: native Cocoa UI, screen sampling and local Qwen speech.
- `app/config.py`: sole owner of settings defaults. User settings live under
  `$DSH_HOME/whale-girl/`, normally `~/.dsh/whale-girl/`.
- `app/theme.py` and `app/glass.py`: shared material and native drawing, based on
  [generated design](design/surface-study.png). Do not redraw characters for UI changes.
- `app/autostart.py`: the login job starts `dsh web --no-open`; the plugin starts
  the overlay. Do not introduce a second independent login launcher for Python.

Before changing DSH integration, read [DSH contract](docs/DSH.md) and the installed
0.2.1-rc.2 package's public types and implementation. Do not invent host APIs or
replace DSH's tool engine with direct shell execution.

Before editing runtime, assets or setup, read the relevant section of
[development guide](docs/DEVELOPMENT.md). Sources and reuse boundaries are in
[credits](docs/CREDITS.md) and [third-party notices](THIRD-PARTY-NOTICES.md).

## Behavior boundaries

- Capture excludes all windows of the overlay process before frame selection; never
  restore a full-screen fallback that sees the companion itself.
- Automatic screenshots use `ctx.llm` only. They must never wake a tool-enabled
  Agent or be interpreted as permission to read/write files.
- Explicit text goes to one DSH session. Match the durable user `source.rpcId`
  to its enclosing turn; never display the latest arbitrary assistant message.
- DSH owns tools, skills, history and approvals. Show approval waits and offer
  the DSH workbench; never auto-approve or change the session's permission policy.
- Avatar and full-body modes use separate local asset folders. Preserve entire
  full-body silhouettes, shoes and whale tails. Keep drag geometry in screen
  coordinates; save position on release and defer layout changes during dragging.
- Personal artwork, reference audio, model weights, user settings, credentials
  and logs stay outside tracked/public files. Never publish the private set in
  screenshots, design studies or package assets. The repository uses CC BY-NC-SA
  4.0; preserve third-party attribution.

## Checks and delivery

Prepare with `./scripts/setup.sh` (`uv sync --frozen --extra tts`). Keep Python,
Node, MLX dependencies and the documented model revision pinned.

For affected code run:

```bash
npm test
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python tests/smoke_macos.py
```

The smoke opens real Cocoa windows without screenshots/model calls. For UI work,
inspect an actual native-window capture, not only the generated design. For DSH
chat, run `.venv/bin/python tests/smoke_dsh.py` against the loaded plugin to verify
a real controller round trip and tool use in its owned temporary workspace. Do not
claim support from fake-context tests alone. For capture changes, separately run
`.venv/bin/python tests/smoke_capture.py` with Screen Recording permission; it opens
two colored native windows and checks that sampled pixels exclude both.

Before pushing, inspect exact staged files, `git diff --check`, package contents,
and private-data boundaries; preserve unrelated changes. Development flags in
`app/main.py` are internal checks, not additional human startup routes.
