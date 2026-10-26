// The poll the message box is making (P3-68, design §3.7), kept for the page's life like the attach tray and the voice
// note (one per reader and conversation), so leaving the room does not lose it. The form's rules are in form.js. Each
// option's picture is a file staged by a tray of its own (the same upload, scan and "Share and send" copy as any
// attachment); the send names those staged files in the attachments part. A poll is sent on its own, with its own
// client id, never through the box's text.
import { reactive } from 'vue'
import { newClientId } from '../../unsent.js'
import { Tray } from '../attachments/tray.js'
import { PollForm } from './form.js'

const drafts = new Map()

// The page's draft for one conversation, made on first use. `audience` is the conversation's ('Internal' or 'Client').
export function pollOf(host, thread, audience) {
  const key = `${host.viewer}:${thread}`
  if (!drafts.has(key)) drafts.set(key, new PollDraft(host, thread, audience))
  const draft = drafts.get(key)
  draft.audience = audience
  return draft
}

export class PollDraft {
  constructor(host, thread, audience) {
    this.host = host
    this.thread = thread
    this.tray = new Tray(host)
    this.tray.thread = thread
    this.state = reactive({ open: false, sending: false, error: '', tried: false, form: new PollForm(audience) })
  }

  set audience(value) {
    this.state.form.audience = value
  }

  get form() {
    return this.state.form
  }

  get busy() {
    return this.tray.busy || this.tray.blocked
  }

  open() {
    this.state.open = true
  }

  close() {
    this.state.open = false
  }

  toggle() {
    this.state.open = !this.state.open
  }

  // Cancel: the form is emptied and every staged picture is let go.
  cancel() {
    for (const item of [...this.tray.items]) this.tray.remove(item.key)
    this.reset()
  }

  // A picture from this device for one option.
  pick(optionId, file) {
    this.tray.add([file], { shrink: false })
    this.setPicture(optionId, this.tray.items[this.tray.items.length - 1])
  }

  // A project file for one option (the picker's staged answer). Only a photo can be a picture.
  link(optionId, answer) {
    this.tray.link(answer)
    const item = this.tray.items[this.tray.items.length - 1]
    if (answer?.kind && answer.kind !== 'photo') {
      this.tray.remove(item.key)
      this.state.error = 'not_photo'
      return
    }
    this.setPicture(optionId, item)
  }

  setPicture(optionId, item) {
    const old = this.form.options.find((o) => o.id === optionId)?.picture
    if (old !== null && old !== undefined) this.tray.remove(old)
    this.form.setPicture(optionId, item ? item.key : null)
    this.state.error = ''
  }

  clearPicture(optionId) {
    this.setPicture(optionId, null)
  }

  // The tray item of an option's picture, for its thumbnail and state.
  itemOf(option) {
    return option.picture === null ? null : this.tray.items.find((i) => i.key === option.picture) || null
  }

  problems() {
    return this.form.problems({ busy: this.busy })
  }

  // Send the poll. Resolves to the message's name, or '' when it was not sent (the panel shows why).
  async send() {
    this.state.tried = true
    this.state.error = ''
    if (this.state.sending || this.problems().length) return ''
    this.state.sending = true
    try {
      const idOf = (key) => this.tray.items.find((i) => i.key === key && i.state === 'ready')?.attachment || ''
      const name = await this.host.send({ thread: this.thread, text: '', client_id: newClientId(), parts: this.form.parts(idOf) })
      this.tray.sent()
      this.reset()
      return name
    } catch (e) {
      this.state.error = e.message || 'failed'
      return ''
    } finally {
      this.state.sending = false
    }
  }

  reset() {
    this.state.form = new PollForm(this.state.form.audience)
    this.state.open = false
    this.state.tried = false
    this.state.error = ''
  }
}
