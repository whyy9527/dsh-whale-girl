import assert from 'node:assert/strict'
import { test } from 'node:test'
import { projectChat, submitChat, submitLook, projectHistory, installScreenPolicy, isLookTurn, LOOK_PREFIX } from '../lib/chat.js'

const event = (type, data) => ({ type, data })
const answer = text => event('assistant/message', { message: { content: [{ type: 'text', text }] } })

test('binds replies to rpcId and ignores other queued turns', () => {
  const events = [
    event('turn/start', { turn: 1 }), event('user/message', { source: { rpcId: 'other' } }), answer('other answer'),
    event('turn/end', { turn: 1, reason: { kind: 'completed' } }),
    event('turn/start', { turn: 2 }), event('user/message', { source: { rpcId: 'mine' } }), answer('my answer'),
    event('turn/end', { turn: 2, reason: { kind: 'completed' } }),
    event('turn/start', { turn: 3 }), answer('later unrelated answer'),
  ]
  assert.deepEqual(projectChat(events, 'mine'), { kind: 'text', status: 'complete', text: 'my answer' })
  assert.equal(projectChat(events, 'not-admitted').status, 'queued')
})

test('exposes approval waits and turn failure without granting anything', () => {
  const events = [event('turn/start', { turn: 1 }), event('user/message', { source: { rpcId: 'mine' } }), event('approval/asked', { id: 'a' })]
  assert.equal(projectChat(events, 'mine').status, 'approval')
  events.push(event('approval/decided', { id: 'a', outcome: 'rejected' }))
  assert.equal(projectChat(events, 'mine').status, 'running')
  events.push(event('turn/end', { turn: 1, reason: { kind: 'error', error: { message: 'failed' } } }))
  assert.equal(projectChat(events, 'mine').error, 'failed')
})

test('explicit text goes through DSH Session Controller and keeps existing session identity', async () => {
  let prompt
  const controller = { create: async options => ({ sessionId: 'new-session' }), prompt: async request => { prompt = request } }
  const result = await submitChat(controller, { text: 'read README.md', sessionId: 'chosen-session' })
  assert.equal(result.sessionId, 'chosen-session')
  assert.equal(prompt.sessionId, 'chosen-session')
  assert.ok(prompt.content[0].text.endsWith('read README.md'))
  assert.equal(prompt.requestId, result.requestId)
  assert.equal(prompt.mode, 'queue')
})

test('tool activity is retained in the same request turn', () => {
  const events = [
    event('turn/start', { turn: 2 }), event('user/message', { source: { rpcId: 'mine' } }),
    answer('I will read the file'), event('tool/result', { content: 'file text' }), answer('Read complete'),
    event('turn/end', { turn: 2, reason: { kind: 'completed' } }),
  ]
  assert.equal(projectChat(events, 'mine').text, 'Read complete')
})


test('observations and text reuse the same session with native image parts', async () => {
  const prompts = []
  const controller = { prompt: async request => prompts.push(request) }
  const receipt = await submitLook(controller, { sessionId: 'shared', instructions: 'short JSON', images: [{ bytes: Buffer.from('image'), mediaType: 'image/png' }] })
  await submitChat(controller, { sessionId: receipt.sessionId, text: 'remember that scene' })
  assert.equal(receipt.kind, 'look')
  assert.ok(receipt.requestId.startsWith(LOOK_PREFIX))
  assert.equal(prompts[0].content[1].type, 'image')
  assert.equal(prompts[0].content[1].data, Buffer.from('image').toString('base64'))
  assert.deepEqual(prompts.map(p => p.sessionId), ['shared', 'shared'])
})

test('automatic-turn policy survives durable compaction markers and restores text tools', async () => {
  const listeners = new Map()
  let guard
  const ctx = { on: (name, fn) => listeners.set(name, fn), tools: { guard: fn => { guard = fn; return () => {} } }, effect: fn => fn() }
  installScreenPolicy(ctx)
  const events = [event('turn/start', { turn: 1 }), event('user/message', { source: { rpcId: LOOK_PREFIX + 'one' } }), event('compaction/summary', {})]
  const agent = { session: { snapshotEvents: () => events } }
  listeners.get('agent/inbox/claimed')({ agent, turn: 1, message: { source: { rpcId: LOOK_PREFIX + 'one' } } })
  const assemble = () => ({ sections: [], contexts: [], tools: [{ name: 'write' }], variables: {} })
  const screen = await listeners.get('system-prompt/assemble')(null, { scope: agent }, async () => assemble())
  assert.deepEqual(screen.tools, [])
  assert.match(guard({ agent }), /明确文字请求/)
  events.push(event('turn/end', { turn: 1 }), event('turn/start', { turn: 2 }), event('user/message', { source: { rpcId: 'human' } }))
  listeners.get('agent/inbox/claimed')({ agent, turn: 2, message: { source: { rpcId: 'human' } } })
  assert.equal(isLookTurn(events), false)
  assert.equal(guard({ agent }), undefined)
  const text = await listeners.get('system-prompt/assemble')(null, { scope: agent }, async () => assemble())
  assert.equal(text.tools[0].name, 'write')
})

test('shared transcript restores readable text and comments while retaining silence in DSH only', () => {
  const events = [
    event('turn/start', { turn: 1 }), event('user/message', { source: { rpcId: 'human' }, content: [{ type: 'text', text: 'my class is mage' }] }), answer('记住了'), event('turn/end', { turn: 1 }),
    event('turn/start', { turn: 2 }), event('user/message', { source: { rpcId: LOOK_PREFIX + 'x' }, content: [{ type: 'text', text: 'observation instructions' }] }), answer('{"say":"法师到了城门。","mood":"happy"}'), event('turn/end', { turn: 2 }),
    event('turn/start', { turn: 3 }), event('user/message', { source: { rpcId: LOOK_PREFIX + 'y' } }), answer('{"say":"","mood":"idle"}'), event('turn/end', { turn: 3, reason: { kind: 'completed' } }),
  ]
  assert.deepEqual(projectHistory(events), [{ name: '你', text: 'my class is mage' }, { name: 'DSH', text: '记住了' }, { name: '看屏', text: '法师到了城门。' }])
  assert.equal(projectChat(events, LOOK_PREFIX + 'y').text, '')
  assert.equal(projectHistory(events, 42, LOOK_PREFIX + 'x').length, 2)
})
