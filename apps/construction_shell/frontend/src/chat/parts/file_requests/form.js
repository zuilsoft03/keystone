// The file request builder's rules (P3-71, design §3.10), as a class and plain functions so tests read them without a
// browser. The server checks everything again (parts/file_requests.py claim): a title, 1 to 20 files each described, an
// example only from this project's files, recipients who are in the conversation, and a due date up to 90 days ahead
// (left out: 5 working days, D-379). The form never holds a file, only the name of a project file picked as an example.
import { reactive } from 'vue'
import { MAX_DESCRIPTION, MAX_DUE_DAYS, MAX_ITEMS, MAX_TITLE } from './view.js'

let seq = 0
const drafts = new Map()

// The page's form for one conversation, made on first use and kept while the page lives (like the poll's draft), so leaving
// the room does not lose a long checklist.
export function requestFormOf(key) {
  if (!drafts.has(key)) drafts.set(key, reactive(new RequestForm()))
  return drafts.get(key)
}

export class RequestForm {
  constructor() {
    this.reset()
  }

  reset() {
    this.title = ''
    this.note = ''
    this.due = '' // "YYYY-MM-DD", as a date box gives it; empty is the server's default
    this.recipients = [] // user ids
    this.items = [blank()]
  }

  get canAdd() {
    return this.items.length < MAX_ITEMS
  }

  get canRemove() {
    return this.items.length > 1
  }

  add() {
    if (!this.canAdd) return null
    const item = blank()
    this.items.push(item)
    return item
  }

  remove(id) {
    if (this.canRemove) this.items = this.items.filter((i) => i.id !== id)
  }

  // The picker's file (a File row: name, file_name) is an item's example; null takes it off.
  setExample(id, file) {
    const item = this.items.find((i) => i.id === id)
    if (item) item.example = file ? { name: file.name, file_name: file.file_name } : null
  }

  toggle(user, on) {
    this.recipients = on ? [...new Set([...this.recipients, user])] : this.recipients.filter((u) => u !== user)
  }

  // A saved checklist replaces the files (descriptions and Required only, as a template holds) and names the request.
  useTemplate(template) {
    const list = itemsOf(template)
    if (!list.length) return
    this.title = String(template.title || '').slice(0, MAX_TITLE)
    this.items = list.slice(0, MAX_ITEMS).map((i) => ({ ...blank(), description: String(i.description || ''), required: i.required !== 0 && i.required !== false }))
  }

  // What a template keeps of this checklist.
  templateItems() {
    return this.items.map((i) => ({ description: i.description.trim(), required: i.required ? 1 : 0 }))
  }

  // The title and the files: enough to save a template.
  checklistProblems() {
    const out = []
    const title = this.title.trim()
    if (!title) out.push({ code: 'title' })
    if (title.length > MAX_TITLE) out.push({ code: 'title_long' })
    this.items.forEach((i, n) => {
      const text = i.description.trim()
      if (!text) out.push({ code: 'item', n: n + 1 })
      if (text.length > MAX_DESCRIPTION) out.push({ code: 'item_long', n: n + 1 })
    })
    return out
  }

  // What stops the request from being sent, as [{ code, n? }] in screen order; empty when it is ready. `today` is a Date.
  problems({ today = new Date() } = {}) {
    const out = this.checklistProblems()
    if (!this.recipients.length) out.push({ code: 'people' })
    if (this.due && !dueInRange(this.due, today)) out.push({ code: 'due' })
    return out
  }

  // The send: the message text (the note, else the title, as the server needs words) and the part.
  payload() {
    const request = {
      title: this.title.trim(),
      recipients: [...this.recipients],
      items: this.items.map((i) => ({
        description: i.description.trim(),
        required: i.required ? 1 : 0,
        ...(i.example ? { example_file: i.example.name } : {}),
      })),
    }
    if (this.due) request.due_on = this.due
    return { text: this.note.trim() || request.title, parts: { file_requests: request } }
  }
}

// A template row's checklist: its Long Text is JSON, [{ description, required }].
export function itemsOf(template) {
  try {
    const list = typeof template?.items === 'string' ? JSON.parse(template.items) : template?.items
    return Array.isArray(list) ? list.filter((i) => i && typeof i.description === 'string') : []
  } catch {
    return []
  }
}

// Today to 90 days on, as dates (a due date is never past; the server checks it in its own zone).
export function dueInRange(value, today = new Date()) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ''))
  if (!m) return false
  const due = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  const first = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const last = new Date(first)
  last.setDate(last.getDate() + MAX_DUE_DAYS)
  return due >= first && due <= last
}

// "YYYY-MM-DD" for a Date, in its own (the reader's) day: the date box's min and max.
export function dateValue(at) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`
}

// The people the conversation may ask: a Client conversation's client contacts, an Internal one's staff, never the sender.
export function askable(people, audience, me) {
  return (people || []).filter((p) => p.user !== me && (audience === 'Client' ? !p.team : Boolean(p.team)))
}

function blank() {
  return { id: ++seq, description: '', required: true, example: null }
}
