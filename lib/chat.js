/** Explicit text input uses DSH's Session Controller; screenshots never enter this path. */
import { randomUUID } from 'node:crypto'

export async function submitChat(controller, { text, sessionId, cwd }) {
  if (typeof text !== 'string' || !text.trim()) throw new Error('请输入文字')
  if (text.length > 32000) throw new Error('消息不能超过 32000 字符')
  if (sessionId != null && typeof sessionId !== 'string') throw new Error('sessionId 必须是字符串')
  if (cwd != null && (typeof cwd !== 'string' || !cwd.startsWith('/'))) throw new Error('cwd 必须是绝对路径')
  if (!sessionId) ({ sessionId } = await controller.create({ cwd }))
  const requestId = randomUUID()
  await controller.prompt({
    requestId, sessionId, mode: 'queue',
    content: [{ type: 'text', text: text.trim() }],
    clientTimeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  }, new AbortController().signal)
  return { sessionId, requestId }
}

/** Bind the reply to the admitted request's rpcId and enclosing turn, not the latest message. */
export function projectChat(events, requestId) {
  let currentTurn = null
  let targetTurn = null
  let text = ''
  let reason = null
  const approvals = new Set()
  for (const event of events) {
    if (event.type === 'turn/start') currentTurn = event.data.turn
    if (event.type === 'user/message' && event.data.source?.rpcId === requestId) targetTurn = currentTurn
    if (targetTurn === null || currentTurn !== targetTurn) continue
    if (event.type === 'assistant/message') {
      const value = event.data.message.content.filter(block => block.type === 'text').map(block => block.text).join('')
      if (value) text = value
    }
    if (event.type === 'approval/asked') approvals.add(event.data.id)
    if (event.type === 'approval/decided') approvals.delete(event.data.id)
    if (event.type === 'turn/end' && event.data.turn === targetTurn) {
      reason = event.data.reason
      break
    }
  }
  return {
    status: reason ? (reason.kind === 'completed' ? 'complete' : 'failed') : approvals.size ? 'approval' : targetTurn === null ? 'queued' : 'running',
    text,
    ...(reason && reason.kind !== 'completed' ? { error: reason.error?.message ?? reason.kind } : {}),
  }
}

export async function chatStatus(controller, sessionId, requestId) {
  if (!sessionId || !requestId) throw new Error('缺少 sessionId 或 requestId')
  return projectChat((await controller.inspect(sessionId)).events, requestId)
}
