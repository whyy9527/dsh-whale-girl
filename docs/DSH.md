# DSH integration contract

Target: installed DeepSeek Harness 0.2.1-rc.2. The public Session Controller,
Agent, Session, System Prompt and Tools APIs were checked against its shipped
types and implementation.

## One session and one memory

`POST /chat` (explicit text) and `POST /look` (screen images) both enter the same
DSH Session Controller via `prompt({requestId,sessionId,mode:'queue',content})`.
Images are native `PromptContentPart` entries; DSH admits and stores attachments.
Both return 202 admission receipts. `GET /chat` polls the exact request, not the
latest arbitrary reply. The desktop serializes admissions through `Conversation`
and persists one `chat.sessionId` and one `chat.pending` receipt (including kind and
the manual-look display flag).
Reuse that exact session across restarts. Never silently select the latest session.

The DSH append-only session log owns user text, images, observations, replies and
tool results. The native compaction backend summarizes this same shared history
under token pressure; no independent screen summary or log is fed to the model.
Older images may be offloaded during native compaction; relevant facts are retained
in the resulting summary rather than promising unlimited original-pixel memory.
`GET /history` cold-reads the same session for a small readable UI projection.
The panel restores that projection on launch before admitting new work; pending
receipts resume by polling without reposting text or images. The pending turn is
excluded from the initial UI history projection to avoid displaying its completed
reply twice when polling resumes.

## Turn provenance, format and tools

Explicit text uses a normal UUID request ID and a text-conversation envelope.
Ordinary screen observation IDs begin `whale-look:`. Observations admitted with a
fresh non-combat task snapshot or a fresh OS-observed foreground Forever capture
begin `whale-guide:`. Both remain UI kind `look`. Only the host selects this
provenance after validating the snapshot or foreground capture stamp. Guide
availability is projected in `/health`; missing MCP tools do not masquerade as
an available guide. Image-only lookups use readable task names/IDs and do not
claim access to hidden game state.
Their envelope marks
the image as untrusted screen content and limits the short `say`/`mood` JSON rule
to that observation turn. The following explicit text turn answers normally.
The source identity is durable `user/message.data.source.rpcId`, not text OCR,
a marker guessed from the reply, or an in-memory latest-request variable.

`installScreenPolicy` projects synchronous `agent/inbox/claimed` events into a
WeakMap before prompt assembly. `agent/pre-step` is too late: the native loop has
already assembled its tool schemas at that point. `system-prompt/assemble` clears
ordinary observations' tools and filters game-guide turns to the exact read-only
allowlist owned by `lib/game.js`. A native monotonic `tools.guard` independently
checks the full append-only current-turn source identities and rejects every
other tool, including `report_issue`, shell, files, web fetch and subagents.
Mixed input retains the more restrictive observation policy.
The three guide schemas load immediately. When the offered name set changes,
the public pre-step decision declares `startsRequestSeries: true`; DSH records a
new native tool baseline while retaining the shared conversation. Incremental
MCP additions alone are deferred and would otherwise leave an all-deferred
tool set that the provider rejects. Never rewrite frozen LLM requests.
Compaction appends replacement events; it does not erase those original source
facts. Every ordinary followup is a separate turn; the next text turn restores
normal tools and the user's existing approval policy. The user's standing
authorization covers proactive guide lookups only; screenshots never authorize
file access, commands, arbitrary websites or public reports.

`projectChat` matches the admitted request to its enclosing `turn/start`, reads
only its assistant messages and `turn/end`, and surfaces unmatched approval waits.
DSH owns approvals; never auto-approve or change permission presets. The workbench
action uses `ctx.webServer.getOrigin()` and `ctx.connection.authenticatedUrl()`
and opens locally without returning or logging its authentication token.

The shared session uses DSH's selected model for both text and images. Do not add
separate screen provider/model/temperature/timeout settings; a selected model must
support images. Screens wait for native task completion without a wall-clock cutoff.
The UI can keep a draft editable during an observation while serializing send.
Automatic frame filtering still requires substantial changes and never forces a
comment after an idle interval. A valid empty `say` stays silent in the UI and TTS.

## Transport and verification

The plugin binds loopback; browser-Origin requests cannot submit text/images or
read shared history. POSTs require JSON. Model execution remains with DSH; the
plugin does not launch a second CLI or implement its own tools.

Verify text → image → text recall, exact request/turn correlation, exact read-only
tools in game-guide requests, zero tools in ordinary observations, restored full
text tools afterward, history reload and pending-image
resume without replay. Fake-context tests are not evidence of real DSH behavior;
run the real shared-memory smoke against the loaded plugin as well.

## Optional WoW Forever lookup

The local web profile may mount the official `@deepseek-ai/dsh-mcp-client` bridge
with `serverName: wuxianwow`, `transport: streamable-http` and
`url: https://wuxianwow.com/mcp`. This [third-party database](https://wuxianwow.com/ai)
is available to explicit DSH conversations; the public package does not enable it
automatically. Project skills remain in `.dsh/skills` or `.agents/skills`.

For 魔兽世界：无限 questions, use `mcp__wuxianwow__*` query tools when present.
Search by name/keyword, then fetch the returned ID. Cite the source and distinguish
temporary third-party coordinates from client data; do not invent missing locations.
Ask the player's current zone when directions depend on it. `report_issue` sends a
public report and requires an explicit user request. Authorized automatic game
observations proactively query `quests`, `npcs`, `atlas`; this is an exact name
allowlist, not the entire `mcp__wuxianwow__*` namespace. Existing matching static
guide facts can be reused from the shared history; player positions never become
a cached current state. No separate guide cache or approval auto-confirm is added.

WhaleBridge may attach a fresh, bounded, explicitly untrusted public game snapshot
to either request as an additional native text part. The snapshot remains
untrusted data; only the host's admitted request identity selects the authorized
guide policy. The UI history projects only the
user's first text part; DSH retains the complete envelope. See [game bridge](WOW.md)
for ownership, freshness and client installation. This sensor has no independent
conversation memory or direct model/tool execution path.
