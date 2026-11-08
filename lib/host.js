/**
 * Loopback bridge for one shared DSH conversation with text and screen observations.
 * The native app owns capture, artwork and speech; DSH owns models, tools,
 * sessions and approvals.
 */

import { spawn, execFile } from 'node:child_process'
import { submitChat, submitLook, chatStatus, projectHistory, installScreenPolicy } from './chat.js'
import { createServer } from 'node:http'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import {
  buildSystemPrompt,
  buildUserPrompt,
  decodeFrames,
  resolveConfig,
} from './core.js'

/** cordis 插件名。 */
export const name = 'whale-girl'

/** DSH host services: tools, ordinary sessions and authenticated workbench handoff. */
export const inject = ['tools', 'sessionController', 'webServer', 'connection']

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
 * 插件入口。
 * @param {import('@deepseek-ai/cordis').Context} ctx - 插件上下文。
 * @param {Record<string, unknown>} rawConfig - cordis 传进来的配置。
 * @returns {void}
 */
export function apply(ctx, rawConfig) {
  const config = resolveConfig(rawConfig)
  if (!config.enabled) return

  installScreenPolicy(ctx)
  const startedAt = Date.now()

  /**
   * 处理 `POST /look`：将观察排入共享会话，返回回执。
   * @param {import('node:http').IncomingMessage} req - 请求。
   * @param {import('node:http').ServerResponse} res - 响应。
   * @returns {Promise<void>}
   */
  async function handleLook(req, res) {
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

    const accepted = await submitLook(ctx.sessionController, {
      sessionId: payload.sessionId, cwd: payload.cwd ?? process.cwd(),
      images: decoded.decoded, instructions: `${system}\n\n${userText}`,
      game: payload.game,
    })
    sendJson(res, 202, { ok: true, ...accepted })
  }

  const server = createServer((req, res) => {
    const url = new URL(req.url ?? '/', `http://${config.host}:${config.port}`)
    if (req.method === 'GET' && url.pathname === '/health') {
      sendJson(res, 200, {
        ok: true,
        plugin: 'dsh-whale-girl',
        sharedSession: true,
        workbenchUrl: ctx.webServer?.getOrigin(),
        uptimeSec: Math.round((Date.now() - startedAt) / 1000),
      })
      return
    }
    if (req.method === 'GET' && url.pathname === '/history') {
      if (req.headers.origin) {
        sendJson(res, 403, { ok: false, error: '仅允许本机客户端读取历史' })
        return
      }
      const sessionId = url.searchParams.get('sessionId')
      if (!sessionId) { sendJson(res, 400, { ok: false, error: '缺少 sessionId' }); return }
      ctx.sessionController.inspect(sessionId).then(state => {
        sendJson(res, 200, { ok: true, entries: projectHistory(state.events, config.maxChars, url.searchParams.get('excludeRequestId')) })
      }).catch(error => sendJson(res, 400, { ok: false, error: error.message }))
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
            game: payload.game,
          })
          sendJson(res, 202, { ok: true, ...accepted })
        } else {
          const state = await chatStatus(ctx.sessionController, url.searchParams.get('sessionId'), url.searchParams.get('requestId'), config.maxChars)
          sendJson(res, 200, { ok: true, ...state })
        }
      }
      operation().catch(error => sendJson(res, 400, { ok: false, error: error.message }))
      return
    }
    if (req.method === 'POST' && url.pathname === '/look') {
      if (req.headers.origin || !req.headers['content-type']?.startsWith('application/json')) {
        sendJson(res, 403, { ok: false, error: '仅允许本机客户端提交观察' }); return
      }
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
    ctx.logger?.info?.(`whale-girl: 听在 http://${config.host}:${config.port}（共享 DSH 会话）`)
  })

  ctx.effect(() => () => {
    server.close()
  }, 'whale-girl.http')
}
