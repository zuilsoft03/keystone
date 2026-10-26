// The Discussion inbox (P3-74, design §14.6, D-414): the reader's rooms across their projects, from one read
// (host.read('discussion_inbox')) in pages of 50. Live: a message, a part change or the reader's own read in another
// tab or device (cc_discuss_read) reloads it after a short wait, so a burst costs one read; a change event without a
// part is ignored (§14.6). The rows say where a click opens: the room at a message, with a thread open.
import { reactive } from 'vue'
import { onEvent } from '../../realtime.js'
import { CHANGED_EVENT, MESSAGE_EVENT } from '../live.js'
import { plain } from '../tokens.js'

export const READ_EVENT = 'cc_discuss_read'
export const WAIT = 800 // ms between an event and the reload it causes
export const PAGE = 50 // rooms per page, as the server pages them
export const SHOWS = ['', 'unread', 'reply', 'mentions']

export class Inbox {
  constructor(host, query = {}) {
    this.host = host
    this.state = reactive({ rooms: [], projects: [], totals: {}, more: false, loaded: false, loading: false, error: '',
      query: { show: '', project: '', closed: 0, ...query } })
    this.asked = 0
    this.offs = []
    this.timer = null
    this.onLoad = null
  }

  // Read the first page again, and as many more pages as the reader had opened, so a reload keeps their place.
  async load() {
    const ask = ++this.asked
    const pages = Math.max(1, Math.ceil(this.state.rooms.length / PAGE))
    this.state.loading = true
    try {
      let out = await this.read(0)
      const rooms = [...out.rooms]
      for (let p = 1; p < pages && out.more; p += 1) {
        out = await this.read(p * PAGE)
        rooms.push(...out.rooms)
      }
      if (ask !== this.asked) return
      Object.assign(this.state, { rooms, projects: out.projects, totals: out.totals, more: out.more, error: '' })
      if (this.onLoad) this.onLoad(this.state)
    } catch (e) {
      if (ask === this.asked) this.state.error = e.message || 'error'
    } finally {
      if (ask === this.asked) Object.assign(this.state, { loading: false, loaded: true })
    }
  }

  async next() {
    if (!this.state.more || this.state.loading) return
    const ask = ++this.asked
    this.state.loading = true
    try {
      const out = await this.read(this.state.rooms.length)
      if (ask !== this.asked) return
      Object.assign(this.state, { rooms: [...this.state.rooms, ...out.rooms], totals: out.totals, more: out.more })
    } catch (e) {
      if (ask === this.asked) this.state.error = e.message || 'error'
    } finally {
      if (ask === this.asked) this.state.loading = false
    }
  }

  // A new filter starts again at the first page.
  set(query) {
    Object.assign(this.state.query, query)
    this.state.rooms = []
    return this.load()
  }

  read(start) {
    const { show, project, closed } = this.state.query
    const args = { start }
    if (show) args.show = show
    if (project) args.project = project
    if (closed) args.closed = 1
    return this.host.read('discussion_inbox', args)
  }

  listen() {
    if (this.offs.length || this.host.viewer === 'preview') return
    this.offs.push(onEvent(MESSAGE_EVENT, () => this.soon()))
    this.offs.push(onEvent(CHANGED_EVENT, (d) => d && d.part && this.soon()))
    this.offs.push(onEvent(READ_EVENT, () => this.soon()))
  }

  soon() {
    clearTimeout(this.timer)
    this.timer = setTimeout(() => this.load(), WAIT)
  }

  close() {
    this.offs.forEach((off) => off())
    this.offs = []
    clearTimeout(this.timer)
    this.asked += 1
  }
}

// The page's rooms under their projects, in the server's order: [{ project, title, status, rooms }].
export function byProject(rooms, projects) {
  const named = new Map((projects || []).map((p) => [p.name, p]))
  const groups = new Map()
  for (const r of rooms || []) {
    if (!groups.has(r.project)) {
      const p = named.get(r.project) || {}
      groups.set(r.project, { project: r.project, title: p.title || r.project, status: p.status || '', rooms: [] })
    }
    groups.get(r.project).rooms.push(r)
  }
  return [...groups.values()]
}

// "3 new · 2 in threads" (D-414): the room's own unread and the replies in threads the reader follows, apart.
export function countsLine(row, w) {
  const out = []
  if (row.unread) out.push(w('inbox.new', { count: row.unread }))
  if (row.in_threads) out.push(w('inbox.in_threads', { count: row.in_threads }))
  return out.join(' · ')
}

// The newest line: who wrote it and its first line, or the word for its kind (a file has no text of its own).
export function lineOf(row, w) {
  const m = row.last
  if (!m) return { who: '', text: w('inbox.no_line') }
  const first = plain(String(m.text || ''), w).split('\n').map((l) => l.trim()).find(Boolean) || ''
  return { who: m.author?.name || '', text: first || w(`kind.${m.kind}`) || '' }
}

// Where a staff row opens: the project's Discussion at the room, at the message, with its thread open (§14.6).
export function roomLink(row) {
  const query = {}
  if (row.open_thread) query.thread = row.open_thread
  if (row.around) query.at = row.around
  return { name: 'section', params: { project: row.project, section: 'discuss', item: row.room }, query }
}

// Where a client's row opens: the project's Discussion tab in the portal, with the thread open when the line is in one.
export function portalLink(row) {
  const query = { tab: 'discuss' }
  if (row.open_thread) query.thread = row.open_thread
  return { name: 'portal-project', params: { project: row.project }, query }
}
