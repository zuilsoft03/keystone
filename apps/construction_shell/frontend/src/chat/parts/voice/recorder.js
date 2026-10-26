// The voice recorder (P3-67, design §3.6): one microphone take, from the browser's MediaRecorder, with no timeslice
// (FIT-15), a level for the meter and the waveform the send carries. Everything the browser gives (the clock, the timers,
// MediaRecorder, the microphone, the analyser, the page's visibility) comes in through `env`, `clock` and `timer`, so
// vitest drives it without a browser.
//
// The type order is the lead's decision for P3-67 (it changes §3.6's order): MP4 with AAC first, then Ogg Opus, then
// WebM Opus. None supported: the recorder refuses to start. It stops itself at MAX_SECONDS (299), so the server's 300.0
// second limit is never passed (Firefox overshoots by up to 0.05 s). A call, a locked screen, a hidden page or a lost
// microphone ends the take as "interrupted": the audio so far is kept (the store keeps it as a draft voice note).
export const VOICE_TYPES = ['audio/mp4;codecs=mp4a.40.2', 'audio/ogg;codecs=opus', 'audio/webm;codecs=opus']
export const MAX_SECONDS = 299
export const MIN_SECONDS = 0.5 // a shorter take is a slip of the thumb, not a note
export const WAVE_POINTS = 100 // the server takes 50 to 128 whole numbers from 0 to 100; about 100 (§3.6)
export const SAMPLE_MS = 50 // how often the level is read

export class VoiceError extends Error {
  constructor(code) {
    super(code)
    this.code = code // insecure | unsupported | denied | no_mic | failed
  }
}

export const realTimer = { set: (fn, ms) => setTimeout(fn, ms), clear: (id) => clearTimeout(id) }

// The first of VOICE_TYPES the browser can record, or ''.
export function pickType(isTypeSupported) {
  for (const type of VOICE_TYPES) {
    try {
      if (isTypeSupported?.(type)) return type
    } catch { /* a browser that throws for a type does not support it */ }
  }
  return ''
}

// 'ok', or why this page cannot record: 'insecure' (plain http: no microphone, D-321's precedent) or 'unsupported'.
export function canRecord(env = globalThis) {
  if (env.isSecureContext === false) return 'insecure'
  if (!env.navigator?.mediaDevices?.getUserMedia || typeof env.MediaRecorder !== 'function') return 'unsupported'
  return pickType((t) => env.MediaRecorder.isTypeSupported?.(t)) ? 'ok' : 'unsupported'
}

// The peak levels read while recording (0 to 1) as exactly `points` whole numbers from 0 to 100: the loudest of each
// share of the take (a short take is stretched). A square root keeps quiet speech visible. Anything not a number is 0.
export function reduceWaveform(levels, points = WAVE_POINTS) {
  const list = Array.isArray(levels) ? levels.map((v) => (Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0)) : []
  return Array.from({ length: points }, (_, i) => {
    if (!list.length) return 0
    const from = Math.floor((i * list.length) / points)
    const to = Math.max(from + 1, Math.floor(((i + 1) * list.length) / points))
    let peak = 0
    for (let k = from; k < Math.min(to, list.length); k++) peak = Math.max(peak, list[k])
    return Math.min(100, Math.max(0, Math.round(Math.sqrt(peak) * 100)))
  })
}

// 'm:ss' for a length in seconds.
export function lengthText(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export const extOf = (type) => (/mp4/.test(type) ? 'm4a' : /ogg/.test(type) ? 'ogg' : 'weba')

export class Recorder {
  constructor({ env = globalThis, clock = () => performance.now(), timer = realTimer, onLevel = () => {}, limit = MAX_SECONDS } = {}) {
    Object.assign(this, { env, clock, timer, onLevel, limit })
    this.rec = null
    this.stream = null
    this.ended = ''
    this.cancelled = false
    this.levels = []
    this.chunks = []
    this.t0 = null
    this.timers = []
    this.cleanups = []
    this.done = null // a promise of { blob, seconds, waveform, type, reason }, or null when the take was cancelled
  }

  // Asks for the microphone and starts. Resolves once the browser says it records; rejects with a VoiceError.
  async start() {
    const why = canRecord(this.env)
    if (why !== 'ok') throw new VoiceError(why)
    const type = pickType((t) => this.env.MediaRecorder.isTypeSupported?.(t))
    try {
      this.stream = await this.env.navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e) {
      throw new VoiceError(['NotAllowedError', 'SecurityError', 'PermissionDeniedError'].includes(e?.name) ? 'denied'
        : ['NotFoundError', 'OverconstrainedError', 'DevicesNotFoundError'].includes(e?.name) ? 'no_mic' : 'failed')
    }
    try {
      this.rec = new this.env.MediaRecorder(this.stream, { mimeType: type })
    } catch {
      this.release()
      throw new VoiceError('unsupported')
    }
    this.type = type
    this.done = new Promise((resolve) => (this.resolve = resolve))
    const { rec } = this
    rec.addEventListener('dataavailable', (e) => e.data?.size && this.chunks.push(e.data))
    rec.addEventListener('stop', () => this.settle())
    rec.addEventListener('error', () => this.end('interrupted'))
    for (const track of this.stream.getTracks?.() || []) {
      track.addEventListener?.('ended', () => this.end('interrupted'))
    }
    this.watchPage()
    this.meter()
    try {
      await new Promise((resolve, reject) => {
        rec.addEventListener('start', resolve, { once: true })
        rec.addEventListener('error', () => reject(new VoiceError('failed')), { once: true })
        rec.start() // no timeslice
      })
    } catch (e) {
      this.cancelled = true
      this.release()
      this.resolve(null)
      throw e
    }
    this.t0 = this.clock()
    this.timers.push(this.timer.set(() => this.end('limit'), this.limit * 1000))
    this.sample()
  }

  elapsed() {
    return this.t0 === null ? 0 : Math.max(0, (this.clock() - this.t0) / 1000)
  }

  // Ends the take (the reader's Stop, the limit or an interruption); `done` then resolves with the audio.
  end(reason = 'stop') {
    if (!this.rec || this.ended) return
    this.ended = reason
    this.seconds = this.elapsed()
    this.stopTimers()
    if (this.rec.state === 'inactive') this.settle()
    else {
      try { this.rec.stop() } catch { this.settle() }
    }
  }

  // Ends the take and throws the audio away.
  cancel() {
    this.cancelled = true
    this.end('cancel')
  }

  settle() {
    if (this.settled) return
    this.settled = true
    if (!this.ended) { // the browser stopped it (a call, a lost microphone): the take is kept as interrupted
      this.ended = 'interrupted'
      this.seconds = this.elapsed()
    }
    const blob = new Blob(this.chunks, { type: this.rec.mimeType || this.type })
    this.release()
    if (this.cancelled || !blob.size) return this.resolve(null)
    this.resolve({ blob, seconds: this.seconds, waveform: reduceWaveform(this.levels), type: blob.type || this.type, reason: this.ended })
  }

  // An interruption is a hidden page (a call, a locked screen, another app) or a page that is going away.
  watchPage() {
    const { env } = this
    const doc = env.document
    if (!doc || !env.addEventListener) return
    const hide = () => this.end('interrupted')
    const visibility = () => doc.visibilityState === 'hidden' && hide()
    doc.addEventListener?.('visibilitychange', visibility)
    env.addEventListener('pagehide', hide)
    this.cleanups.push(() => {
      doc.removeEventListener?.('visibilitychange', visibility)
      env.removeEventListener?.('pagehide', hide)
    })
  }

  // The level meter: an analyser on the same stream. A browser without one records with a flat meter.
  meter() {
    const Context = this.env.AudioContext || this.env.webkitAudioContext
    if (!Context) return
    try {
      const context = new Context()
      const analyser = context.createAnalyser()
      analyser.fftSize = 512
      context.createMediaStreamSource(this.stream).connect(analyser)
      context.resume?.()?.catch?.(() => {})
      this.analyser = analyser
      this.buffer = new Uint8Array(analyser.fftSize)
      this.cleanups.push(() => context.close?.()?.catch?.(() => {}))
    } catch { /* no meter */ }
  }

  level() {
    if (!this.analyser) return 0
    this.analyser.getByteTimeDomainData(this.buffer)
    let peak = 0
    for (const b of this.buffer) peak = Math.max(peak, Math.abs(b - 128) / 128)
    return peak
  }

  sample() {
    if (this.ended) return
    const level = this.level()
    this.levels.push(level)
    this.onLevel(level)
    this.sampler = this.timer.set(() => this.sample(), SAMPLE_MS)
  }

  stopTimers() {
    for (const t of this.timers.splice(0)) this.timer.clear(t)
    if (this.sampler !== undefined) this.timer.clear(this.sampler)
    this.sampler = undefined
  }

  release() {
    this.stopTimers()
    for (const undo of this.cleanups.splice(0)) undo()
    for (const track of this.stream?.getTracks?.() || []) track.stop?.()
  }
}
