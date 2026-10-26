// The poll form's rules (P3-68, design §3.7), as a class and plain functions so tests read them without a browser. The
// server checks everything again (parts/polls.py claim): 2 to 10 options, each with words or a picture, a question, a close
// time in the coming year, anonymous only in a Team (Internal) conversation, and a picture must be a photo sent with it.
export const MIN_OPTIONS = 2
export const MAX_OPTIONS = 10
export const MAX_QUESTION = 300
export const MAX_OPTION = 200
let seq = 0

export class PollForm {
  constructor(audience = 'Client') {
    this.audience = audience
    this.question = ''
    this.multiple = false
    this.anonymous = false
    this.closes = '' // "YYYY-MM-DDTHH:mm", as a date-time box gives it
    this.options = [blank(), blank()]
  }

  // A named poll only: a Client conversation always shows who voted (QH-D).
  get anonymousAllowed() {
    return this.audience === 'Internal'
  }

  get canAdd() {
    return this.options.length < MAX_OPTIONS
  }

  get canRemove() {
    return this.options.length > MIN_OPTIONS
  }

  add() {
    if (!this.canAdd) return null
    const option = blank()
    this.options.push(option)
    return option
  }

  remove(id) {
    if (this.canRemove) this.options = this.options.filter((o) => o.id !== id)
  }

  // A picture is a tray item's key; the form never holds the file.
  setPicture(id, key) {
    const o = this.options.find((x) => x.id === id)
    if (o) o.picture = key
  }

  // What stops the poll from being sent, as [{ code, n? }] in screen order; empty when it is ready. `busy` is a picture
  // still on its way or being checked; `now` is a Date.
  problems({ busy = false, now = new Date() } = {}) {
    const out = []
    const question = this.question.trim()
    if (!question) out.push({ code: 'question' })
    if (question.length > MAX_QUESTION) out.push({ code: 'question_long' })
    this.options.forEach((o, i) => {
      if (!o.text.trim() && o.picture === null) out.push({ code: 'option', n: i + 1 })
      if (o.text.trim().length > MAX_OPTION) out.push({ code: 'option_long', n: i + 1 })
    })
    const when = this.closes ? new Date(this.closes) : null
    if (when && (Number.isNaN(when.getTime()) || when <= now)) out.push({ code: 'closes' })
    if (busy) out.push({ code: 'busy' })
    return out
  }

  // The send's parts: the poll, and the pictures as the attachments part. `idOf(key)` is the staged attachment id of a
  // picture, or '' when it is not ready (the caller has checked problems first).
  parts(idOf) {
    const pictures = []
    const options = this.options.map((o) => {
      const id = o.picture === null ? '' : idOf(o.picture)
      if (id) pictures.push(id)
      return { text: o.text.trim(), ...(id ? { picture: id } : {}) }
    })
    const polls = { question: this.question.trim(), options, multiple: this.multiple, anonymous: this.anonymousAllowed && this.anonymous }
    if (this.closes) polls.closes_on = closesOn(this.closes)
    return { polls, ...(pictures.length ? { attachments: pictures } : {}) }
  }
}

// "2026-10-23T17:00" -> "2026-10-23 17:00:00": the site's wall time as the server reads it.
export function closesOn(local) {
  const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/.exec(local || '')
  return m ? `${m[1]} ${m[2]}:00` : ''
}

function blank() {
  return { id: ++seq, text: '', picture: null }
}
