// What the approval screens say about a request, from the rows the portal payload and the sheet carry (P3-79). Pure
// functions of those rows and the words, so they are tested without a screen. Amounts and days arrive as text
// ("84000.00", "7"); a doctype name never appears in code: the server's `kind` indexes the glossary.
import { approvalWord } from './words.js'

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// "Wed 22 Oct" from a written site date (YYYY-MM-DD); '' without one.
export function dayText(iso) {
  const m = /^(\d{4})-(\d\d)-(\d\d)/.exec(iso || '')
  if (!m) return ''
  const day = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]))
  return `${DAYS[day.getUTCDay()]} ${+m[3]} ${MONTHS[+m[2] - 1]}`
}

// "18 Oct" and "18 Oct, 10:42" from a server time (UTC, "2026-10-18 10:42:00.123456Z": the column keeps microseconds, which
// Safari's date parser refuses beyond milliseconds), on the reader's own clock.
const instant = (iso) => new Date(String(iso || '').replace(' ', 'T').replace(/(\.\d{3})\d+/, '$1'))
export function dateText(iso) {
  const at = instant(iso)
  return Number.isNaN(at.getTime()) ? '' : `${at.getDate()} ${MONTHS[at.getMonth()]}`
}
export function whenText(iso) {
  const at = instant(iso)
  return Number.isNaN(at.getTime()) ? '' : `${dateText(iso)}, ${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`
}

export function names(list, joiner = 'and') {
  const all = (list || []).filter(Boolean)
  return all.length < 2 ? all.join('') : `${all.slice(0, -1).join(', ')} ${joiner} ${all[all.length - 1]}`
}

const MINUS = '−'
const grouped = (text) => {
  const [whole, cents] = String(text).replace('-', '').split('.')
  const digits = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return /^0*$/.test(cents || '') ? digits : `${digits}.${cents}`
}

// "+ PHP 84,000", "− PHP 2,000", or null when nothing changes.
export function costText(amount, currency) {
  const n = Number(amount)
  if (!n) return null
  return `${n < 0 ? MINUS : '+'} ${currency ? `${currency} ` : ''}${grouped(amount)}`
}

export function timeText(days, w) {
  const n = Number(days)
  if (!n) return null
  const sign = n < 0 ? `${MINUS} ` : '+ '
  return Math.abs(n) === 1 ? w('day_one', { sign }) : w('days', { sign, count: Math.abs(n) })
}

// The cost and time of a request as chips: [[label, text]]. A request with no price (a Submittal, a Document) has none;
// a Decision's lie on its options.
export function chips(terms, w) {
  if (!terms || terms.total === undefined) return []
  return [[w('cost'), costText(terms.total, terms.currency) || w('no_change')], [w('time'), timeText(terms.days, w) || w('no_change')]]
}

export const isDecision = (terms) => Array.isArray(terms?.options) && terms.options.length > 0

// A Decision's options for the screen: the text of each difference, "recommended" and the key of its picture.
export function optionRows(terms, w) {
  return (terms?.options || []).map((o) => ({
    key: o.key, label: o.label, description: o.description, picture: o.file || '', recommended: o.key === terms.recommended,
    cost: costText(o.cost_difference, terms.currency) || w('no_change'), time: timeText(o.time_difference, w) || w('no_change'),
  }))
}

export const kindWord = (kind, mode) => approvalWord(`kind.${kind}`, { mode })

// The link under a card: the exact version for a priced record, the revision for the others, the options for a
// Decision (which opens the sheet); a record without a file opens the sheet too. { label, href } or { label, sheet: true }.
export function openLink(row, w) {
  const file = row.files?.[0]
  const terms = row.terms || {}
  if (isDecision(terms) || !file) return { label: w(isDecision(terms) ? 'open_options' : 'open_details'), sheet: true }
  if (terms.total !== undefined) return { label: file.rev ? w('open_version_rev', { rev: file.rev }) : w('open_version'), href: file.url }
  return { label: w('open_revision', { rev: terms.revision || file.rev || '' }), href: file.url }
}

// What a request is named by on every screen (B4): a Document by its number and revision, not the record's name and the
// file's counter. The cards already get the number from the server (waiting.py); the sheet has the raw name, so it picks here.
export const refOf = (sheet) => sheet.terms?.number || sheet.reference
export const revOf = (sheet) => sheet.terms?.revision || sheet.files?.[0]?.rev || ''

// The rows the badge, the Home card and the tab's "Waiting for your approval" count: one list, the payload's (N11).
export const waitingRows = (data) => (data?.approvals || []).filter((r) => r.status === 'Open')
export const decidedRows = (data) => (data?.approvals || []).filter((r) => r.status !== 'Open')

// The first due date among the waiting rows (not the first row's).
export const soonest = (rows) => rows.map((r) => r.due_date).filter(Boolean).sort()[0] || ''

// Where a request's sheet opens: the Approvals tab with the request (and, for a Decision, the option picked; `step`
// "return" opens the Return step). The same address the request email carries (approvals.api._portal_link).
export const approvalLink = (request, option = '', step = '') => ({ query: { tab: 'approvals', request, ...(option ? { option } : {}), ...(step ? { step } : {}) } })

// The card's answer line for a decided row: { text, note } (the second line, when there is one).
export function decidedLines(row, w) {
  const when = whenText(row.at)
  if (row.state === 'disputed') return { text: w('disputed'), note: w('disputed_note') }
  if (row.state === 'recorded') return { text: w('recorded', { name: row.by, when }), note: '' }
  if (row.status === 'Returned') return { text: w(row.mine ? 'returned_you' : 'returned_other', { name: row.by, when }), note: row.reason ? `“${row.reason}”` : '' }
  return { text: w(row.mine ? 'approved_you' : 'approved_other', { name: row.by, when }), note: row.mine ? w('you_approved', { date: dateText(row.at) }) : '' }
}

// The sheet's head: { title, subtitle } for a sheet the server sent.
export function sheetHead(sheet, w, mode) {
  const kind = kindWord(sheet.kind, mode)
  const decision = isDecision(sheet.terms)
  return {
    title: decision ? sheet.title : `${refOf(sheet)}: ${sheet.title}`,
    subtitle: sheet.can_answer ? (decision ? w('head_choose_one', { kind }) : w('head_project', { kind, project: sheet.project_name })) : w('head_read_only', { kind }),
  }
}

export function sizeText(bytes) {
  const n = Number(bytes) || 0
  return n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`
}
