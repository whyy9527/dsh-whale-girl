import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { apply } from '../lib/host.js'

/** 最小的 cordis 上下文替身：只实现插件用到的那几个口子。 */
function fakeCtx(records) {
  const effects = []
  const saved = []
  return {
    effects,
    saved,
    logger: { info() {}, warn() {} },
    effect(fn) {
      effects.push(fn())
    },
    attachments: {
      async saveImages(inputs) {
        saved.push(...inputs)
        return inputs.map((input, index) => ({
          attachmentId: `sha256:${String(index).padStart(64, '0')}`,
          mediaType: input.mediaType,
          bytes: input.data.byteLength,
          width: 100,
          height: 100,
        }))
      },
    },
    llm: {
      stream(options) {
        records.push(options)
        return (async function* () {
          yield { type: 'block-start', index: 0, blockType: 'text' }
          yield { type: 'text-delta', index: 0, text: '{"say":"' }
          yield { type: 'text-delta', index: 0, text: '你盯着这行报错看了四分钟。","mood":"smug"}' }
          yield { type: 'usage', usage: { inputTokens: 1200, outputTokens: 30 } }
          yield { type: 'finish', reason: { kind: 'stop' } }
        })()
      },
    },
  }
}

const PNG = Buffer.concat([
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  Buffer.alloc(32, 7),
])

// 随机高位端口：别和真在跑的插件的 8791 撞上，撞上了测试会打到真服务上
const PORT = 18000 + (process.pid % 2000)
const base = `http://127.0.0.1:${PORT}`

before(async () => {
  // 端口被占用时整个测试跳过会更好，但这里直接让它报错，方便发现残留进程。
  const ctx = fakeCtx(globalThis.__records ??= [])
  apply(ctx, { port: PORT })
  globalThis.__ctx = ctx
  // 等 listen 回调
  await new Promise((resolve) => setTimeout(resolve, 120))
})

after(() => {
  for (const dispose of globalThis.__ctx.effects) dispose()
})

test('GET /health 报出模型与状态', async () => {
  const response = await fetch(`${base}/health`)
  const body = await response.json()
  assert.equal(response.status, 200)
  assert.equal(body.ok, true)
  assert.equal(body.model, 'deepseek-official/deepseek-flash')
  assert.equal(body.busy, false)
})

test('POST /look 走通模型调用并解析出评论', async () => {
  const response = await fetch(`${base}/look`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      frames: [{ data: PNG.toString('base64'), ts: '10:00:01' }],
      spanSec: 12,
    }),
  })
  const body = await response.json()
  assert.equal(response.status, 200, JSON.stringify(body))
  assert.equal(body.say, '你盯着这行报错看了四分钟。')
  assert.equal(body.mood, 'smug')
  assert.equal(body.frames, 1)

  const call = globalThis.__records.at(-1)
  assert.equal(call.provider, 'deepseek-official')
  assert.equal(call.model, 'deepseek-flash')
  assert.equal(call.messages[0].content[0].type, 'image')
  assert.equal(call.messages[0].content.at(-1).type, 'text')
  assert.ok(call.system.includes('DeepSeek'))
})

test('POST /look dryRun 只回提示词，不碰模型', async () => {
  const before = globalThis.__records.length
  const response = await fetch(`${base}/look`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ frames: [{ data: PNG.toString('base64') }], dryRun: true }),
  })
  const body = await response.json()
  assert.equal(body.ok, true)
  assert.equal(body.dryRun, true)
  assert.ok(body.userText.includes('截图'))
  assert.equal(globalThis.__records.length, before)
})

test('POST /look 拒绝坏输入', async () => {
  const bad = await fetch(`${base}/look`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ frames: [] }),
  })
  assert.equal(bad.status, 400)

  const broken = await fetch(`${base}/look`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: '{not json',
  })
  assert.equal(broken.status, 400)
})

test('GET /log 记下刚才那几句', async () => {
  const response = await fetch(`${base}/log`)
  const body = await response.json()
  assert.ok(body.entries.length >= 1)
  assert.equal(body.entries[0].say, '你盯着这行报错看了四分钟。')
})

test('autostartOverlay 在监听成功后启动可执行文件', async () => {
  const { mkdtemp, writeFile, readFile, rm } = await import('node:fs/promises')
  const { tmpdir } = await import('node:os')
  const { join } = await import('node:path')
  const directory = await mkdtemp(join(tmpdir(), 'whale-autostart-'))
  const marker = join(directory, 'started')
  const command = join(directory, 'overlay')
  const ctx = fakeCtx([])
  try {
    await writeFile(command, `#!/bin/sh\nprintf started > '${marker}'\n`, { mode: 0o755 })
    apply(ctx, { port: PORT + 1, autostartOverlay: true, overlayCommand: command })
    let result
    for (let attempt = 0; attempt < 50; attempt++) {
      try { result = await readFile(marker, 'utf8'); break } catch {}
      await new Promise(resolve => setTimeout(resolve, 20))
    }
    assert.equal(result, 'started')
  } finally {
    for (const dispose of ctx.effects) dispose()
    await rm(directory, { recursive: true, force: true })
  }
})

test('浮窗启动路径不存在时记录错误并保持 HTTP 服务在线', async () => {
  const ctx = fakeCtx([])
  const warnings = []
  ctx.logger.warn = message => warnings.push(message)
  try {
    apply(ctx, { port: PORT + 2, autostartOverlay: true, overlayCommand: '/no-such-whale-overlay' })
    await new Promise(resolve => setTimeout(resolve, 120))
    assert.ok(warnings.some(message => message.includes('ENOENT')))
    const response = await fetch(`http://127.0.0.1:${PORT + 2}/health`)
    assert.equal(response.status, 200)
  } finally {
    for (const dispose of ctx.effects) dispose()
  }
})


test('browser origins cannot submit tool-enabled user text', async () => {
  const response = await fetch(`${base}/chat`, {
    method: 'POST', headers: { 'content-type': 'application/json', origin: 'https://example.com' },
    body: JSON.stringify({ text: 'write a file' }),
  })
  assert.equal(response.status, 403)
})
