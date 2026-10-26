// Previews in lists (P3-75, design §15.3): one batched read of the previews' states for a screen's files or boards,
// and the address of each ready picture. The server answers {id: {state, reason, w, h, meta}} for up to 100 ids at once
// (previews.api.states, which also asks for the ones not made yet); this asks in chunks, never one call per row, and
// asks again for the ones still "pending" a few times, then waits for the screen's next look. The picture itself is
// the endpoint previews.api.image (no-store, so a new revision is never hidden by a cache).
import { reactive } from 'vue'
import { call } from './api.js'

const API = 'construction_core.previews.api.'
export const MAX_IDS = 100
export const AGAIN_MS = [2000, 5000, 10000, 20000] // waits before asking again for previews still being made
// The types the renderer reads (previews.jobs.READ); the server decides, this only saves asking for the rest.
export const PREVIEWABLE = new Set(['pdf', 'jpg', 'jpeg', 'png', 'webp', 'dwg', 'dxf', 'rvt', 'rfa', 'ifc', 'docx', 'xlsx', 'pptx', 'doc', 'xls', 'ppt'])

export const previewable = (name) => PREVIEWABLE.has(String(name || '').split('.').pop().toLowerCase())
export const previewUrl = (kind, id) => `/api/method/${API}image?kind=${encodeURIComponent(kind)}&name=${encodeURIComponent(id)}`

const realTimer = { set: (fn, ms) => setTimeout(fn, ms), clear: (id) => clearTimeout(id) }

export class PreviewBook {
  constructor(kind, { transport = call, timer = realTimer, again = AGAIN_MS } = {}) {
    this.kind = kind
    this.transport = transport
    this.timer = timer
    this.again = again
    this.entries = reactive({})
    this.stamps = new Map() // id -> what the file looked like when it was asked (its modified time)
    this.tries = new Map() // id -> how often a pending one was asked again
    this.waitFor = null
    this.gone = false
  }

  // The entry of one id, or null when it was not asked yet.
  of(id) {
    return this.entries[id] || null
  }

  src(id) {
    return previewUrl(this.kind, id)
  }

  // Ask for these ({ id, stamp }): the ones not known yet, changed since, or still pending from an earlier look. A
  // screen calls it whenever its list changes; ids it already knows cost nothing.
  async want(items) {
    const due = []
    for (const { id, stamp = '' } of items) {
      const known = this.entries[id]
      // A pending one is asked for again only once its own schedule is used up: until then `schedule` has it.
      const spent = (this.tries.get(id) || 0) >= this.again.length
      if (!known || this.stamps.get(id) !== stamp || (known.state === 'pending' && spent)) {
        this.stamps.set(id, stamp)
        this.tries.set(id, 0)
        due.push(id)
      }
    }
    await this.read(due)
    this.schedule()
  }

  async read(ids) {
    for (let at = 0; at < ids.length; at += MAX_IDS) {
      const chunk = ids.slice(at, at + MAX_IDS)
      try {
        const answer = (await this.transport(`${API}states`, { kind: this.kind, ids: chunk }, { post: true })) || {}
        for (const id of chunk) this.entries[id] = answer[id] || { state: 'none', reason: null, w: null, h: null, meta: {} } // not listed: not visible
      } catch {
        // the next look asks again; a row without an entry keeps its icon
      }
    }
  }

  // Ask again for the previews still being made, a few times with longer waits, then leave them to the next look.
  schedule() {
    if (this.waitFor !== null || this.gone) return
    const pending = this.pendingIds()
    if (!pending.length) return
    const round = Math.min(...pending.map((id) => this.tries.get(id) || 0))
    if (round >= this.again.length) return
    this.waitFor = this.timer.set(async () => {
      this.waitFor = null
      const ids = this.pendingIds().filter((id) => (this.tries.get(id) || 0) === round)
      for (const id of ids) this.tries.set(id, round + 1)
      await this.read(ids)
      this.schedule()
    }, this.again[round])
  }

  pendingIds() {
    return Object.keys(this.entries).filter((id) => this.entries[id].state === 'pending' && (this.tries.get(id) || 0) < this.again.length)
  }

  stop() {
    this.gone = true
    if (this.waitFor !== null) this.timer.clear(this.waitFor)
    this.waitFor = null
  }
}
