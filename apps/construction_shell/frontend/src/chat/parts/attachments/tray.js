// The attach tray (P3-65, design §3.2, canvas "The composer" frame 2): the files a message will carry. Each file is
// staged by the server as soon as it is picked (host.upload, two at a time, FIT-14) with its progress, and can be taken
// out while it uploads (cancelled) or after (the server deletes the waiting copy, D-389). The send carries the ids of
// the ready files as its attachments part; the server claims them. At most MAX_FILES a message.
// One tray per conversation for the page's life, like its draft (trayOf): leaving the room (a portal tab, a phone's
// thread screen) keeps what waits in it. A file goes only when it is taken out, sent, or its 24 hours have passed.
// P3-75 (D-417): a large file is scanned after the request. Its answer says `checking`, and the tray asks the server
// (host.read('checking')) until it is clean (ready) or refused (a reason). A checking or refused file blocks Send; a
// refused file leaves only when the reader removes it, and an id the server no longer lists is never taken as ready.
import { markRaw, reactive } from 'vue'
import { captureTime } from './exif.js'
import { shrinkImage } from './shrink.js'

export const MAX_FILES = 10
export const AT_ONCE = 2
// What the server accepts in chat (client_files.CLIENT_TYPES); the Team room also takes Revit families and SketchUp
// files (client_files.STAFF_ROOM_TYPES, P3-75).
export const ACCEPT = '.pdf,.jpg,.jpeg,.png,.webp,.docx,.xlsx,.pptx,.dwg,.dxf,.rvt,.ifc'
export const TEAM_ROOM_ACCEPT = `${ACCEPT},.rfa,.skp`
// Take photo: JPEG, PNG and WebP only, so an iPhone hands over a JPEG, never its HEIC (§3.3).
export const PHOTO_ACCEPT = 'image/jpeg,image/png,image/webp'
const PHOTO = /\.(jpe?g|png|webp)$/i
export const CHECK_MS = 2000 // between asks while a large file is checked
export const CHECK_MAX_MS = 10000 // the longest wait between asks after the network failed
export const KEEP_MS = 23.5 * 3600 * 1000 // a waiting file the server deletes after 24 hours (D-389) leaves the tray first
let seq = 0
const trays = new Map()

export const isPhoto = (name) => PHOTO.test(name || '')

// The page's tray for one conversation, made on first use and kept while the page lives.
export function trayOf(host, thread) {
  const key = `${host.viewer}:${thread}`
  if (!trays.has(key)) {
    const tray = new Tray(host)
    tray.thread = thread
    trays.set(key, tray)
  }
  const tray = trays.get(key)
  tray.prune()
  return tray
}

// The reasons the server gives for a refused large file; any other reason reads as "This file cannot be sent".
export const REFUSALS = ['threat', 'could_not_check', 'not_stored', 'gone']

export class Tray {
  constructor(host, { shrink = shrinkImage, takenOf = captureTime, atOnce = AT_ONCE, timer = realTimer, checkMs = CHECK_MS } = {}) {
    this.host = host
    this.timer = timer
    this.checkMs = checkMs
    this.waitFor = null
    this.misses = 0
    this.shrink = shrink
    this.takenOf = takenOf
    this.atOnce = atOnce
    this.thread = ''
    this.state = reactive({ items: [], error: '', original: false, max: MAX_FILES })
  }

  get items() {
    return this.state.items
  }

  get busy() {
    return this.items.some((i) => i.state === 'waiting' || i.state === 'uploading')
  }

  // A file being checked or refused keeps Send off (P3-75): nothing is sent with it, and nothing is sent without it.
  get blocked() {
    return this.items.some((i) => i.state === 'checking' || i.state === 'refused')
  }

  get checking() {
    return this.items.some((i) => i.state === 'checking')
  }

  get refused() {
    return this.items.some((i) => i.state === 'refused')
  }

  ids() {
    return this.items.filter((i) => i.state === 'ready').map((i) => i.attachment)
  }

  names() {
    return this.items.filter((i) => i.state === 'ready').map((i) => i.file_name)
  }

  // Files from the device, a paste, a drop or the camera. `shrink`: picked on a phone, so photos are made smaller
  // unless "Send original quality" is ticked. More than MAX_FILES: the rest are left out and the tray says so.
  add(files, { shrink = false } = {}) {
    const list = [...(files || [])]
    const room = Math.max(0, MAX_FILES - this.items.length)
    this.state.error = list.length > room ? 'too_many' : ''
    for (const file of list.slice(0, room)) {
      const photo = isPhoto(file.name)
      this.items.push({ key: ++seq, file: markRaw(file), file_name: file.name, size: file.size, kind: photo ? 'photo' : 'file',
        state: 'waiting', progress: 0, error: '', reason: '', attachment: '', abort: null, shrink, thumb: photo ? thumbOf(file) : '', at: Date.now() })
    }
    this.pump()
  }

  // A file the server staged from Files (Attach from Files, Ask about this file): ready at once.
  link(answer) {
    if (this.items.length >= MAX_FILES) {
      this.state.error = 'too_many'
      return
    }
    const item = { key: ++seq, file: null, file_name: answer.file_name, size: answer.size, kind: answer.kind || 'file',
      state: 'ready', progress: 1, error: '', reason: '', attachment: answer.attachment, abort: null, shrink: false, thumb: '', at: Date.now() }
    this.settle(item, answer)
    this.items.push(item)
    if (item.state === 'checking') this.watch()
  }

  // What the server says of a staged file: still being checked, refused for a reason, or ready to send.
  settle(item, answer) {
    if (answer?.reason) Object.assign(item, { state: 'refused', reason: answer.reason })
    else if (answer?.checking) Object.assign(item, { state: 'checking', reason: '' })
    else Object.assign(item, { state: 'ready', reason: '' })
  }

  // Ask the server about the files being checked, until none is left. One ask at a time; a failed ask tries again later.
  watch() {
    if (this.waitFor || !this.checking) return
    this.waitFor = this.timer.set(() => this.ask(), Math.min(CHECK_MAX_MS, this.checkMs * (1 + this.misses)))
  }

  async ask() {
    this.waitFor = null
    const items = this.items.filter((i) => i.state === 'checking')
    if (!items.length) return
    try {
      const answer = (await this.host.read('checking', { attachments: items.map((i) => i.attachment) })) || {}
      this.misses = 0
      for (const item of items) {
        if (item.state !== 'checking') continue // taken out, or settled, while the ask was away
        const now = answer[item.attachment]
        if (!now) Object.assign(item, { state: 'refused', reason: 'gone' }) // no longer waiting: never taken as ready
        else this.settle(item, now)
      }
    } catch {
      this.misses += 1
    }
    this.watch()
  }

  // A file refused for a passing reason (a third upload at once from another tab, the network) is tried again.
  retry(key) {
    const item = this.items.find((i) => i.key === key)
    if (!item || item.state !== 'failed' || !item.file) return
    Object.assign(item, { state: 'waiting', error: '', progress: 0 })
    this.pump()
  }

  // Files whose waiting copy the server has deleted by now leave the tray (nothing to discard).
  prune(now = Date.now()) {
    for (let i = this.items.length - 1; i >= 0; i--) {
      const item = this.items[i]
      if (item.state !== 'uploading' && now - (item.at || now) > KEEP_MS) {
        this.items.splice(i, 1)
        if (item.thumb) URL.revokeObjectURL(item.thumb)
      }
    }
  }

  pump() {
    const running = this.items.filter((i) => i.state === 'uploading').length
    for (const item of this.items.filter((i) => i.state === 'waiting').slice(0, Math.max(0, this.atOnce - running))) {
      this.start(item)
    }
  }

  async start(item) {
    item.state = 'uploading'
    const thread = this.thread
    try {
      let file = item.file
      const takenOn = item.kind === 'photo' ? await this.takenOf(file) : ''
      if (item.shrink && !this.state.original && item.kind === 'photo') file = await this.shrink(file)
      if (item.state !== 'uploading') return // taken out meanwhile
      const job = this.host.upload(thread, file, { onProgress: (p) => (item.progress = p), takenOn })
      item.abort = job.abort
      const answer = await job.done
      if (thread !== this.thread || !this.items.includes(item)) {
        this.discard(answer?.attachment) // the tray moved on while it uploaded
        return
      }
      Object.assign(item, { progress: 1, attachment: answer.attachment, size: answer.size ?? item.size,
        kind: answer.kind || item.kind, abort: null })
      this.settle(item, answer)
      if (item.state === 'checking') this.watch()
    } catch (e) {
      if (!e?.cancelled && this.items.includes(item)) Object.assign(item, { state: 'failed', error: e?.message || '', abort: null })
    } finally {
      this.pump()
    }
  }

  remove(key) {
    const at = this.items.findIndex((i) => i.key === key)
    if (at < 0) return
    const [item] = this.items.splice(at, 1)
    this.drop(item)
    this.state.error = ''
    this.pump()
  }

  // After a send: the ready files belong to the message now; nothing is discarded.
  sent() {
    this.stopWatching()
    for (const item of this.items.splice(0)) if (item.thumb) URL.revokeObjectURL(item.thumb)
    this.state.error = ''
    this.state.original = false
  }

  stopWatching() {
    if (this.waitFor !== null) this.timer.clear(this.waitFor)
    this.waitFor = null
  }

  drop(item) {
    if (item.state === 'uploading') item.abort?.()
    item.state = 'removed'
    if (item.attachment) this.discard(item.attachment)
    if (item.thumb) URL.revokeObjectURL(item.thumb)
  }

  discard(attachment) {
    if (attachment && this.host.act) this.host.act('attachments', 'discard', { attachment }).catch(() => {})
  }
}

const realTimer = { set: (fn, ms) => setTimeout(fn, ms), clear: (id) => clearTimeout(id) }

function thumbOf(file) {
  try {
    return typeof URL.createObjectURL === 'function' ? URL.createObjectURL(file) : ''
  } catch {
    return ''
  }
}
