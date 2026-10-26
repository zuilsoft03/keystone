// Pure helpers of the sections (P2-04); unit-tested in tests/sections.test.js.

// Frappe stores Text Editor fields as sanitised HTML; the shell shows them as plain text (Vue escapes it).
export function plainText(html) {
  return String(html || '')
    .replace(/<\s*(br|\/p|\/div|\/li)\s*\/?>/gi, '\n')
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function formatSize(bytes) {
  const n = Number(bytes) || 0
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// Frappe's timestamps carry no offset: they are the site's wall time. They are shown as written, with no conversion to
// the browser's time zone, so a client elsewhere reads the same clock as the team (P2-10).
function parts(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(String(value || ''))
  return m ? { y: +m[1], mo: +m[2], d: +m[3], h: m[4], mi: m[5] } : null
}

// A message's time as the design shows it: "09:58" today, "12 Oct" before that.
export function clockTime(value, now = new Date()) {
  const p = parts(value)
  if (!p) return ''
  const today = p.y === now.getFullYear() && p.mo === now.getMonth() + 1 && p.d === now.getDate()
  return today && p.h ? `${p.h}:${p.mi}` : `${p.d} ${MONTHS[p.mo - 1]}`
}

// A message's date and time as the portal design writes them: "10 Oct 09:58" ("10 Oct 2025 09:58" in another year).
// No "today" guess, so a client in another time zone is never told the wrong day.
export function stampTime(value, now = new Date()) {
  const p = parts(value)
  if (!p) return ''
  const day = p.y === now.getFullYear() ? `${p.d} ${MONTHS[p.mo - 1]}` : `${p.d} ${MONTHS[p.mo - 1]} ${p.y}`
  return p.h ? `${day} ${p.h}:${p.mi}` : day
}

// A date as the design writes it, the same in every browser: "11 Oct" this year, "11 Oct 2025" before.
export function formatDate(value, now = new Date()) {
  const p = parts(value)
  if (!p) return value ? String(value) : ''
  const day = `${p.d} ${MONTHS[p.mo - 1]}`
  return p.y === now.getFullYear() ? day : `${day} ${p.y}`
}

// The chip between two days of a conversation (P3-61): "Today", "Yesterday", else the date. Days are the written site
// dates compared with the reader's calendar day, as clockTime does.
export function dayLabel(value, now = new Date()) {
  const p = parts(value)
  if (!p) return ''
  const ago = Math.round((Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) - Date.UTC(p.y, p.mo - 1, p.d)) / 86400000)
  if (ago === 0) return 'Today'
  if (ago === 1) return 'Yesterday'
  return formatDate(value, now)
}

// A conversation's messages as rows, each with the day chip when it is the first of its day ({ m, sep }; sep is '' else).
// `label` names a day: dayLabel in the team's chat, formatDate in the portal, which never guesses "today" for a client
// in another time zone (P2-10).
export function withDaySeparators(messages, now = new Date(), label = dayLabel) {
  let last = ''
  return (messages || []).map((m) => {
    const day = label(m.creation, now)
    const sep = day && day !== last ? day : ''
    if (day) last = day
    return { m, sep }
  })
}

// A file type's badge theme, as the live design's Files screen colours them (D-124, version 1791648865-5845).
export function extTheme(ext) {
  if (/^(DXF|DWG|IFC|RVT|RFA|SKP)$/.test(ext)) return 'violet' // P3-75: the model files with the drawings
  if (/^(PDF)$/.test(ext)) return 'red'
  if (/^(DOCX?|ODT|PPTX?|TXT)$/.test(ext)) return 'blue'
  if (/^(XLSX?|ODS|CSV)$/.test(ext)) return 'green'
  if (/^(JPE?G|PNG|GIF|WEBP|HEIC)$/.test(ext)) return 'amber'
  return 'gray'
}

export function fileExt(name) {
  const m = /\.([A-Za-z0-9]{1,5})$/.exec(name || '')
  return m ? m[1].toUpperCase() : ''
}

// The fields a form may change: not read-only, not the state (changed by the transition buttons), not the project.
export function editableFields(meta) {
  return meta.fields.filter((f) => !f.read_only && f.fieldname !== meta.state_field)
}

// Only the changed values are sent with the saved document, so a field the user did not touch is never overwritten.
export function changes(original, current, fields) {
  const out = {}
  for (const f of fields) {
    const a = original[f.fieldname] ?? ''
    const b = current[f.fieldname] ?? ''
    if (String(a) !== String(b)) out[f.fieldname] = current[f.fieldname]
  }
  return out
}

// P3-77: a save that replaces the record's approval request is refused (ReplaceRequest) until the person agrees; `ask`
// shows the server's words and answers yes or no, and on yes the same save goes again with the confirmation.
export async function saveConfirming(send, values, ask) {
  try {
    return await send(values)
  } catch (e) {
    if (e?.type !== 'ReplaceRequest' || !ask(e.message)) throw e
    return send({ ...values, __replace_request: 1 })
  }
}

export function countByState(rows, field) {
  const out = {}
  for (const r of rows) out[r[field]] = (out[r[field]] || 0) + 1
  return out
}

// Badge colours for record states (frappe-ui 1.x palette).
// A record state's badge theme, as the live design colours them (D-124, version 1791648865-5845, PM): closed is violet,
// waiting on someone is amber, sent back is red.
export function stateTheme(state) {
  if (/^(Closed)$/.test(state)) return 'violet'
  if (/^(Approved|Approved as Noted|Approved Change|Published|Answered|Resolved)$/.test(state)) return 'green'
  if (/^(Revise and Resubmit|Rejected|Cancelled|Locked)$/.test(state)) return 'red'
  if (/^(Under Review|Change Order Request|Lead Review)$/.test(state)) return 'amber'
  if (/^(Client Review)$/.test(state)) return 'violet'
  if (/^(Draft|WIP|Potential Change|Archived)$/.test(state)) return 'gray'
  return 'blue'
}

// At most one run per key at a time (a page marking a thread read twice after a send makes two writes to one row, which
// can lose a race on the server: F15). A call made while one is pending is not run at once and returns false; it is
// remembered, and when the pending run settles one more run follows (the latest function), so the last call is never
// dropped: a message that arrived during the first run is still marked read.
export function singleFlight() {
  const state = new Map() // key -> the latest function asked for while a run is pending, or null
  function start(key, run) {
    state.set(key, null)
    Promise.resolve()
      .then(run)
      .catch(() => {})
      .finally(() => {
        const next = state.get(key)
        if (next) start(key, next)
        else state.delete(key)
      })
  }
  return (key, run) => {
    if (state.has(key)) {
      state.set(key, run)
      return false
    }
    start(key, run)
    return true
  }
}
