// The voice draft (P3-67, design §3.6): the one voice note a conversation's message box is making, kept for the page's life
// like the attach tray (draftOf, one per reader and conversation), so leaving the room does not lose it.
//   idle -> starting -> recording -> review (the note: Play, Delete, and the box's Send)
// Press and hold records; sliding up locks it (hands-free), sliding left cancels. A tap also starts and stops it. A hold
// that is let go without a lock or a cancel is sent at once, the one case where nothing waits for a review (`sendNow`);
// after a tap or a lock the note waits for Play, Delete or Send. A call, a locked screen or a hidden page ends the take as
// "interrupted": what was recorded is kept as a draft in review. The note is staged on the server as soon as it is
// recorded (host.upload with voice: true; the server checks the recording and answers its waiting copy), and the send
// claims it with its waveform. A note the server holds for 24 hours is let go before that (KEEP_MS).
import { markRaw, reactive } from 'vue'
import { MIN_SECONDS, Recorder, canRecord, extOf, realTimer } from './recorder.js'

export const KEEP_MS = 23.5 * 3600 * 1000
export const BARS = 64 // the level meter's bars while recording (a few seconds of levels)
export const LOCK_PX = 60 // slide up this far to lock
export const CANCEL_PX = 80 // slide left this far to cancel
export const TAP_MS = 350 // a press shorter than this is a tap
const drafts = new Map()

// The page's draft for one conversation, made on first use.
export function voiceOf(host, thread, options) {
  const key = `${host.viewer}:${thread}`
  if (!drafts.has(key)) {
    const draft = new VoiceDraft(host, options)
    draft.thread = thread
    drafts.set(key, draft)
  }
  const draft = drafts.get(key)
  draft.prune()
  return draft
}

export class VoiceDraft {
  constructor(host, { make = (o) => new Recorder(o), env = globalThis, timer = realTimer, now = () => Date.now() } = {}) {
    Object.assign(this, { host, make, env, timer, now })
    this.thread = ''
    this.recorder = null
    this.pending = ''
    this.ticker = undefined
    this.state = reactive({
      phase: 'idle', // idle | starting | recording | review
      mode: '', // hold | free (hands-free: a tap or a lock)
      cancelling: false,
      seconds: 0,
      bars: Array(BARS).fill(0),
      error: '', // a VoiceError code, or the server's words for a note it refused
      notice: '', // interrupted | limit
      note: null,
      upload: 'idle', // idle | uploading | ready | failed
      progress: 0,
      sendNow: false,
      announce: null, // { key, values }: said once, politely
    })
  }

  get support() {
    return canRecord(this.env)
  }

  get recording() {
    return this.state.phase === 'starting' || this.state.phase === 'recording'
  }

  get hasNote() {
    return this.state.phase === 'review' && Boolean(this.state.note)
  }

  // Send waits while the take runs and while the note is on its way to the server.
  get busy() {
    return this.recording || (this.hasNote && this.state.upload !== 'ready')
  }

  get active() {
    return this.state.phase !== 'idle'
  }

  // What the send carries once the note is staged: { attachment, waveform }, or null.
  payload() {
    const { note, upload } = this.state
    return this.hasNote && upload === 'ready' && note.attachment ? { attachment: note.attachment, waveform: [...note.waveform] } : null
  }

  async begin(mode = 'free') {
    if (this.state.phase !== 'idle') return
    Object.assign(this.state, { phase: 'starting', mode, cancelling: false, seconds: 0, error: '', notice: '', sendNow: false, bars: Array(BARS).fill(0) })
    this.pending = ''
    const recorder = this.make({ env: this.env, timer: this.timer, onLevel: (v) => this.level(v) })
    this.recorder = recorder
    try {
      await recorder.start()
    } catch (e) {
      this.recorder = null
      Object.assign(this.state, { phase: 'idle', mode: '', error: e?.code || 'failed' })
      return
    }
    this.state.phase = 'recording'
    this.say('announce_started')
    this.tick()
    recorder.done.then((result) => this.finish(result))
    const next = this.pending
    this.pending = ''
    if (next) this[next]()
  }

  level(v) {
    const bars = this.state.bars
    bars.push(Math.min(1, v * 2.5))
    if (bars.length > BARS) bars.shift()
  }

  tick() {
    stopTick(this)
    this.ticker = this.timer.set(() => {
      if (!this.recorder || this.state.phase !== 'recording') return
      this.state.seconds = this.recorder.elapsed()
      this.tick()
    }, 200)
  }

  // The finger slid: up locks, left past the line cancels on release.
  gesture(dx, dy) {
    if (this.state.phase === 'idle' || this.state.mode !== 'hold') return
    if (dy <= -LOCK_PX) return this.lock()
    this.state.cancelling = dx <= -CANCEL_PX
  }

  // Hands-free: a lock, or a tap that began the take.
  lock() {
    if (this.state.phase === 'idle') return
    Object.assign(this.state, { mode: 'free', cancelling: false })
  }

  // The finger is lifted from a hold: cancelled when it ended left of the line, else sent at once.
  release() {
    if (this.defer('release')) return
    if (this.state.mode !== 'hold') return
    if (this.state.cancelling) return this.cancel()
    this.recorder?.end('stop')
  }

  // Stop: to review (a note that waits for Play, Delete or Send).
  stop() {
    if (this.defer('stop')) return
    this.lock()
    this.recorder?.end('stop')
  }

  cancel() {
    if (this.defer('cancel')) return
    this.recorder?.cancel()
    this.say('announce_deleted')
  }

  // A call, a locked screen, a pointer lost: the take ends and is kept as a draft.
  interrupt() {
    if (this.defer('interrupt')) return
    this.lock()
    this.recorder?.end('interrupted')
  }

  // While the microphone is being asked for, the reader's next move waits for it.
  defer(name) {
    if (this.state.phase !== 'starting') return false
    this.pending = name
    return true
  }

  finish(result) {
    stopTick(this)
    this.recorder = null
    if (!result) return Object.assign(this.state, { phase: 'idle', mode: '', cancelling: false })
    if (result.seconds < MIN_SECONDS) return Object.assign(this.state, { phase: 'idle', mode: '', cancelling: false, error: 'too_short' })
    const interrupted = result.reason === 'interrupted'
    if (interrupted || result.reason === 'limit') this.state.mode = 'free' // never sent unseen
    const note = {
      blob: markRaw(result.blob), url: safeUrl(result.blob), seconds: result.seconds, waveform: result.waveform, type: result.type,
      attachment: '', size: result.blob.size, abort: null, at: this.now(),
    }
    Object.assign(this.state, { phase: 'review', cancelling: false, seconds: result.seconds, note,
      notice: interrupted ? 'interrupted' : result.reason === 'limit' ? 'limit' : '' })
    this.say('announce_stopped', { length: Math.round(result.seconds) })
    this.upload()
  }

  async upload() {
    const note = this.state.note
    if (!note || !this.host.upload) return
    Object.assign(this.state, { upload: 'uploading', progress: 0, error: '' })
    const file = new File([note.blob], `voice-note.${extOf(note.type)}`, { type: note.type })
    try {
      const job = this.host.upload(this.thread, file, { voice: true, onProgress: (p) => (this.state.progress = p) })
      note.abort = job.abort
      const answer = (await job.done) || {}
      if (this.state.note !== note) {
        this.discardOnServer(answer.attachment) // deleted while it uploaded
        return
      }
      if (answer.reason || !answer.attachment) throw new Error('') // refused or not staged: "upload_failed"
      Object.assign(note, { attachment: answer.attachment, size: answer.size ?? note.size, abort: null })
      this.state.upload = 'ready'
      if (this.state.mode === 'hold') this.state.sendNow = true
    } catch (e) {
      if (e?.cancelled || this.state.note !== note) return
      Object.assign(this.state, { upload: 'failed', error: e?.message || 'upload_failed' })
      note.abort = null
    }
  }

  retryUpload() {
    if (this.hasNote && this.state.upload === 'failed') this.upload()
  }

  // Delete: the note goes, and the server's waiting copy with it.
  discard() {
    if (this.recording) return this.cancel()
    const note = this.state.note
    if (!note) return
    note.abort?.()
    this.discardOnServer(note.attachment)
    this.clear()
    this.say('announce_deleted')
  }

  // After a send: the note belongs to the message now; nothing is discarded.
  sent() {
    this.clear()
  }

  clear() {
    const note = this.state.note
    if (note?.url) URL.revokeObjectURL(note.url)
    Object.assign(this.state, { phase: 'idle', mode: '', cancelling: false, note: null, upload: 'idle', progress: 0, sendNow: false, notice: '', error: '', seconds: 0 })
  }

  discardOnServer(attachment) {
    if (attachment && this.host.act) this.host.act('attachments', 'discard', { attachment }).catch(() => {})
  }

  // A note whose waiting copy the server has deleted by now leaves the draft.
  prune(now = this.now()) {
    const note = this.state.note
    if (note && this.state.upload !== 'uploading' && now - note.at > KEEP_MS) this.clear()
  }

  say(key, values = {}) {
    this.state.announce = { key, values, n: (this.state.announce?.n || 0) + 1 }
  }
}

function stopTick(draft) {
  if (draft.ticker !== undefined) draft.timer.clear(draft.ticker)
  draft.ticker = undefined
}

function safeUrl(blob) {
  try {
    return URL.createObjectURL(blob)
  } catch {
    return ''
  }
}
