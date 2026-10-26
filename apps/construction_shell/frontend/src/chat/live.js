// The live store (P3-64, design §13.2 F6): one conversation's messages, kept current by message. On a message or change
// event for the conversation on screen it reads that one message (host.read('message')) and merges it; it never reloads
// the page and joins no document room (events reach the user's own room, D-394). A message the reader may not read
// answers "not found" like a missing one, and leaves the list (SEC-22).
import { reactive } from 'vue'
import { onEvent } from '../realtime.js'

export const MESSAGE_EVENT = 'cc_discuss_message'
export const CHANGED_EVENT = 'cc_discuss_changed'

export class Timeline {
  constructor(host) {
    this.host = host
    this.state = reactive({ name: '', thread: null, messages: [], cursor: null, newer: null, at: '', error: '', loading: false,
      older: false, newering: false })
    this.asked = 0
    this.offs = []
    this.onNewest = null // called when newerPage() reaches the newest message (the room may then be marked read)
  }

  // Whether the newest message is on screen: a room opened at an older message is not read yet (D-099: seen receipts
  // never say a reader saw messages they did not).
  atNewest() {
    return !this.state.newer && !this.state.loading
  }

  // Open a conversation at its newest page, or around one message (`at`, the inbox's "open at the message", P3-74):
  // then `newer` names the next newer page. An answer for a conversation the reader has left is dropped.
  async open(name, { at = '' } = {}) {
    const ask = ++this.asked
    Object.assign(this.state, { name, thread: null, messages: [], cursor: null, newer: null, at, error: '', loading: Boolean(name) })
    if (!name) return
    try {
      const page = await this.host.read('messages', at ? { thread: name, around: at } : { thread: name })
      if (ask !== this.asked) return
      Object.assign(this.state, { thread: page.thread, messages: [...page.messages].reverse(), cursor: page.cursor,
        newer: page.newer || null })
    } catch (e) {
      if (ask === this.asked) this.state.error = e.message || 'Could not open this conversation.'
    } finally {
      if (ask === this.asked) this.state.loading = false
    }
  }

  async older() {
    const { name, cursor } = this.state
    if (!cursor || this.state.older) return
    this.state.older = true
    try {
      const page = await this.host.read('messages', { thread: name, cursor })
      if (name !== this.state.name) return
      this.state.messages = mergeAll(this.state.messages, page.messages)
      this.state.cursor = page.cursor
    } catch (e) {
      if (name === this.state.name) this.state.error = e.message
    } finally {
      this.state.older = false
    }
  }

  // The page just newer than the newest message on screen, when the conversation opened at an older message.
  async newerPage() {
    const { name, newer } = this.state
    if (!newer || this.state.newering) return
    this.state.newering = true
    try {
      const page = await this.host.read('messages', { thread: name, after: newer })
      if (name !== this.state.name) return
      this.state.messages = mergeAll(this.state.messages, page.messages)
      this.state.newer = page.newer || null
      if (!this.state.newer && this.onNewest) this.onNewest()
    } catch (e) {
      if (name === this.state.name) this.state.error = e.message
    } finally {
      this.state.newering = false
    }
  }

  // Merge the newest page again (after a file was sent, or a "seen" signal), keeping what is on screen.
  async latest() {
    const name = this.state.name
    if (!name) return
    try {
      const page = await this.host.read('messages', { thread: name })
      if (name === this.state.name) this.state.messages = mergeAll(this.state.messages, page.messages)
    } catch { /* the next event or open reads it again */ }
  }

  // Read one message of the conversation on screen and merge it (a send's answer, a live event).
  async refresh(message) {
    const name = this.state.name
    if (!message || !name || this.host.viewer === 'preview') return
    try {
      const m = await this.host.read('message', { name: message })
      if (name === this.state.name) this.state.messages = mergeAll(this.state.messages, [m])
    } catch (e) {
      if (e.type === 'DoesNotExistError' && name === this.state.name) {
        this.state.messages = this.state.messages.filter((x) => x.name !== message)
      }
    }
  }

  // Put a message an action answered (P3-68: react, vote, edit) into the list. A re-read would be stale: the tallies are
  // recounted by a job after the commit, and the answer already carries them.
  merge(message) {
    if (message && message.name) this.state.messages = mergeAll(this.state.messages, [message])
  }

  // Live: one handler per event, removed by close(). `onMessage` hears every message event (row counts, read marks).
  listen({ onMessage } = {}) {
    if (this.host.viewer === 'preview' || this.offs.length) return
    const mine = (d) => d && d.thread === this.state.name
    // Opened at an older message (`newer` is set): a new message waits for "Show newer messages", so no gap is hidden.
    const shown = (d) => !this.state.newer || this.state.messages.some((m) => m.name === d.message)
    this.offs.push(onEvent(MESSAGE_EVENT, (d) => {
      if (mine(d) && shown(d)) this.refresh(d.message)
      if (onMessage) onMessage(d)
    }))
    this.offs.push(onEvent(CHANGED_EVENT, (d) => mine(d) && shown(d) && this.refresh(d.message)))
  }

  close() {
    this.offs.forEach((off) => off())
    this.offs = []
    this.asked += 1
  }
}

// Oldest first, one row per name; a newer copy of a message replaces the old one.
export function mergeAll(list, incoming) {
  const byName = new Map(list.map((m) => [m.name, m]))
  for (const m of incoming || []) if (m && m.name) byName.set(m.name, m)
  return [...byName.values()].sort(order)
}

function order(a, b) {
  if (a.creation !== b.creation) return a.creation < b.creation ? -1 : 1
  return a.name < b.name ? -1 : a.name > b.name ? 1 : 0
}
