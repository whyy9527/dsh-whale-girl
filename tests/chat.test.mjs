import assert from 'node:assert/strict'
import { test } from 'node:test'
import { projectChat, submitChat } from '../lib/chat.js'

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
  assert.deepEqual(projectChat(events, 'mine'), { status: 'complete', text: 'my answer' })
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
  assert.equal(prompt.content[0].text, 'read README.md')
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
