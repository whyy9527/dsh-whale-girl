/**
 * Loopback bridge for screen-only comments and explicit DSH Agent input.
 * The native app owns capture, artwork and speech; DSH owns models, tools,
 * sessions and approvals.
 */

import { spawn, execFile } from 'node:child_process'
import { submitChat, chatStatus } from './chat.js'
import { createServer } from 'node:http'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import {
  buildSystemPrompt,
  buildUserPrompt,
  decodeFrames,
  parseModelOutput,
  resolveConfig,
} from './core.js'

/** cordis 插件名。 */
export const name = 'whale-girl'

/** DSH host services: model, attachments, ordinary sessions and authenticated workbench handoff. */
export const inject = ['llm', 'attachments', 'sessionController', 'webServer', 'connection']

/** 请求体上限：九张 900px 的 PNG 拼完也就几 MB，留足余量。 */
const MAX_BODY_BYTES = 24 * 1024 * 1024

/**
 * 读完整请求体，超限直接拒绝。
 * @param {import('node:http').IncomingMessage} req - 请求。
 * @returns {Promise<Buffer>} 请求体。
 */
function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = []
    let size = 0
    req.on('data', (chunk) => {
      size += chunk.length
      if (size > MAX_BODY_BYTES) {
        reject(new Error(`请求体超过 ${Math.round(MAX_BODY_BYTES / 1024 / 1024)} MB`))
        req.destroy()
        return
      }
      chunks.push(chunk)
    })
    req.on('end', () => resolve(Buffer.concat(chunks)))
    req.on('error', reject)
  })
}

/**
 * 统一的 JSON 响应。
 * @param {import('node:http').ServerResponse} res - 响应。
 * @param {number} status - HTTP 状态码。
 * @param {unknown} payload - 响应体。
 * @returns {void}
 */
function sendJson(res, status, payload) {
  const body = JSON.stringify(payload)
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
    'cache-control': 'no-store',
  })
  res.end(body)
}

/**
 * 把一次模型调用攒成完整文本。
 * @param {object} options - 调用参数。
 * @param {import('@deepseek-ai/cordis').Context} options.ctx - 插件上下文。
 * @param {object} options.config - 已归一化的配置。
 * @param {Uint8Array[]} options.images - 九宫格图片字节（这里只有一张拼好的图，或若干张）。
 * @param {string[]} options.mediaTypes - 每张图的媒体类型。
 * @param {string} options.system - system 提示词。
 * @param {string} options.userText - 用户消息文字。
 * @returns {Promise<{ text: string, usage: object | null }>} 模型输出与用量。
 */
async function callModel({ ctx, config, images, mediaTypes, system, userText }) {
  const refs = await ctx.attachments.saveImages(
    images.map((data, index) => ({
      data,
      mediaType: mediaTypes[index],
      name: `whale-frame-${index + 1}`,
    })),
  )

  const content = [
    ...refs.map((attachment) => ({ type: 'image', attachment })),
    { type: 'text', text: userText },
  ]

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(new Error(`模型 ${config.timeoutMs}ms 没返回`)), config.timeoutMs)
  const options = {
    provider: config.provider,
    model: config.model,
    messages: [{ role: 'user', content }],
    system,
    maxTokens: config.maxTokens,
    temperature: config.temperature,
    signal: controller.signal,
  }
  if (config.reasoningEffort !== '') options.reasoningEffort = config.reasoningEffort

  let text = ''
  let usage = null
  let failure = null
  try {
    for await (const chunk of ctx.llm.stream(options)) {
      if (chunk?.type === 'text-delta') text += chunk.text ?? ''
      else if (chunk?.type === 'usage') usage = chunk.usage ?? usage
      else if (chunk?.type === 'finish' && chunk.reason?.kind === 'error') failure = chunk.reason.failure ?? null
    }
  } finally {
    clearTimeout(timer)
  }

  // dsh-llm 把适配器/路由的失败装进终态 finish chunk，而不是抛出来。
  if (failure !== null) {
    const detail = failure.message ?? failure.code ?? JSON.stringify(failure).slice(0, 200)
    const error = new Error(String(detail))
    error.code = failure.code
    throw error
  }
  return { text, usage }
}

/**
 * 插件入口。
 * @param {import('@deepseek-ai/cordis').Context} ctx - 插件上下文。
 * @param {Record<string, unknown>} rawConfig - cordis 传进来的配置。
 * @returns {void}
 */
export function apply(ctx, rawConfig) {
  const config = resolveConfig(rawConfig)
  if (!config.enabled) return

  /** 单飞：同一时刻只跑一次模型调用，免得浮窗抽风把额度烧穿。 */
  let busy = false
  const startedAt = Date.now()
  const log = []

  /**
   * 处理 `POST /look`：九宫格 → 一句话。
   * @param {import('node:http').IncomingMessage} req - 请求。
   * @param {import('node:http').ServerResponse} res - 响应。
   * @returns {Promise<void>}
   */
  async function handleLook(req, res) {
    if (busy) {
      sendJson(res, 409, { ok: false, busy: true, error: '上一轮还没看完，这轮先跳过' })
      return
    }

    let payload
    try {
      const body = await readBody(req)
      payload = JSON.parse(body.toString('utf8'))
    } catch (error) {
      sendJson(res, 400, { ok: false, error: `请求体不是合法 JSON：${error.message}` })
      return
    }

    let decoded
    try {
      decoded = decodeFrames(payload.frames, 9)
    } catch (error) {
      sendJson(res, 400, { ok: false, error: error.message })
      return
    }

    const spanSec = Number(payload.spanSec ?? 0) || 0
    const system = buildSystemPrompt({ maxChars: config.maxChars, persona: config.persona })
    const userText = buildUserPrompt({
      count: Number(payload.cellCount ?? decoded.decoded.length) || decoded.decoded.length,
      spanSec,
      timestamps: decoded.timestamps,
      grid: payload.grid === true,
    })

    if (payload.dryRun === true) {
      sendJson(res, 200, { ok: true, dryRun: true, system, userText, frames: decoded.decoded.length })
      return
    }

    busy = true
    const started = Date.now()
    try {
      const { text, usage } = await callModel({
        ctx,
        config,
        images: decoded.decoded.map((item) => item.bytes),
        mediaTypes: decoded.decoded.map((item) => item.mediaType),
        system,
        userText,
      })
      const { say, mood } = parseModelOutput(text, config.maxChars)
      if (say === '') {
        sendJson(res, 502, { ok: false, error: '模型没说出人话（空回复）', raw: text.slice(0, 400) })
        return
      }
      const record = {
        at: new Date().toISOString(),
        say,
        mood,
        frames: decoded.decoded.length,
        spanSec,
        ms: Date.now() - started,
        usage,
      }
      log.unshift(record)
      if (log.length > config.logLimit) log.length = config.logLimit
      sendJson(res, 200, { ok: true, ...record })
    } catch (error) {
      const message = error?.message ?? String(error)
      const hint = /image|vision|multimodal|modality/iu.test(message)
        ? '（看起来是模型不支持图片输入：把 provider/model 换成一个支持 vision 的）'
        : ''
      ctx.logger?.warn?.(`whale-girl: 模型调用失败: ${message}`)
      sendJson(res, 500, { ok: false, error: `${message}${hint}` })
    } finally {
      busy = false
    }
  }

  const server = createServer((req, res) => {
    const url = new URL(req.url ?? '/', `http://${config.host}:${config.port}`)
    if (req.method === 'GET' && url.pathname === '/health') {
      sendJson(res, 200, {
        ok: true,
        plugin: 'dsh-whale-girl',
        model: `${config.provider}/${config.model}`,
        busy,
        workbenchUrl: ctx.webServer?.getOrigin(),
        uptimeSec: Math.round((Date.now() - startedAt) / 1000),
        last: log[0] ?? null,
      })
      return
    }
    if (req.method === 'GET' && url.pathname === '/log') {
      sendJson(res, 200, { ok: true, entries: log })
      return
    }
    if (url.pathname === '/workbench' && req.method === 'POST') {
      if (req.headers.origin || !req.headers['content-type']?.startsWith('application/json')) {
        sendJson(res, 403, { ok: false, error: '仅允许本机客户端打开工作台' })
        return
      }
      const authenticatedUrl = ctx.connection.authenticatedUrl(ctx.webServer.getOrigin())
      execFile('open', [authenticatedUrl], error => {
        sendJson(res, error ? 500 : 200, error ? { ok: false, error: '无法打开 DSH 工作台，请检查默认浏览器' } : { ok: true })
      })
      return
    }
    if (url.pathname === '/chat' && ['GET', 'POST'].includes(req.method)) {
      if (req.headers.origin || (req.method === 'POST' && !req.headers['content-type']?.startsWith('application/json'))) {
        sendJson(res, 403, { ok: false, error: '此接口仅接受本机客户端的 JSON 请求' })
        return
      }
      const operation = async () => {
        if (!ctx.sessionController) throw new Error('DSH 会话服务未加载，请通过 dsh web 启动插件')
        if (req.method === 'POST') {
          const payload = JSON.parse((await readBody(req)).toString('utf8'))
          const accepted = await submitChat(ctx.sessionController, {
            text: payload.text,
            sessionId: payload.sessionId,
            cwd: payload.cwd ?? process.cwd(),
          })
          sendJson(res, 202, { ok: true, ...accepted })
        } else {
          const state = await chatStatus(ctx.sessionController, url.searchParams.get('sessionId'), url.searchParams.get('requestId'))
          sendJson(res, 200, { ok: true, ...state })
        }
      }
      operation().catch(error => sendJson(res, 400, { ok: false, error: error.message }))
      return
    }
    if (req.method === 'POST' && url.pathname === '/look') {
      handleLook(req, res).catch((error) => {
        sendJson(res, 500, { ok: false, error: error?.message ?? String(error) })
      })
      return
    }
    sendJson(res, 404, { ok: false, error: `没有这个入口：${req.method} ${url.pathname}` })
  })

  server.on('error', (error) => {
    ctx.logger?.warn?.(`whale-girl: 端口 ${config.port} 起不来: ${error.message}`)
  })

  /**
   * 顺手把浮窗拉起来：`dsh web` 一起，头像就在屏幕上了，不用再开一个终端。
   * 已经在跑（pidfile 活着）就不再拉第二份。
   */
  function startOverlay() {
    const root = dirname(dirname(fileURLToPath(import.meta.url)))
    const command = config.overlayCommand !== '' ? config.overlayCommand : join(root, 'scripts', 'run.sh')
    try {
      const child = spawn(command, [], { detached: true, stdio: 'ignore', cwd: root })
      child.on('error', (error) => ctx.logger?.warn?.(`whale-girl: 浮窗没起来 ${error.message}`))
      child.unref()
      ctx.logger?.info?.(`whale-girl: 拉起浮窗 ${command}`)
    } catch (error) {
      ctx.logger?.warn?.(`whale-girl: 浮窗没起来 ${error.message}`)
    }
  }

  server.listen(config.port, config.host, () => {
    if (config.autostartOverlay) startOverlay()
    ctx.logger?.info?.(`whale-girl: 听在 http://${config.host}:${config.port}（${config.provider}/${config.model}）`)
  })

  ctx.effect(() => () => {
    server.close()
  }, 'whale-girl.http')
}
