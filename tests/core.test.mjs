import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  buildSystemPrompt,
  buildUserPrompt,
  clampText,
  decodeFrames,
  parseModelOutput,
  resolveConfig,
  sniffImageType,
} from '../lib/core.js'

const PNG = Buffer.concat([
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  Buffer.alloc(16, 1),
])
const JPEG = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), Buffer.alloc(16, 2)])

test('resolveConfig 补默认值并校验', () => {
  const config = resolveConfig({ port: 9000 })
  assert.equal(config.port, 9000)
  assert.equal(config.maxChars, 42)
  assert.ok(config.persona.includes('DeepSeek'))

  assert.throws(() => resolveConfig({ port: 0 }), /port/)
  assert.throws(() => resolveConfig({ maxChars: 1 }), /maxChars/)
})

test('buildSystemPrompt 带上字数上限和 mood 枚举', () => {
  const prompt = buildSystemPrompt({ maxChars: 30, persona: '你是鲨鲨' })
  assert.ok(prompt.includes('不超过 30 个字'))
  assert.ok(prompt.includes('"mood"'))
  assert.ok(prompt.includes('smug'))
})

test('buildUserPrompt 说明顺序与时间戳', () => {
  const text = buildUserPrompt({ count: 3, spanSec: 42, timestamps: ['10:00:01', '10:00:20', '10:00:40'] })
  assert.ok(text.includes('42 秒'))
  assert.ok(text.includes('1=10:00:01'))
  assert.ok(text.includes('从早到晚'))
})

test('buildUserPrompt 认出九宫格拼图', () => {
  const text = buildUserPrompt({ count: 9, spanSec: 30, grid: true })
  assert.ok(text.includes('九宫格'))
  assert.ok(text.includes('1 到 9'))
  assert.ok(!text.includes('张截图'))
})

test('四宫格准确说明四帧而不描述不存在的格子', () => {
  const text = buildUserPrompt({ count: 4, spanSec: 8, grid: true })
  assert.match(text, /2x2 的四宫格/)
  assert.match(text, /1 到 4/)
  assert.ok(!text.includes('九宫格'))
})

test('parseModelOutput 吃标准 JSON', () => {
  const { say, mood } = parseModelOutput('{"say":"你这段代码在打折。","mood":"smug"}', 40)
  assert.equal(say, '你这段代码在打折。')
  assert.equal(mood, 'smug')
})

test('optional quick replies require two distinct short labels and a spoken question', () => {
  const parse = choices => parseModelOutput(JSON.stringify({say: '先交任务还是继续收集？', mood: 'happy', choices}))
  assert.deepEqual(parse(['先交任务', '继续收集']).choices, ['先交任务', '继续收集'])
  for (const choices of [['先交任务'], ['重复', '重复'], ['一'.repeat(13), '继续'], [null, '继续']]) {
    assert.equal(parse(choices).choices, undefined)
    assert.equal(parse(choices).say, '先交任务还是继续收集？')
  }
  assert.equal(parseModelOutput('{"say":"","choices":["先交任务","继续收集"]}').choices, undefined)
})

test('parseModelOutput 吃 ```json 围栏和前后废话', () => {
  const raw = '好的，这是结果：\n```json\n{"say":"摸鱼三十分钟了。","mood":"bored"}\n```\n以上。'
  const out = parseModelOutput(raw, 40)
  assert.equal(out.say, '摸鱼三十分钟了。')
  assert.equal(out.mood, 'bored')
})

test('parseModelOutput 遇到未知 mood 退回 idle', () => {
  assert.equal(parseModelOutput('{"say":"嗯。","mood":"confused"}').mood, 'idle')
})

test('parseModelOutput 不是 JSON 时退化成第一句人话', () => {
  const out = parseModelOutput('- 窗口右下角那个红点又亮了。\n还有别的', 40)
  assert.equal(out.say, '窗口右下角那个红点又亮了。')
  assert.equal(out.mood, 'idle')
})

test('parseModelOutput 空回复返回空串', () => {
  assert.deepEqual(parseModelOutput('', 30), { say: '', mood: 'idle' })
})

test('parseModelOutput preserves deliberate JSON silence', () => {
  for (const raw of ['{"say":"","mood":"idle"}', '```json\n{"say":"  ","mood":"idle"}\n```']) {
    assert.deepEqual(parseModelOutput(raw, 30), { say: '', mood: 'idle' })
  }
})

test('clampText 按字符截断并削掉尾部标点', () => {
  assert.equal(clampText('  一二三四五六  ', 4), '一二三四')
  assert.equal(clampText('一二三四，', 4), '一二三四')
})

test('sniffImageType 认 PNG/JPEG，拒掉别的', () => {
  assert.equal(sniffImageType(PNG), 'image/png')
  assert.equal(sniffImageType(JPEG), 'image/jpeg')
  assert.equal(sniffImageType(Buffer.from('GIF89a----------')), null)
})

test('decodeFrames 解 base64 并保序', () => {
  const { decoded, timestamps } = decodeFrames(
    [
      { data: PNG.toString('base64'), ts: '10:00:01' },
      { data: JPEG.toString('base64'), ts: '10:00:02' },
    ],
    9,
  )
  assert.equal(decoded.length, 2)
  assert.equal(decoded[0].mediaType, 'image/png')
  assert.equal(decoded[1].mediaType, 'image/jpeg')
  assert.deepEqual(timestamps, ['10:00:01', '10:00:02'])
})

test('decodeFrames 拒绝空数组、超量、坏图', () => {
  assert.throws(() => decodeFrames([]), /至少给一张/)
  assert.throws(() => decodeFrames(Array.from({ length: 10 }, () => ({ data: PNG.toString('base64') }))), /最多 9 张/)
  assert.throws(() => decodeFrames([{ data: Buffer.from('not-an-image').toString('base64') }]), /PNG\/JPEG/)
})
