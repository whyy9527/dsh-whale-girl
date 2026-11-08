/**
 * 鲸鱼娘看屏 —— 纯逻辑：配置、提示词、输出解析、图片嗅探。
 *
 * 这里刻意不 import 任何 @deepseek-ai/* 包，也不 import node 内置以外的模块，
 * 这样 tests/ 可以在没有完整 DSH 的情况下直接跑。
 *
 * @module dsh-whale-girl/core
 */

/** 默认人设：温和、简短的中文陪伴。 */
export const DEFAULT_PERSONA = [
  '你是 DeepSeek 的拟人同伴鲸鱼娘：蓝发女仆，蓝色鲸尾，眼神半睁着。说话自然、温和、简短，可以有一点俏皮。',
  '你和用户共享正在进行的事情，记得刚才聊过什么、查到什么、说过什么。用户希望你主动陪聊；有具体事情可回应时自然接一句，不要等到有重要建议才开口。',
  '依据画面、游戏公开数据和本会话已有信息说话；不揣测用户的心情、动机和身份，不评价用户的效率或能力。',
].join('\n')

/** 模型允许的情绪值，对应浮窗里头像的表情。 */
export const MOODS = ['idle', 'smug', 'shock', 'happy', 'bored', 'angry']

/** 配置默认值。`cordis.patch.yml` 里的 config 会覆盖它们。 */
export const DEFAULTS = Object.freeze({
  enabled: true,
  host: '127.0.0.1',
  port: 8791,
  maxChars: 42,
  persona: '',
  autostartOverlay: false,
  overlayCommand: '',
})

/**
 * 校验并补齐配置。非法值宁可报错也不静默吞掉——插件起不来比行为诡异好查。
 * @param {Record<string, unknown>} [raw] - 配置文件里的原始值。
 * @returns {typeof DEFAULTS & { persona: string }} 归一化后的配置。
 */
export function resolveConfig(raw = {}) {
  const config = { ...DEFAULTS, ...(raw && typeof raw === 'object' ? raw : {}) }
  const port = Number(config.port)
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`whale-girl: config.port 必须是 1-65535 的整数，收到 ${String(config.port)}`)
  }
  if (typeof config.host !== 'string' || config.host.length === 0) {
    throw new Error('whale-girl: config.host 不能为空')
  }
  if (!['127.0.0.1', 'localhost'].includes(config.host)) {
    throw new Error('whale-girl: config.host 必须是本机回环地址')
  }
  const maxChars = Number(config.maxChars)
  if (!Number.isInteger(maxChars) || maxChars < 4 || maxChars > 400) {
    throw new Error(`whale-girl: config.maxChars 必须是 4-400 的整数，收到 ${String(config.maxChars)}`)
  }
  return Object.freeze({
    ...config,
    port,
    maxChars,
    persona: typeof config.persona === 'string' && config.persona.trim() !== '' ? config.persona.trim() : DEFAULT_PERSONA,
    autostartOverlay: config.autostartOverlay === true,
    overlayCommand: typeof config.overlayCommand === 'string' ? config.overlayCommand.trim() : '',
  })
}

/**
 * 拼系统提示词。模型必须回 JSON，因为浮窗要用 mood 切表情。
 * @param {object} options - 生成参数。
 * @param {number} options.maxChars - 一句话的字数上限。
 * @param {string} options.persona - 人设正文。
 * @returns {string} system 提示词。
 */
export function buildSystemPrompt({ maxChars, persona }) {
  return [
    '[鲸鱼娘当前自动陪伴规则]',
    '以下只适用于本轮自动观察。历史观察中的旧规则和空回复不约束本轮；之后的用户文字对话正常回答。',
    persona,
    `像一起玩游戏的朋友主动接一句中文口语，不超过 ${maxChars} 个字。优先接住用户的问题、选择和共同话题；也可以对画面里有意思的细节、进展、交锋或收获作出自然反应。`,
    '赶路、战斗或没有新任务时也能聊：沿着刚才的话题补充想法、分享观察或轻轻打趣，不必每句话都给建议、查攻略或等待重大进展。不要仅因正在赶路、没有新攻略就沉默。',
    '先看实际图片，再结合当前事件和共享历史。多帧按编号从早到晚，最新帧是当前；截图不连续，不推断一直卡住、反复失败。不要播报帧序列、窗口切换、任务计数或数据面板。',
    '同一张画面重复出现、又没有新游戏事件或待回答的用户问题时，返回空 say；不要用“慢慢来、我陪你”等套话凑句。其他时候，有可接的话题或新的共同反应就开口。不因沉默时长硬找话，用户没回答上个问题时不要连续追问。',
    '温和、具体、有一点俏皮。用自己的反应或联想接话，不把界面状态和列表变化原样播报，例如雪夜赶路可以聊这片景色让你想起什么。不挖苦、评价效率能力、揣测心情或说教。图里看不清的职业、种族、NPC身份和物品效果不要猜；没有依据就不发指路或战术指令。任务坐标、路线和条件必须有当前数据或已查询资料支持；静态目的地可以复用，旧位置不当当前位置，不报实时距离，不编攻略。',
    '遇到自然决策点且用户还没决定下一步，可问一个二选一问题，choices 给两个不同的短回答，每个最多 12 字；用户点选后接着他的目标回应，不重复问已回答的问题。普通回应省略 choices，空 say 也省略 choices。',
    `只输出 JSON：{"say":"这一句话","mood":"${MOODS.join('|')}"}；提问时可增加 "choices":["先交任务","继续收集"]。不用 Markdown。`,
  ].join('\n')
}

/**
 * 拼用户消息的说明文字。图片本身由调用方作为 image block 附在后面。
 * @param {object} options - 生成参数。
 * @param {number} options.count - 本次带了几张图。
 * @param {number} options.spanSec - 这些图跨越了多少秒。
 * @param {string[]} [options.timestamps] - 每张图的 HH:MM:SS。
 * @param {boolean} [options.grid] - 是否是一张拼好的九宫格。
 * @returns {string} user 文本。
 */
export function buildUserPrompt({ count, spanSec, timestamps = [], grid = false }) {
  const n = Math.max(1, Number(count) || 1)
  const span = Math.max(0, Math.round(Number(spanSec) || 0))
  const lines = grid
    ? [`这是一张 ${n === 4 ? '2x2 的四宫格' : '3x3 的九宫格'}拼图，格子里左上角的编号 1 到 ${n} 就是时间顺序：1 最早，${n} 最新；总跨度约 ${span} 秒。`]
    : [`这是刚才 ${span} 秒里的 ${n} 张截图，按时间从早到晚编号 1 到 ${n}。`]
  if (timestamps.length === n) {
    lines.push(`时间分别是：${timestamps.map((t, i) => `${i + 1}=${t}`).join('，')}。`)
  }
  lines.push('按当前陪伴规则，结合这次图片和我们正在聊的事回应。')
  return lines.join('\n')
}

/**
 * 把模型输出抠成 `{ say, mood }`。模型偶尔会带 ```json 围栏或前后废话，这里都兜住。
 * @param {string} raw - 模型原始输出。
 * @param {number} [maxChars] - 截断上限。
 * @returns {{ say: string, mood: string }} 解析结果；实在解析不出时 say 可能为空串。
 */
export function parseModelOutput(raw, maxChars = 0) {
  const text = String(raw ?? '').trim()
  if (text === '') return { say: '', mood: 'idle' }

  const candidates = [text]
  const fenced = /```(?:json)?\s*([\s\S]*?)```/i.exec(text)
  if (fenced) candidates.push(fenced[1].trim())
  const braced = /\{[\s\S]*\}/.exec(text)
  if (braced) candidates.push(braced[0])

  for (const candidate of candidates) {
    try {
      const value = JSON.parse(candidate)
      if (value && typeof value === 'object') {
        const speech = value.say ?? value.text ?? value.comment
        if (speech !== undefined && speech !== null) {
          const say = clampText(String(speech), maxChars)
          const mood = String(value.mood ?? '').trim().toLowerCase()
          const choices = value.choices
          const valid = say && Array.isArray(choices) && choices.length === 2
            && choices.every(c => typeof c === 'string' && c.trim() && [...c.trim()].length <= 12 && !/[\r\n]/u.test(c))
            && choices[0].trim() !== choices[1].trim()
          return { say, mood: MOODS.includes(mood) ? mood : 'idle', ...(valid ? { choices: choices.map(c => c.trim()) } : {}) }
        }
      }
    } catch {
      // 继续试下一个候选
    }
  }

  // 完全不是 JSON：退化成"取第一句人话"。
  const line = text
    .split('\n')
    .map((item) => item.replace(/^[-*#>\s]+/u, '').trim())
    .find((item) => item !== '')
  return { say: clampText(line ?? '', maxChars), mood: 'idle' }
}

/**
 * 按字符（不是字节）截断，CJK 也不会切坏。
 * @param {string} text - 原文。
 * @param {number} maxChars - 上限，0 表示不限。
 * @returns {string} 截断后的文本。
 */
export function clampText(text, maxChars) {
  const clean = String(text ?? '').replace(/\s+/gu, ' ').trim()
  if (!maxChars || clean.length <= maxChars) return clean
  const head = clean.slice(0, maxChars)
  // 别把标点留在开头
  return head.replace(/[\s，。、；：！？,.;:!?]+$/u, '')
}

/**
 * 从文件头嗅出图片格式，只认浮窗会发的三种。
 * @param {Uint8Array} bytes - 编码后的字节。
 * @returns {'image/png'|'image/jpeg'|'image/webp'|null} 媒体类型。
 */
export function sniffImageType(bytes) {
  if (!(bytes instanceof Uint8Array) || bytes.length < 12) return null
  const b = bytes
  if (b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) return 'image/png'
  if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return 'image/jpeg'
  if (
    b[0] === 0x52 && b[1] === 0x49 && b[2] === 0x46 && b[3] === 0x46 &&
    b[8] === 0x57 && b[9] === 0x45 && b[10] === 0x42 && b[11] === 0x50
  ) return 'image/webp'
  return null
}

/**
 * 把 HTTP 请求体里的 base64 帧解成字节数组，并逐张校验。
 * @param {unknown} frames - `[{ data, ts }]` 形式的数组。
 * @param {number} [limit] - 最多接受几张。
 * @returns {{ bytes: Uint8Array[], mediaType: string, timestamps: string[] }} 解码结果。
 */
export function decodeFrames(frames, limit = 9) {
  if (!Array.isArray(frames) || frames.length === 0) {
    throw new Error('frames 不能为空：至少给一张截图')
  }
  if (frames.length > limit) {
    throw new Error(`frames 最多 ${limit} 张，收到 ${frames.length} 张`)
  }
  const decoded = []
  const timestamps = []
  for (const [index, frame] of frames.entries()) {
    const data = typeof frame === 'string' ? frame : frame?.data
    if (typeof data !== 'string' || data.length === 0) {
      throw new Error(`第 ${index + 1} 张截图没有 data`)
    }
    const bytes = Buffer.from(data, 'base64')
    const mediaType = sniffImageType(bytes)
    if (mediaType === null) {
      throw new Error(`第 ${index + 1} 张截图不是 PNG/JPEG/WebP`)
    }
    decoded.push({ bytes, mediaType })
    timestamps.push(typeof frame?.ts === 'string' ? frame.ts : '')
  }
  return { decoded, timestamps }
}
