// The answering flow on the approval sheet (P3-79; approvals design §3.5 items 2-8, §6 T24; D-461's screen contract; N4-N7,
// N12): the order of its steps, the signature's checks and picture, the location and the answer id. Functions of the
// sheet the server sent and of the flow's own state (newAnswer), so they are tested without a browser; the screens only
// draw them (AnswerFlow.vue, SignPad.vue).
import { ref } from 'vue'
import { ApiError, call } from '../api.js'

const API = 'construction_core.approvals.'
export const AGREE = `${API}agreement.agree`
export const PASSWORD = `${API}answer.password`
export const DECIDE = `${API}answer.decide`
export const RESET = 'frappe.core.doctype.user.user.reset_password' // Frappe's own reset email, as the sign-in page sends it

// The flow's state, one per open sheet (ApprovalSheet): a reload of the sheet never touches it, so typed text stays.
export const newAnswer = () => ({
  how: remembered(), typed: '', strokes: [], ratio: 0, reason: '', password: '', // ratio: the draw box's width over its height, once drawn
  agreed: null, // { text, version, at, fresh } once accepted here; fresh until Continue
  passwordOk: false, needPassword: false, locked: false,
  where: { ticked: false, state: '', value: null, result: null, skip: null },
  banner: '', notice: '', stop: '', result: null, pending: '', busy: false,
})

// "Type my name" or "Draw", remembered per device (design §3.5 item 4). Storage can be missing or refuse (private window).
const HOW = 'cc_approval_sign_how'
export function remembered(store) {
  try {
    return (store ?? globalThis.localStorage)?.getItem(HOW) === 'draw' ? 'draw' : 'type'
  } catch {
    return 'type'
  }
}
export function remember(how, store) {
  try {
    ;(store ?? globalThis.localStorage)?.setItem(HOW, how)
  } catch {
    // not kept: the next sheet starts on "Type my name"
  }
}

// What a client typed, drew or wrote on a sheet closed by the X, a tap outside, Escape or Back comes back when they open it
// again, as long as the page lives (B9). Only that: not the password, a refusal or a result, and nothing once the answer is
// over (it would otherwise bring back a finished flow).
const drafts = new Map()
export const answerFor = (request) => Object.assign(newAnswer(), drafts.get(request))
export function keepDraft(request, a) {
  const { typed, reason, strokes } = a
  if (a.result || a.stop || !(tidy(typed) || reason.trim() || strokes.some((s) => s.length))) drafts.delete(request)
  else drafts.set(request, { typed, reason, strokes: [...strokes] })
}

// The step to draw. The agreement comes first, then the password step, then signing or the reason (design §3.5 items 2-4).
// The flow's own answer wins over the sheet: its decide reloads the sheet as Approved, and the result stays on screen
// (while decide is in flight, the live event's reload can arrive first).
export function stageOf(sheet, a, step) {
  if (a.result) return 'done'
  if (a.stop || (sheet.can_answer && sheet.must_reset)) return 'stopped'
  if (!a.busy && (!sheet.can_answer || sheet.status !== 'Open')) return 'closed'
  if (a.agreed?.fresh) return 'accepted'
  const agreement = Boolean(sheet.agreement) && !a.agreed
  const password = (sheet.password_step || a.needPassword) && !a.passwordOk
  if ((agreement || password) && (sheet.password_locked || a.locked)) return 'locked'
  if (agreement) return 'agreement'
  if (password) return 'password'
  return step === 'return' ? 'return' : 'sign'
}

// A typed name: two words or more (as the server counts them), and whether it differs from the account's name, which is
// recorded, not refused (§3.5 item 4).
export const tidy = (text) => String(text || '').split(/\s+/).filter(Boolean).join(' ')
export function typedName(text, account = '') {
  const name = tidy(text)
  const ok = name.split(' ').length >= 2 && name.length <= 140
  return { name, ok, differs: ok && Boolean(tidy(account)) && name.toLowerCase() !== tidy(account).toLowerCase() }
}

// What "Sign and approve" says is missing, as a word key, or '' when nothing is.
export function signatureProblem({ how, typed, strokes, decision, option }) {
  if (decision && !option) return 'choose_option'
  if (how === 'draw') return strokes.some((s) => s.length) ? '' : 'answer.add_signature'
  if (!tidy(typed)) return 'answer.add_signature'
  return typedName(typed).ok ? '' : 'answer.two_words'
}

// The drawing: strokes of points as fractions of the box, so a rotation or a resize draws them again at the new size.
// The paper is white and the ink dark in both themes (N12): the picture is data, shown later on light and dark pages.
export const PAPER = 'white'
export const INK = 'rgb(28, 32, 38)'
export function paint(ctx, strokes, width, height, paper = true) {
  if (paper) {
    ctx.fillStyle = PAPER
    ctx.fillRect(0, 0, width, height)
  }
  Object.assign(ctx, { strokeStyle: INK, lineWidth: Math.max(2, width / 160), lineCap: 'round', lineJoin: 'round' })
  for (const s of strokes) {
    if (!s.length) continue
    ctx.beginPath()
    ctx.moveTo(s[0][0] * width, s[0][1] * height)
    for (const [x, y] of s.length > 1 ? s.slice(1) : [[s[0][0] + 0.002, s[0][1]]]) ctx.lineTo(x * width, y * height) // a tap is a dot
    ctx.stroke()
  }
}

// The signature as a PNG data URL on opaque white (a canvas starts transparent), or '' with nothing drawn. It has the draw
// box's own shape (B6: the strokes are fractions of the box, so a fixed shape would stretch them): 600 wide and at least
// 120 high. The server checks only the type, 512 KB, 50 megapixels and that it is not blank.
export function exportPng(strokes, make = () => document.createElement('canvas'), ratio = 2.5) {
  if (!strokes.some((s) => s.length)) return ''
  const canvas = make()
  canvas.width = 600
  canvas.height = Math.max(120, Math.round(600 / (ratio > 0 ? ratio : 2.5)))
  paint(canvas.getContext('2d'), strokes, canvas.width, canvas.height)
  return canvas.toDataURL('image/png')
}

// Location (§3.5 item 5, T24): asked only when the client ticks the box, and then the browser asks them. Our own
// 10-second limit, because the browser's own timeout does not run while its prompt is open; Skip ends the wait. Every
// outcome is a state to send; none blocks the answer. A shared position is rounded to 2 decimals (about 1 km) here, so
// the exact one never leaves the device.
const CODES = { 1: 'denied', 2: 'unavailable', 3: 'timed_out' }
const coarse = (n) => Math.round(n * 100) / 100
export function askLocation({ geolocation = globalThis.navigator?.geolocation, secure = globalThis.isSecureContext !== false, wait = 10000 } = {}) {
  let end
  const result = new Promise((resolve) => { end = resolve })
  if (!geolocation || !secure) {
    end({ state: 'not_supported' })
    return { result, skip() {} }
  }
  const timer = setTimeout(() => end({ state: 'timed_out' }), wait)
  const finish = (value) => {
    clearTimeout(timer)
    end(value)
  }
  try {
    geolocation.getCurrentPosition(
      ({ coords }) => finish({ state: 'shared', latitude: coarse(coords.latitude), longitude: coarse(coords.longitude), accuracy: Math.round(coords.accuracy) }),
      (e) => finish({ state: CODES[e?.code] || 'unavailable' }),
      { enableHighAccuracy: false, timeout: wait, maximumAge: 600000 },
    )
  } catch {
    finish({ state: 'unavailable' })
  }
  return { result, skip: () => finish({ state: 'timed_out' }) }
}

export function tickLocation(a, ticked, env) {
  a.where = { ticked, state: ticked ? 'waiting' : '', value: null, result: null, skip: null }
  if (!ticked) return
  const { result, skip } = askLocation(env)
  Object.assign(a.where, { result, skip })
  result.then((value) => a.where.result === result && Object.assign(a.where, { value, state: value.state }))
}

// What decide gets: nothing while the project's switch is off, null while unticked, else the outcome (waiting at most
// the rest of the 10 seconds).
export async function locationFor(sheet, a) {
  if (!sheet.location?.on) return undefined
  if (!a.where.ticked) return null
  return a.where.value || (a.where.result ? await a.where.result : null)
}

// One answer id per press (M5, T "Replay or double submit"): made on the press, sent again only when that press never
// reached the server (a lost connection, or a gateway error with no answer from Frappe), dropped once the server answered.
// getRandomValues, because randomUUID needs HTTPS and an office server may run plain HTTP.
export function answerId() {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('')
}
const unanswered = (e) => !(e instanceof ApiError) || (!e.type && e.status >= 500)

export async function send(a, args, post = call) {
  a.pending = a.pending || answerId()
  try {
    const out = await post(DECIDE, { ...args, answer_id: a.pending }, { post: true })
    a.pending = ''
    return out
  } catch (e) {
    if (!unanswered(e)) a.pending = ''
    throw e
  }
}

// One press of "Sign and approve" or "Return": the checks the screen makes first (a.banner says what is missing, and
// nothing is sent), then decide. A refusal is thrown for refuse().
export async function press(kind, { sheet, a, option = '', w, post = call, make }) {
  a.banner = ''
  if (kind === 'return') {
    if (!a.reason.trim()) return void (a.banner = w('answer.reason_missing'))
    return send(a, { request: sheet.request, answer: 'return', tokens: sheet.tokens, reason: a.reason.trim() }, post)
  }
  const problem = signatureProblem({ ...a, decision: Boolean(sheet.options?.length), option })
  if (problem) return void (a.banner = w(problem))
  const signature = a.how === 'draw' ? { kind: 'drawn', picture: exportPng(a.strokes, make, a.ratio) } : { kind: 'typed', name: tidy(a.typed) }
  return send(a, { request: sheet.request, answer: 'approve', tokens: sheet.tokens, option: option || undefined, signature, location: await locationFor(sheet, a) }, post)
}

// One try at a step's job (agree, password, decide, forgot): busy while it runs, a refusal shown by refuse(). True when the
// sheet on screen must be read again: a refusal that asks for it, or one that ends the flow (B7: someone else answered, the
// team voided or replaced it), so the terms and the who-line stop saying the request is open. Not for a missing request.
export async function attempt(a, job, w) {
  a.banner = ''
  a.busy = true
  let gone = false
  try {
    await job()
  } catch (e) {
    gone = e.type === 'DoesNotExistError'
    if (refuse(a, e, w)) return true
  } finally {
    a.busy = false
  }
  return Boolean(a.stop) && !gone
}

// decide's answer: the result, or "replaced" (returned, not thrown, so the server keeps the supersede) as a refusal.
export function settle(a, out, by) {
  if (out.state === 'replaced') a.stop = out.message
  else a.result = { state: out.state, to: out.receipt_to, at: new Date().toISOString(), by }
}

// A refusal (N7): the server's sentence, by its class. Some end the flow (a banner in place of the buttons), some go back
// a step; typed text always stays. Returns true when the sheet must be read again.
const FINAL = new Set(['AlreadyAnswered', 'Replaced', 'Voided', 'NotApprover', 'ApprovalsClosed', 'NotClient', 'NotBrowserSession', 'MustReset', 'DoesNotExistError'])
export function refuse(a, e, w) {
  if (unanswered(e)) {
    a.banner = w('answer.offline')
    return false
  }
  if (FINAL.has(e.type)) a.stop = e.message
  else a.banner = e.message
  if (e.type === 'PasswordNeeded') Object.assign(a, { passwordOk: false, needPassword: true })
  if (e.type === 'NeedsAgreement') a.agreed = null
  if (e.type === 'PasswordLocked') a.locked = true
  return ['NeedsAgreement', 'PageOutdated', 'PasswordNeeded'].includes(e.type)
}

// The agreement (§3.5 item 2): accepted with the password once. agree does not pass the password step, so when that is
// due too, the same password passes it here and the client is not asked twice.
export async function agree(a, sheet, post = call) {
  const password = a.password
  a.password = ''
  const out = await post(AGREE, { request: sheet.request, version: sheet.agreement.version, password }, { post: true })
  a.agreed = { text: sheet.agreement.text, version: out.version, at: new Date().toISOString(), fresh: true }
  if (sheet.password_step && !a.passwordOk) a.passwordOk = await post(PASSWORD, { password }, { post: true }).then(() => true, () => false)
}

export async function confirmPassword(a, post = call) {
  const password = a.password
  a.password = ''
  await post(PASSWORD, { password }, { post: true })
  Object.assign(a, { passwordOk: true, needPassword: false })
}

// The sheet of one request, read again on a live event (cc_approval_changed). A failed reload keeps the sheet on screen,
// and with it the flow and its typed text; the error shows above the terms.
export function useSheet(request, w, fetch = call) {
  const sheet = ref(null)
  const error = ref('')
  async function load() {
    try {
      sheet.value = await fetch(`${API}answer.sheet`, { request: request() })
      error.value = ''
    } catch (e) {
      error.value = e.type === 'DoesNotExistError' ? w('not_found') : e.message || w('answer.offline')
    }
  }
  return { sheet, error, load }
}

// What the step's polite live region says (B1): its title, then the refusal in view (the banner; the lockout or the stop
// sentence on those steps). The sentences are drawn once; their own alert roles are left off so they are not spoken twice.
export function announce(stage, title, a, sheet, w) {
  const refusal = stage === 'locked' ? w('answer.too_many') : stage === 'stopped' ? a.stop || sheet.must_reset : a.banner
  return [title, refusal].filter(Boolean).join('. ')
}

// A step replaces the one that held the pressed button, so focus is moved onto it (B1): its heading (tabindex -1), else the
// flow itself.
export function focusStep(root) {
  const target = root?.querySelector?.('[data-focus]') || root
  target?.focus?.({ preventScroll: true })
}
