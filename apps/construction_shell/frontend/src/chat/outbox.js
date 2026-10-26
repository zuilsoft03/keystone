// What one reader is writing and sending (P3-64): each room's draft (drafts.js, F4) and its unsent messages (unsent.js),
// for the screen that shows the room. A send that finishes after the reader moved to another room touches only its own
// room's entries.
import { reactive } from 'vue'
import { boot } from '../boot.js'
import { clearDraft, clearOtherUsers, draftStorage, loadDraft, saveDraft } from '../sections/drafts.js'
import { cleanMarks, partsOf } from './tokens.js'
import { UnsentList } from './unsent.js'

export class Outbox {
  constructor(host, user = boot.user || '') {
    this.host = host
    this.user = user
    this.storage = draftStorage()
    this.lists = new Map()
    this.picks = new Map() // room -> the marks of its draft (P3-66)
    this.reasons = reactive({}) // client_id -> the server's answer to a failed send, shown with "Not sent"
    if (!host?.readOnly) clearOtherUsers(this.storage, user) // a read-only view touches no draft (audit F2)
  }

  // A room's saved draft. An old draft marked as a staff-only note is never put into a box clients read (D-419): it
  // is dropped and the room says so; in the Team room its text stays.
  draft(room, audience) {
    const d = loadDraft(this.storage, this.user, room)
    if (d.staffOnly && audience !== 'Internal') {
      clearDraft(this.storage, this.user, room)
      this.picks.delete(room)
      return { text: '', dropped: true }
    }
    const marks = cleanMarks(d.marks) // P3-66: the people and items picked into the draft's text
    this.picks.set(room, marks)
    return { text: d.text, dropped: false, ...(marks.length ? { marks } : {}) }
  }

  keep(room, text) {
    saveDraft(this.storage, this.user, room, { text, marks: this.picks.get(room) || [] })
  }

  // The marks of a room's box changed (a person or an item picked, or the text sent): kept with its draft.
  pick(room, marks, text) {
    this.picks.set(room, marks)
    this.keep(room, text)
  }

  list(room) {
    if (!this.lists.has(room)) this.lists.set(room, reactive(new UnsentList(this.storage, this.user, room)))
    return this.lists.get(room)
  }

  // Send `text` to `room` as a new unsent entry; resolves to the stored message's name, or null when it failed (the
  // entry stays, marked "failed", for Retry or Delete). A retry sends the same id: when the first send was stored after
  // all, the server answers with that message, and the entry goes (D-8 of the round-1 review: never both).
  // `also_room`: a thread reply also shown in its room (§14.1, off by default). `attachments`: the ids of the files the
  // tray staged (P3-65), sent as the attachments part, and `files` their names, shown on the unsent row; a retry sends
  // the same ids, which the server still holds for 24 hours (D-389).
  // `mentions` and `refs` (P3-66): the people and items the text's tokens number (tokens.js build), sent as the mentions
  // and refs parts and kept with the unsent row for a retry. `voice` (P3-67): { attachment, waveform }, the voice part, sent
  // on its own (never with files).
  send(room, text, { also_room = false, attachments = [], files = [], mentions = [], refs = [], voice = null } = {}) {
    const row = this.list(room).add(text, new Date(), { also_room, attachments, files, mentions, refs, voice })
    return this.deliver(room, row)
  }

  retry(room, clientId) {
    const row = this.list(room).rows.find((r) => r.client_id === clientId)
    if (!row || row.state === 'sending') return Promise.resolve(null)
    this.list(room).mark(clientId, 'sending')
    return this.deliver(room, row)
  }

  discard(room, clientId) {
    this.list(room).remove(clientId)
    delete this.reasons[clientId]
  }

  async deliver(room, row) {
    try {
      const parts = { ...(row.attachments?.length ? { attachments: row.attachments } : {}), ...(row.voice ? { voice: row.voice } : {}), ...partsOf(row.mentions, row.refs) }
      const name = await this.host.send({ thread: room, text: row.text, client_id: row.client_id, also_room: row.also_room, parts: Object.keys(parts).length ? parts : undefined })
      this.discard(room, row.client_id)
      return name
    } catch (e) {
      this.list(room).mark(row.client_id, 'failed')
      this.reasons[row.client_id] = e.message || ''
      return null
    }
  }
}
