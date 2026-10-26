// The voice player's model (P3-67, design §3.6): play and pause, a position, a seek and the speeds 1×, 1.5× and 2×, over
// one audio element made on the first play. P3-67's measurement found that play() after a failed seek can stay pending
// for ever, so every play and every seek is given a time (PLAY_MS, SEEK_MS); one that does not settle ends in the "error"
// state, which the card says in words and offers Try again for. Never a spinner without an end.
// The audio element and the timers come in as arguments, so vitest drives it without a browser. The length is the
// server's (the container's own), never the element's: a recording from MediaRecorder reports an infinite duration.
import { reactive } from 'vue'
import { realTimer } from './recorder.js'

export const SPEEDS = [1, 1.5, 2]
export const PLAY_MS = 8000
export const SEEK_MS = 5000
export const SKIP_SECONDS = 5 // an arrow key on the waveform

let active = null // only one note plays at a time

const makeAudio = () => new Audio()

export class VoicePlayer {
  constructor({ src, length = 0, make = makeAudio, timer = realTimer, playMs = PLAY_MS, seekMs = SEEK_MS } = {}) {
    Object.assign(this, { src, length: Number(length) || 0, make, timer, playMs, seekMs })
    this.audio = null
    this.startAt = 0
    this.state = reactive({ status: 'idle', position: 0, speed: 1, error: '' }) // idle | loading | playing | paused | error
  }

  get busy() {
    return this.state.status === 'loading' || this.state.status === 'playing'
  }

  // Settles with `promise`, or rejects with a timeout after `ms`.
  within(promise, ms) {
    return new Promise((resolve, reject) => {
      const id = this.timer.set(() => reject(Object.assign(new Error('timeout'), { timeout: true })), ms)
      Promise.resolve(promise).then(
        (v) => { this.timer.clear(id); resolve(v) },
        (e) => { this.timer.clear(id); reject(e) },
      )
    })
  }

  element() {
    if (this.audio) return this.audio
    const a = this.make()
    this.audio = a
    a.preload = 'auto'
    a.src = this.src
    a.addEventListener('timeupdate', () => { if (this.audio === a) this.state.position = clamp(a.currentTime, this.length) })
    a.addEventListener('ended', () => {
      if (this.audio !== a) return
      Object.assign(this.state, { status: 'idle', position: 0 })
      this.startAt = 0
      a.currentTime = 0
      if (active === this) active = null
    })
    a.addEventListener('pause', () => { if (this.audio === a && this.state.status === 'playing' && !a.ended) this.state.status = 'paused' })
    a.addEventListener('error', () => { if (this.audio === a) this.fail('error') })
    return a
  }

  async play() {
    if (this.busy) return
    if (active && active !== this) active.pause()
    active = this
    const a = this.element()
    Object.assign(this.state, { status: 'loading', error: '' })
    a.playbackRate = this.state.speed
    if (this.startAt) a.currentTime = this.startAt
    try {
      await this.within(a.play(), this.playMs)
      if (this.audio !== a || this.state.status !== 'loading') return // paused or ended meanwhile
      this.state.status = 'playing'
    } catch (e) {
      if (this.audio !== a) return
      if (e?.name === 'AbortError' && this.state.status !== 'loading') return // pause() while it loaded
      this.fail(e?.timeout ? 'timeout' : 'error')
    }
  }

  pause() {
    if (!this.audio || this.state.status === 'idle' || this.state.status === 'error') return
    this.audio.pause()
    this.state.status = 'paused'
    this.startAt = this.state.position
  }

  toggle() {
    return this.busy ? this.pause() : this.play()
  }

  // To a second of the note. Before the first play it only sets where the play starts; while the audio is loaded the
  // browser must confirm the seek, or the player is in the error state.
  async seek(seconds) {
    const at = clamp(seconds, this.length)
    this.state.position = at
    this.startAt = at
    const a = this.audio
    if (!a || this.state.status === 'error') return
    try {
      const seeked = new Promise((resolve) => a.addEventListener('seeked', resolve, { once: true }))
      a.currentTime = at
      await this.within(seeked, this.seekMs)
    } catch (e) {
      if (this.audio === a) this.fail(e?.timeout ? 'timeout' : 'error')
    }
  }

  setSpeed(speed) {
    if (!SPEEDS.includes(speed)) return
    this.state.speed = speed
    if (this.audio) this.audio.playbackRate = speed
  }

  fail(reason) {
    this.drop()
    Object.assign(this.state, { status: 'error', error: reason })
    if (active === this) active = null
  }

  // Try again after an error: a new element, from the start.
  retry() {
    this.drop()
    this.startAt = 0
    Object.assign(this.state, { status: 'idle', position: 0, error: '' })
    return this.play()
  }

  // The element is let go, with its network request.
  drop() {
    const a = this.audio
    this.audio = null
    if (!a) return
    try {
      a.pause()
      a.removeAttribute('src')
      a.load()
    } catch { /* an element already gone */ }
  }

  dispose() {
    this.drop()
    if (active === this) active = null
  }
}

function clamp(seconds, length) {
  const n = Number.isFinite(seconds) ? Math.max(0, seconds) : 0
  return length > 0 ? Math.min(n, length) : n
}
