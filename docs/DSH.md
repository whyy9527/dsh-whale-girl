# DSH integration contract

Target: installed DeepSeek Harness 0.2.1-rc.2. The integration was checked against
its published `dsh-api-session-controller`, `dsh-agent`, `dsh-session` and
`dsh-user-approval` type declarations and bundled implementations.

## Two distinct paths

1. Automatic screen comments: `POST /look` → attachments → `ctx.llm.stream` →
   short `say`/`mood`. This path has no Agent and cannot call tools.
2. Explicit user input: `POST /chat` → `ctx.sessionController.create({cwd})`
   when needed → `prompt({requestId,sessionId,mode:'queue',content},signal)`.
   The response acknowledges admission; `GET /chat` reads that exact request.

The controller supplies an ordinary DSH session with the configured model,
workspace instructions, installed skills and available tool providers. No CLI
subprocess, custom tool runner or generated shell command replaces the host.
A companion session is persisted by DSH; the desktop stores only its session ID
and the pending request receipt in its own user settings. Reuse the exact ID;
never silently choose a nearby or latest session.

## Reply and approval ownership

`lib/chat.js` folds durable events. It finds the accepted `user/message` whose
`source.rpcId` equals the submitted `requestId`, associates it with the enclosing
`turn/start`, and reads only that turn's assistant messages and `turn/end`.
Unmatched requests remain queued. Another browser prompt's reply is not ours.

An unmatched `approval/asked` inside that turn means the user must act in DSH;
`approval/decided` closes it. Do not synthesize an approval, change permission
policies, or call tools outside the session. The desktop offers a workbench action. The host obtains the origin from
`ctx.webServer.getOrigin()`, creates the authenticated handoff through
`ctx.connection.authenticatedUrl()`, and opens it locally. Never guess a port,
return the authenticated URL to clients, or print its token.

Typed requests such as “read this file”, “write this content” or “search this
page” are interpreted by DSH. Available filesystem/network/skill tools depend on
the installed DSH profile and its permissions. Project skills are discovered from `.dsh/skills/` or `.agents/skills/`; user
skills are discovered from `~/.dsh/skills/` and the configured agents home.
Use an installed skill by asking for it by name; a nonexistent skill is not made available by this plugin.
Full tool output, approvals and durable conversation history remain visible in
DSH. The companion panel shows the reply and the speech bubble shows a short
excerpt; TTS uses its configured speech length limit.

## Transport and verification

The plugin binds loopback. Only loopback bindings are accepted; browser Origin requests and non-JSON
chat POSTs are rejected. No browser CORS access is introduced. `/chat` validates explicit text and IDs; DSH performs prompt
admission and policy enforcement. HTTP network timeouts are transport bounds,
not a wall-clock deadline for Agent work. No automatic POST retry can duplicate
a user-requested mutation.

Fake-context tests verify correlation and routing. A real scratch-workspace
round trip must separately prove host admission, tool activity and the expected
file/result; never infer those from the existence of an exported service type.
