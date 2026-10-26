// The unsent store (P3-64): each message on its way, or not sent, kept per person and thread for the tab's life with
// the id of its one send. A retry sends the same id, so the server answers with the first message if it was stored
// after all (F8): nothing is posted twice. The keys sit under the drafts' prefix (drafts.js), so sign-out and another
// person's start clear them with the drafts.
import { keyOf } from '../sections/drafts.js'

const keyFor = (user, thread) => keyOf(user, `unsent:${thread}`)

export function newClientId() {
  const bytes = new Uint8Array(12)
  globalThis.crypto.getRandomValues(bytes)
  return `cc${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`
}

export function loadUnsent(storage, user, thread) {
  if (!storage || !user || !thread) return []
  try {
    const rows = JSON.parse(storage.getItem(keyFor(user, thread)) || '[]')
    return Array.isArray(rows) ? rows.filter(valid) : []
  } catch {
    return []
  }
}

// A page that opens finds no send of its own in flight: an entry left "sending" by an earlier page is "failed" now.
export function openUnsent(storage, user, thread) {
  return loadUnsent(storage, user, thread).map((r) => (r.state === 'sending' ? { ...r, state: 'failed' } : r))
}

export function saveUnsent(storage, user, thread, rows) {
  if (!storage || !user || !thread) return
  try {
    if (!rows.length) storage.removeItem(keyFor(user, thread))
    else storage.setItem(keyFor(user, thread), JSON.stringify(rows.map(({ client_id, text, at, state, also_room, attachments, files, mentions, refs, voice }) => ({ client_id, text, at, state, also_room: Boolean(also_room),
      attachments: ids(attachments), files: (files || []).map(String), ...tagged(mentions, refs), ...noted(voice) }))))
  } catch { /* storage full or blocked: the entry lives in the open page only */ }
}

// One thread's entries as a small object the screen keeps reactive (rows is replaced on each change).
export class UnsentList {
  constructor(storage, user, thread) {
    Object.assign(this, { storage, user, thread })
    this.rows = openUnsent(storage, user, thread)
  }

  add(text, now = new Date(), { also_room = false, attachments = [], files = [], mentions = [], refs = [], voice = null } = {}) {
    const row = { client_id: newClientId(), text, at: now.toISOString(), state: 'sending', also_room: Boolean(also_room),
      attachments: ids(attachments), files: [...files], ...tagged(mentions, refs), ...noted(voice) }
    this.save([...this.rows, row])
    return row
  }

  mark(clientId, state) {
    this.save(this.rows.map((r) => (r.client_id === clientId ? { ...r, state } : r)))
  }

  remove(clientId) {
    this.save(this.rows.filter((r) => r.client_id !== clientId))
  }

  save(rows) {
    this.rows = rows
    saveUnsent(this.storage, this.user, this.thread, rows)
  }
}

// The staged files' ids a message carries (P3-65): ids only, never a File id or a name the server would trust.
function ids(list) {
  return Array.isArray(list) ? list.filter((a) => typeof a === 'string' && /^[A-Za-z0-9]{1,40}$/.test(a)) : []
}

// P3-66: the people and items a message's tokens number, kept with it so a retry sends the same slots (a token with no
// slot would be refused). Present only when the message has any. Shapes are checked on the way in and out.
function tagged(mentions, refs) {
  const people = (Array.isArray(mentions) ? mentions : []).filter((m) => m && typeof m.user === 'string' && m.user).map((m) => ({ user: m.user, name: String(m.name || '') }))
  const things = (Array.isArray(refs) ? refs : []).filter((r) => r && typeof r.doctype === 'string' && (typeof r.name === 'string' || typeof r.url === 'string'))
    .map((r) => ({ doctype: r.doctype, title: String(r.title || ''), ...(typeof r.url === 'string' ? { url: r.url } : { name: r.name }) }))
  return { ...(people.length ? { mentions: people } : {}), ...(things.length ? { refs: things } : {}) }
}

// P3-67: a voice note's staged id and waveform, kept with its message so a retry sends the same note. Whole numbers
// only; the server checks the count and the range again.
function noted(voice) {
  if (!voice || typeof voice.attachment !== 'string' || !/^[A-Za-z0-9]{1,40}$/.test(voice.attachment) || !Array.isArray(voice.waveform)) return {}
  return { voice: { attachment: voice.attachment, waveform: voice.waveform.filter((n) => Number.isInteger(n)) } }
}

function valid(r) {
  return r && typeof r.client_id === 'string' && /^[A-Za-z0-9_-]{8,64}$/.test(r.client_id) && typeof r.text === 'string'
    && (r.state === 'sending' || r.state === 'failed')
}
