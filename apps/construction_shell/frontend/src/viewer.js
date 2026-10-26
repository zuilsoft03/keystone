// The file viewer popup's logic (P3-48, D-315, D-316), kept apart from its markup so it is tested on its own: which
// viewer a file opens in, the context menu's place on screen, the drawing viewer's page (P3-49) and the control calls
// to Open CAD Studio.
import { extOf } from './files.js'
import { OFFICE } from './loader.js'

// Open CAD Studio at upstream commit 0e4c4c3 (D-319), built by dev/build-opencadstudio.sh and served from our own
// vendor folder.
export const CAD_APP = '/assets/construction_core/vendor/opencadstudio-0e4c4c3/index.html'
export const CAD_SOURCE = 'https://github.com/HakanSeven12/OpenCADStudio/tree/0e4c4c311df6de0d721bbf5fbf05c86dba19b368'
// The drawing viewer (P3-49, D-328, D-329): mlightcad's cad-simple-viewer 1.7.6 (MIT), DWG through LibreDWG
// (GPL-3.0; libredwg-web 0.8.0's wasm, the one libredwg-converter 3.15.11 ships) in its own worker, built by
// dev/build-cadviewer.sh. A drawing opens here; Edit opens it in Open CAD Studio. The page's notices and source are in
// its folder (NOTICE.txt).
const CAD_VIEW_DIR = '/assets/construction_core/vendor/cadviewer-1.7.6/'
export const CAD_VIEW = `${CAD_VIEW_DIR}index.html`
export const CAD_VIEW_NOTICE = `${CAD_VIEW_DIR}NOTICE.txt`
export const CAD_VIEW_SOURCE = 'https://github.com/mlightcad/cad-viewer/tree/v1.7.6'
export const DWG_SOURCE = 'https://github.com/mlightcad/libredwg-web/tree/v0.8.0'

// Why a DWG goes straight to Open CAD Studio, from its first six bytes, or '' for the drawing viewer: 'old' for a
// version older than AutoCAD 2000 (AC1014 is R14, AC1012 R13, AC1009 and older), on which LibreDWG 0.8.0 faults in our
// tests; 'unknown' for bytes that are no DWG version at all. A DXF is never sniffed.
export function dwgNotForViewer(name, bytes) {
  if (extOf(name) !== 'dwg' || !bytes || bytes.length < 6) return ''
  const m = /^AC(\d{4})$/.exec(String.fromCharCode(...bytes.subarray(0, 6)))
  if (!m) return 'unknown'
  return Number(m[1]) < 1015 ? 'old' : ''
}
export const NOT_FOR_VIEWER = {
  old: 'This drawing is in an AutoCAD format older than 2000, which the drawing viewer cannot read: Open CAD Studio shows it.',
  unknown: 'This file does not start like a DWG drawing the drawing viewer can read: Open CAD Studio tries it.',
}

// How long the drawing viewer may take before Open CAD Studio shows the drawing instead: a minute, and two seconds
// more for each megabyte (its own parse worker allows 30 s and a second per MiB).
export function viewDeadline(size) {
  return 60000 + Math.ceil(size / 1e6) * 2000
}
const IMAGE = new Set(['jpg', 'jpeg', 'png', 'webp', 'gif'])

// The viewer a file opens in, or '' when the popup has none and the file opens as it did before the popup.
export function viewerOf(name) {
  const ext = extOf(name)
  if (IMAGE.has(ext)) return 'image'
  if (ext === 'dwg' || ext === 'dxf') return 'cad'
  // a PDF too: the Document Server's PDF editor (zoom, scroll, thumbnails, comments); the popup falls back to pdf.js
  // when the Document Server is not there (D-327)
  if (OFFICE.test(String(name || ''))) return 'office'
  return ''
}

// Where a menu of the given size opens for a pointer at (x, y): at the pointer, moved back inside the window.
export function menuPlace(x, y, size, viewport, gap = 8) {
  return {
    left: Math.max(gap, Math.min(x, viewport.width - size.width - gap)),
    top: Math.max(gap, Math.min(y, viewport.height - size.height - gap)),
  }
}

export function toBase64(bytes) {
  let out = ''
  for (let i = 0; i < bytes.length; i += 0x8000) out += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  return btoa(out)
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
// A few painted frames, or half a second when the frame does not paint (a hidden tab).
const nextFrames = (win, n = 3) => new Promise((resolve) => {
  setTimeout(resolve, 500)
  const step = (left) => (left && win.requestAnimationFrame ? win.requestAnimationFrame(() => step(left - 1)) : setTimeout(resolve, 100))
  step(n)
})

// The control channel of the Open CAD Studio page in `win` (docs/automation/web.md, API-SPEC.md and
// web_save_smoke.cjs at 0e4c4c3). Every wait checks the deadline and `cancelled()` (the popup was closed) on each pass,
// so no reply, a reply that stays "running" or one that stays "busy" ends in an error, never in a loop.
export class CadCancelled extends Error {
  constructor() {
    super('The CAD viewer was closed.')
    this.name = 'CadCancelled'
  }
}

function guard({ deadline, cancelled }, timeout) {
  if (cancelled?.()) throw new CadCancelled()
  if (Date.now() >= deadline) throw new Error(timeout)
}

// `cadRaw` submits one request and polls for its reply.
export async function cadRaw(win, body, opts) {
  const pollMs = opts.pollMs ?? 50
  let api = win.wasmBindings
  while (!api?.ocs_control_submit) {
    guard(opts, 'The CAD viewer did not start.')
    await sleep(pollMs)
    api = win.wasmBindings
  }
  guard(opts, 'The CAD viewer did not answer.')
  const ticket = api.ocs_control_submit(JSON.stringify(body))
  for (;;) {
    const raw = api.ocs_control_take(ticket)
    if (raw) return JSON.parse(raw)
    guard(opts, 'The CAD viewer did not answer.')
    await sleep(pollMs)
  }
}

// A change, as the upstream smoke test sends one: against the current document and revision, under its own
// request_id; an "accepted" or "running" reply is followed with op "operation" until it settles, and a "busy" one is
// sent again under a new id. Failures are {ok: false, code, error} or status "failed".
let sequence = 0
const newId = () => `cc-${Date.now().toString(36)}-${(sequence += 1)}`

export async function cadAct(win, body, opts) {
  const pollMs = opts.pollMs ?? 50
  for (;;) {
    const state = await cadRaw(win, { op: 'state' }, opts)
    const id = newId()
    let reply = await cadRaw(win, { ...body, request_id: id, document_id: state.document_id, revision: state.revision }, opts)
    while (['accepted', 'running'].includes(reply.status)) {
      guard(opts, 'The CAD viewer did not finish.')
      await sleep(pollMs)
      reply = await cadRaw(win, { op: 'operation', request_id: id }, opts)
    }
    if (reply.code !== 'busy') return reply
    guard(opts, 'The CAD viewer stayed busy.')
    await sleep(pollMs)
  }
}

// The drawing viewer's calls in the frame `win` (dev/cadviewer/src/main.js), once its page has set them up.
export async function cadView(win, { timeoutMs = 30000, pollMs = 50, cancelled } = {}) {
  const opts = { deadline: Date.now() + timeoutMs, cancelled }
  while (!win?.ccCadView?.open) {
    guard(opts, 'The drawing viewer did not start.')
    await sleep(pollMs)
  }
  return win.ccCadView
}

// Opens a drawing from its bytes as a viewer (P3-48): the start dialog closed, the drawing opened, the ribbon and
// side panels hidden (CLEANSCREEN), and the whole drawing in view. With `clean: false` (Edit since P3-49) the whole of
// Open CAD Studio stays.
export async function cadOpen(win, name, dataBase64, { timeoutMs = 120000, pollMs = 50, cancelled, clean = true } = {}) {
  const opts = { deadline: Date.now() + timeoutMs, pollMs, cancelled }
  const state = await cadRaw(win, { op: 'state' }, opts)
  if (state.modal) await cadAct(win, { op: 'action', name: 'close_modal' }, opts)
  const reply = await cadAct(win, { op: 'open', name, data_base64: dataBase64 }, opts)
  if (reply.ok === false || reply.status === 'failed') return reply
  // Autosave off for this drawing too (cadstore.js primes it before load; refused before a drawing is open)
  const off = await cadAct(win, { op: 'run', cmd: 'SAVETIME 0' }, opts)
  if (off.ok === false || off.status === 'failed') console.warn('Open CAD Studio kept autosave on:', off.error || off.code)
  // CLEANSCREEN is a toggle: a dialog still open could swallow it, so one is closed first, and its answer is checked.
  if ((await cadRaw(win, { op: 'state' }, opts)).modal) await cadAct(win, { op: 'action', name: 'close_modal' }, opts)
  if (clean) {
    const screen = await cadAct(win, { op: 'run', cmd: 'CLEANSCREEN' }, opts)
    if (screen.ok === false || screen.status === 'failed') console.warn('Open CAD Studio kept its ribbon:', screen.error || screen.code)
  }
  // Zoom to the whole drawing once the canvas has its clean-screen size and the drawing has been drawn once.
  await nextFrames(win)
  await cadAct(win, { op: 'action', name: 'zoom_extents' }, opts)
  // A dialog that came up while it loaded (a GPU warning on a machine without one) cannot be answered in a viewer.
  if ((await cadRaw(win, { op: 'state' }, opts)).modal) await cadAct(win, { op: 'action', name: 'close_modal' }, opts)
  return reply
}

// Edit where Open CAD Studio already shows the drawing as a viewer: CLEANSCREEN again brings back the whole program
// (P3-48).
export async function cadFull(win, { timeoutMs = 30000, pollMs = 50, cancelled } = {}) {
  const opts = { deadline: Date.now() + timeoutMs, pollMs, cancelled }
  if ((await cadRaw(win, { op: 'state' }, opts)).modal) await cadAct(win, { op: 'action', name: 'close_modal' }, opts)
  return cadAct(win, { op: 'run', cmd: 'CLEANSCREEN' }, opts)
}
