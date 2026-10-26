// Mentions and tags in message text (P3-66, design §3.4, §3.5), as pure functions. A sent message holds the tokens
// `@[u:n]` and `#[r:n]` (n counts from 1 in the message's own `mentions` and `refs` lists); the box shows the readable
// label ("@Rachel Lim", "#Lobby finish schedule.pdf") and keeps a mark for each one the reader picked. `build` turns the
// box into the text and the parts to send; `parse` turns a stored message into the pieces the screen draws.

export const MAX_MENTIONS = 20 // the server's cap (mentions.MAX)
export const MAX_REFS = 10 // the server's cap (refs.MAX)
const TOKEN = /@\[u:(\d{1,4})\]|#\[r:(\d{1,4})\]/g
const ZWSP = '\u200b'
const LABEL_MAX = 60

const clean = (v) => String(v || '').replace(/[\r\n\t\u200b]+/g, ' ').replace(/\s+/g, ' ').trim()
const escapeRegex = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const sameThing = (a, b) => a.kind === b.kind && (a.kind === 'mention' ? a.user === b.user : a.doctype === b.doctype && (a.name || a.url) === (b.name || b.url))

// The mark for a person from the @ list ({ user, name }) or an item from the # picker (a card).
export function mentionMark(person) {
  return { kind: 'mention', user: String(person.user), name: clean(person.name || person.user), label: '' }
}

export function refMark(card) {
  // An approval request is known by its reference (#VO-0007 Add 2 skylights), as the chip reads it.
  const title = card.doctype === 'Approval Request' && card.number ? `${card.number} ${card.title || ''}` : card.title || card.name
  const m = { kind: 'ref', doctype: card.doctype, title: clean(title), label: '' }
  if (card.doctype === 'File') m.url = card.url
  else m.name = card.name
  return m
}

// Adds a mark to the reader's marks and gives it its label in the text. The same person or item keeps one label; a
// second, different one with the same label is told apart by a number, so the text never reads two alike.
export function addMark(marks, mark) {
  const found = marks.find((m) => sameThing(m, mark))
  if (found) return { marks, label: found.label }
  const base = (mark.kind === 'mention' ? '@' : '#') + (mark.kind === 'mention' ? mark.name : mark.title).slice(0, LABEL_MAX).trim()
  let label = base
  for (let n = 2; marks.some((m) => m.label === label); n++) label = `${base} (${n})`
  const next = { ...mark, label }
  return { marks: [...marks, next], label }
}

// Marks restored from a draft or an unsent message, never trusted beyond their shape.
export function cleanMarks(list) {
  if (!Array.isArray(list)) return []
  return list.filter((m) => m && (m.kind === 'mention' || m.kind === 'ref') && typeof m.label === 'string' && m.label.length > 1
    && (m.kind === 'mention' ? typeof m.user === 'string' : typeof m.doctype === 'string' && (typeof m.name === 'string' || typeof m.url === 'string')))
    .slice(0, MAX_MENTIONS + MAX_REFS)
}

// Where each mark's label stands in `text`: [{ start, end, mark }], longest label first so one label never eats another,
// and never inside a word ("@Rachel Limbo" is not "@Rachel Lim").
export function spans(text, marks) {
  const list = [...marks].filter((m) => m.label).sort((a, b) => b.label.length - a.label.length)
  if (!list.length || !text) return []
  const pattern = new RegExp(`(?<![\\p{L}\\p{N}_])(?:${list.map((m) => escapeRegex(m.label)).join('|')})(?![\\p{L}\\p{N}_])`, 'gu')
  const found = []
  for (const hit of text.matchAll(pattern)) {
    const mark = list.find((m) => m.label === hit[0])
    if (mark) found.push({ start: hit.index, end: hit.index + hit[0].length, mark })
  }
  return found
}

// What a send carries: the text with a token for each mark the text still names, and the people and items those tokens
// number. `mentions` is [{ user, name }] and `refs` is [{ doctype, title, name | url }] (a file by its address); the
// same person or item uses one slot however often it is named. A token the reader typed by hand is broken, so it can
// never name a slot. Over the caps, the extra marks stay as plain text. `partsOf` makes the server's parts from them.
export function build(text, marks) {
  const raw = String(text || '').replace(/@\[u:/g, `@${ZWSP}[u:`).replace(/#\[r:/g, `#${ZWSP}[r:`)
  const hits = spans(raw, marks)
  const mentions = []
  const refs = []
  let out = ''
  let at = 0
  for (const { start, end, mark } of hits) {
    out += raw.slice(at, start)
    at = end
    if (mark.kind === 'mention') {
      let n = mentions.findIndex((m) => m.user === mark.user) + 1
      if (!n && mentions.length < MAX_MENTIONS) n = mentions.push({ user: mark.user, name: mark.name })
      out += n ? `@[u:${n}]` : raw.slice(start, end)
    } else {
      const key = mark.url || mark.name
      let n = refs.findIndex((r) => r.doctype === mark.doctype && (r.url || r.name) === key) + 1
      if (!n && refs.length < MAX_REFS) n = refs.push({ doctype: mark.doctype, title: mark.title, ...(mark.url ? { url: mark.url } : { name: mark.name }) })
      out += n ? `#[r:${n}]` : raw.slice(start, end)
    }
  }
  out += raw.slice(at)
  return { text: out, mentions, refs }
}

// The parts object the server's send takes for those people and items (only the lists that are not empty).
export function partsOf(mentions, refs) {
  const parts = {}
  if (mentions?.length) parts.mentions = mentions.map((m) => m.user)
  if (refs?.length) parts.refs = refs.map((r) => (r.url ? { doctype: r.doctype, url: r.url } : { doctype: r.doctype, name: r.name }))
  return parts
}

// A sent-but-unsent message drawn as a stored one: the chips for its tokens from the names it was written with.
export function localParts(mentions, refs) {
  return {
    mentions: (mentions || []).map((m, i) => ({ pos: i + 1, user: m.user, name: m.name })),
    refs: (refs || []).map((r, i) => ({ pos: i + 1, doctype: r.doctype, title: r.title })),
  }
}

// The pieces a stored message is drawn from: [{ type: 'text', text } | { type: 'mention', pos, item } | { type: 'ref',
// pos, item }]. `item` is the server's chip or card for that position, or null (the neutral chip). An old "@address"
// shows as the person's chip when the message's mention list names that address (FIT-20).
export function parse(text, { mentions = [], refs = [] } = {}) {
  const people = new Map((mentions || []).map((m) => [m.pos, m]))
  const things = new Map((refs || []).map((r) => [r.pos, r]))
  const pieces = []
  let at = 0
  const body = String(text || '')
  const push = (s) => s && pieces.push(...legacy(s, mentions))
  for (const hit of body.matchAll(TOKEN)) {
    push(body.slice(at, hit.index))
    at = hit.index + hit[0].length
    if (hit[1] !== undefined) pieces.push({ type: 'mention', pos: Number(hit[1]), item: people.get(Number(hit[1])) || null })
    else pieces.push({ type: 'ref', pos: Number(hit[2]), item: things.get(Number(hit[2])) || null })
  }
  push(body.slice(at))
  return pieces
}

function legacy(s, mentions) {
  const known = (mentions || []).filter((m) => m && typeof m.user === 'string' && m.user.includes('@'))
  if (!known.length) return [{ type: 'text', text: s }]
  const pattern = new RegExp(`(?<![\\p{L}\\p{N}_.])@(${known.map((m) => escapeRegex(m.user)).join('|')})(?![\\p{L}\\p{N}_])`, 'gu')
  const out = []
  let at = 0
  for (const hit of s.matchAll(pattern)) {
    if (hit.index > at) out.push({ type: 'text', text: s.slice(at, hit.index) })
    out.push({ type: 'mention', pos: 0, item: known.find((m) => m.user === hit[1]) })
    at = hit.index + hit[0].length
  }
  if (at < s.length) out.push({ type: 'text', text: s.slice(at) })
  return out.length ? out : [{ type: 'text', text: s }]
}

// The token numbers a text names, in order and once each, for the cards under a message.
export function refPositions(text) {
  const seen = []
  for (const hit of String(text || '').matchAll(TOKEN)) if (hit[2] !== undefined && !seen.includes(Number(hit[2]))) seen.push(Number(hit[2]))
  return seen
}

// A line with no parts to draw it from (a thread's name, the inbox's last line, a pointer): the tokens read as words.
// `w` is the reader's chat words.
export function plain(text, w) {
  if (typeof text !== 'string' || !text) return text || ''
  return text.replace(/@\[u:\d{1,4}\]/g, `@${w('mentions.someone')}`).replace(/#\[r:\d{1,4}\]/g, `#${w('refs.item')}`)
}

// A message as one line of words, where there is no room to draw chips (the Agreed list, the remove question): each token
// is the name or title its part gives, or the neutral word. `w` is the reader's chat words.
export function readable(text, parts, w) {
  return parse(text, { mentions: parts?.mentions, refs: parts?.refs }).map((p) => {
    if (p.type === 'text') return p.text
    if (p.type === 'mention') return `@${p.item?.name || w('mentions.someone')}`
    return `#${p.item?.title || w('refs.unavailable')}`
  }).join('')
}

// Where the reader is typing a trigger: "@" or "#" at the start of the text or after a space, then what follows it up to
// the caret (no space right after the trigger, so "meet @ 5pm" and "a@example.com" open nothing). Answers
// { char, start, query } or null; `start` is the trigger's place in the text.
export function triggerAt(text, caret, chars = '@#') {
  const before = String(text || '').slice(0, caret)
  const hit = /(?:^|\s)([@#])((?:[^\s@#][^@#\n]{0,39})?)$/.exec(before)
  if (!hit || !chars.includes(hit[1])) return null
  return { char: hit[1], start: before.length - hit[2].length - 1, query: hit[2] }
}
