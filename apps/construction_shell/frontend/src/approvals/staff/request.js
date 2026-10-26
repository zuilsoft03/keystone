// The staff request screens' rules (P3-80; design §3.9, §3.12, §3.11): the tab's filters, the request page's next steps,
// the recorded forms' required fields and the gated move's reason. The screens draw what the server's reads give
// (approvals.staff); the server decides again on every write.

// The tab's filters, in the frame's order; each is a row's `group` and a key of the server's `counts`.
export const FILTERS = ['waiting', 'overdue', 'approved', 'returned', 'disputed', 'recorded', 'replaced_or_voided']
export const filterRows = (rows, show) => (rows || []).filter((r) => r.group === show)
export const countOf = (counts, show) => counts?.[show] || 0
// The room list's number beside Approvals: the requests still waiting on the client, late or not.
export const openCount = (counts) => countOf(counts, 'waiting') + countOf(counts, 'overdue')

// "3 days", "1 day", "today" from the row's age in days.
export const ageText = (days, w) => (days > 1 ? w('age_days', { count: days }) : days === 1 ? w('age_day') : w('age_today'))

// Where the Approvals tab, a request page and its evidence record live: the Discussion section, in the query.
const here = (project, query) => ({ name: 'section', params: { project, section: 'discuss' }, query })
export const tabRoute = (project) => here(project, { approvals: 1 })
export const requestRoute = (project, request) => here(project, { approval: request })
export const evidenceRoute = (project, request) => here(project, { approval: request, evidence: 1 })

// The server also returns "Close request" and "Record a note"; they have no write yet (after-MVP), so they are not drawn.
const UNDRAWN = ['close_request', 'record_note']
export const stepsOf = (next) => (next || []).filter((s) => !UNDRAWN.includes(s.key))

// The states a request is recorded against / disputed in. A dispute is recorded for an answer that stands.
export const canRecord = (page) => page.state === 'waiting' && page.status === 'Open'
export const canDispute = (page) => page.manager && ['approved', 'recorded'].includes(page.state) && !page.dispute
export const canVoid = (page) => page.status === 'Open'

// The reasons api.void accepts, exactly as the server spells them, and the words key of each.
export const VOID_REASONS = {
  'Sent by mistake': 'void_mistake',
  'The record is being changed': 'void_changing',
  'No longer needed': 'void_unneeded',
  'Another reason': 'void_other',
}

// A record page's gated move (staff.gate): the reason this move waits, or '' when it may go ahead.
export const gatedReason = (gate, to) => (gate?.required && gate.reason && gate.to?.includes(to) ? gate.reason : '')

// --- the recorded approval (board 16) ---------------------------------------------------------------------------------
export const METHODS = ['paper', 'written', 'phone']
export const blankRecorded = () => ({ method: 'paper', member: '', given_at: '', proof: '', original: '', option: '' })

// The words keys of what is missing; none means it may be recorded.
export function recordedErrors(f, decision) {
  const errors = []
  if (!METHODS.includes(f.method)) errors.push('rec_err_method')
  if (!f.member) errors.push('rec_err_member')
  if (!f.given_at) errors.push('rec_err_when')
  if (!f.proof) errors.push('rec_err_proof')
  if (f.method === 'paper' && !f.original.trim()) errors.push('rec_err_original')
  if (decision && !f.option) errors.push('rec_err_option')
  return errors
}

// A datetime-local value as the site's own time, without a zone ("2026-10-12 09:00:00"): the server compares it as written.
const siteTime = (v) => v.replace('T', ' ') + (v.length === 16 ? ':00' : '')
export function recordedBody(request, f, decision) {
  return { request, method: f.method, member: f.member, given_at: siteTime(f.given_at), proof_file: f.proof,
    ...(f.method === 'paper' ? { original: f.original.trim() } : {}), ...(decision ? { option: f.option } : {}) }
}

// --- the recorded dispute (board 17) and its end ----------------------------------------------------------------------
export const HOWS = ['phone', 'email']
export const OUTCOMES = ['withdrawn', 'upheld', 'closed']
export const blankDispute = () => ({ how: 'phone', reason: '', proof: '' })

export function disputeErrors(f) {
  const errors = []
  if (!HOWS.includes(f.how)) errors.push('dis_err_how')
  if (!f.reason.trim()) errors.push('dis_err_reason')
  if (!f.proof) errors.push('dis_err_proof')
  return errors
}
export const disputeBody = (request, f) => ({ request, how: f.how, reason: f.reason.trim(), proof_file: f.proof })

export function resolveErrors(f) {
  const errors = []
  if (!OUTCOMES.includes(f.outcome)) errors.push('res_err_outcome')
  if (!f.reason.trim()) errors.push('res_err_reason')
  return errors
}
export const resolveBody = (request, f) => ({ request, outcome: f.outcome, reason: f.reason.trim() })

// --- the timeline (staff.page's `timeline` rows) in plain words --------------------------------------------------------
// Each row is { kind, at, by, ... }; `w` is the staff words function. A kind the screen does not know shows its own name.
export function lineText(e, w) {
  const name = e.by
  switch (e.kind) {
    case 'requested': return w('tl_requested', { name })
    case 'agreed': return w('tl_agreed', { name })
    case 'opened': return w('tl_opened', { name })
    case 'approved': return e.method ? e.label : e.signed ? w('tl_approved_signed', { name, kind: w(`sign_${e.signed}`) }) : w('tl_approved', { name })
    case 'returned': return w('tl_returned', { name })
    case 'receipt_sent': return w('tl_receipt_sent', { name: e.to })
    case 'receipt_failed': return w('tl_receipt_failed', { name: e.to })
    case 'disputed': return w('tl_disputed', { name })
    case 'dispute_resolved': return w('tl_resolved', { outcome: w(`res_${e.outcome}`) })
    case 'recorded': return w('tl_recorded', { signer: e.signer, label: e.label })
    case 'voided': return w('tl_voided', { reason: e.reason })
    case 'superseded': return w('tl_superseded')
    // P3-82: the firm's own steps; "same person" marks a step its signer was the only one able to do
    case 'internal_review': return w('tl_internal_review')
    case 'route_frozen': return w('tl_route_frozen')
    case 'internal_approved': case 'internal_returned': case 'internal_acknowledged':
      return w(`tl_${e.kind}`, { name, step: e.step }) + (e.same_person ? ` · ${w('same_person')}` : '')
    default: return w('tl_other', { kind: e.kind })
  }
}

// A fingerprint as the evidence record prints it, "3f9a1c22 · 88d4 c21e" (its first 16 characters; the server keeps the whole).
export const shortHash = (hash) => (hash ? `${hash.slice(0, 8)} · ${hash.slice(8, 12)} ${hash.slice(12, 16)}` : '')
