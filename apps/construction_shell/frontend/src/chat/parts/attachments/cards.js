// What the attachment cards draw (P3-65, design §15.6, canvas "Message cards"), as plain functions the tests read.
// A card is the server's: { attachment, file_name, url, size, kind, badge: { type, size, rev }, preview: { state, src,
// w, h }, reason?, taken_on, sent_on, width, height, rev_now? (staff) }. A card with no kind is a P3-07 card (a name and
// an address) and is drawn as the plain file chip it always was.
import { extTheme, fileExt } from '../../../sections/util.js'

// Photos with a ready preview are drawn as pictures; every other card as a file card; old cards as chips.
export function groupCards(items) {
  const list = (Array.isArray(items) ? items : [items]).filter((c) => c && c.url)
  return {
    photos: list.filter((c) => c.kind === 'photo' && c.preview?.state === 'ready'),
    files: list.filter((c) => c.kind && !(c.kind === 'photo' && c.preview?.state === 'ready')),
    legacy: list.filter((c) => !c.kind),
  }
}

// "14:02" on the day it was sent, "19 Oct 14:02" on another day; the site's wall time as written (P2-10).
export function clock(value, sameDayAs) {
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(String(value || ''))
  if (!m) return ''
  const day = String(sameDayAs || '').slice(0, 10)
  if (day && day === `${m[1]}-${m[2]}-${m[3]}`) return `${m[4]}:${m[5]}`
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[4]}:${m[5]}`
}
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// The words' values for "Taken 14:02 · sent 18:30" (one photo) or "Taken 14:02–14:09 · sent 18:30" (several): null
// when no photo has a capture time, so the caption says "Sent 18:30" only.
export function takenValues(photos) {
  const sent = photos.map((p) => p.sent_on).find(Boolean) || ''
  const times = photos.map((p) => p.taken_on).filter(Boolean).sort()
  const at = { sent: clock(sent, sent) }
  if (!times.length) return { ...at, taken: '' }
  const first = clock(times[0], sent)
  const last = clock(times[times.length - 1], sent)
  return { ...at, taken: first === last ? first : `${first}–${last}` }
}

export function typeOf(card) {
  return card.badge?.type || fileExt(card.file_name) || ''
}

// What a file card draws for its preview (design §15.6, canvas "Message cards", P3-75), from the server's card alone.
// `box`: 'image' (a ready preview), 'pending' (a quiet skeleton while the renderer works), 'info' (an IFC file: its
// schema and authoring app, from the header) or 'none' (a clean no-preview box with its reason). `lock`: a locked PDF.
// `action`: staff open PDF, Office and drawing files in the P3-48 viewer (`open`); clients, and every model file for
// everyone, download. A photo opens its own viewer, so it never reaches this.
export const REASONS = ['locked', 'too_large', 'blank', 'failed', 'not_supported', 'service_down']
const VIEWABLE = ['pdf', 'office', 'drawing']

export function cardView(card, { canOpen = false } = {}) {
  const preview = card.preview || {}
  const meta = card.meta && typeof card.meta === 'object' ? card.meta : {}
  const ready = preview.state === 'ready' && Boolean(preview.src)
  const info = !ready && card.kind === 'model' && Boolean(meta.schema || meta.app)
  const lock = meta.encrypted === true || card.reason === 'locked'
  let box = 'none'
  if (ready) box = 'image'
  else if (info) box = 'info'
  else if (preview.state === 'pending') box = 'pending'
  const reason = box === 'none' ? (REASONS.includes(card.reason) ? card.reason : 'not_supported') : ''
  return {
    box, reason, lock,
    schema: info ? meta.schema || '' : '',
    app: info ? meta.app || '' : '',
    image: ready ? { src: preview.src, w: preview.w || null, h: preview.h || null } : null,
    action: canOpen && VIEWABLE.includes(card.kind) ? 'open' : 'download',
  }
}

// A key that changes when a card's preview does, so a picture that failed to load is tried again once the server has
// made a new one (a realtime re-read gives the card a new address or state).
export const previewKey = (card) => `${card.attachment}:${card.preview?.state || ''}:${card.preview?.src || ''}`

// The type badge's colour on a card, as the canvas draws it (Documents, Drawings and models): PDF red, Word blue, Excel
// green, PowerPoint amber, drawings violet, IFC green, Revit blue, SketchUp amber; any other type as the Files list.
const CARD_THEME = { PDF: 'red', DOC: 'blue', DOCX: 'blue', XLS: 'green', XLSX: 'green', PPT: 'amber', PPTX: 'amber', DXF: 'violet', DWG: 'violet',
  IFC: 'green', RVT: 'blue', RFA: 'blue', SKP: 'amber' }
export const cardTheme = (fileName) => CARD_THEME[fileExt(fileName)] || extTheme(fileExt(fileName))
