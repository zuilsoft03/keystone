// Internal approval steps, the screens' rules (P3-82; design §14.6): the route editor's rows and checks, the filters the
// Approvals tab gains, what the Ask sheet warns about, and which buttons a step sheet offers. The server decides everything
// again (approvals.routes); this only mirrors it so a mistake is shown before the round trip.
import { DECISION, DOCUMENT, SUBMITTAL, VARIATION } from './ask.js'
import { FILTERS } from './request.js'

// The four record kinds that can have a route, in the card order.
export const KINDS = [VARIATION, SUBMITTAL, DOCUMENT, DECISION]
export const POSITIONS = ['Before the client', 'After the client']
export const WHO = ['Project role', 'Staff role', 'People']
export const RULES = ['Any one', 'All']
export const CONDITIONS = ['Always', 'Cost above', 'Days above']
export const PROJECT_ROLES = ['Project Manager', 'Architect', 'Engineer', 'Site', 'Consultant']
export const STAFF_ROLES = ['Construction Manager', 'Construction Staff']
// The words key of each choice's stored name (the stored names are data; the screen shows the glossary's words).
export const OPTION_WORD = {
  'Before the client': 'rt_pos_before', 'After the client': 'rt_pos_after', 'Project role': 'rt_who_project', 'Staff role': 'rt_who_staff',
  People: 'rt_who_people', 'Any one': 'rt_rule_any', All: 'rt_rule_all', Always: 'rt_cond_always', 'Cost above': 'rt_cond_cost', 'Days above': 'rt_cond_days',
}
export const LIMIT = 30 // steps per route (routes.LIMIT)

export const blankStep = () => ({
  step_name: '', position: POSITIONS[0], who: WHO[0], project_role: PROJECT_ROLES[0], staff_role: STAFF_ROLES[0], people: '',
  rule: RULES[0], condition: CONDITIONS[0], amount: 0, days: 0, due_days: 2,
})

// The server's rows as the form edits them (missing fields filled); `people` stays one email per line.
export const stepsOf = (rows) => (rows || []).map((r) => ({ ...blankStep(), ...Object.fromEntries(Object.entries(r).filter(([, v]) => v != null && v !== '')), people: String(r.people || '') }))

// Move step `i` up (-1) or down (+1); the client step is not a row, so there is nothing to protect here.
export function moveStep(steps, i, by) {
  const j = i + by
  if (j < 0 || j >= steps.length) return steps
  const out = [...steps]
  ;[out[i], out[j]] = [out[j], out[i]]
  return out
}

const emails = (text) => String(text || '').split(/[\n,]/).map((s) => s.trim()).filter(Boolean)

// The words keys of what is wrong with one step; none means it may be saved. (Whether a person is staff is the server's.)
export function stepErrors(s) {
  const errors = []
  if (!s.step_name.trim() || s.step_name.length > 140) errors.push('rt_err_name')
  if (s.who === 'People' && !emails(s.people).length) errors.push('rt_err_people')
  if (s.condition === 'Cost above' && !(Number(s.amount) > 0)) errors.push('rt_err_amount')
  if (s.condition === 'Days above' && !(Number(s.days) > 0)) errors.push('rt_err_days')
  if (!(s.due_days >= 1 && s.due_days <= 30)) errors.push('rt_err_due')
  return errors
}

// Every step's errors as [step number, words key] pairs, plus the route's own limit.
export function routeErrors(steps) {
  const out = steps.flatMap((s, i) => stepErrors(s).map((key) => [i + 1, key]))
  if (steps.length > LIMIT) out.push([0, 'rt_err_limit'])
  return out
}

// save_route's body: the steps as one JSON list, with only the fields the chosen "who" and "condition" use.
export const routeBody = (kind, steps) => ({
  kind,
  steps: JSON.stringify(steps.map((s) => ({
    step_name: s.step_name.trim(), position: s.position, who: s.who, rule: s.rule, condition: s.condition, due_days: Number(s.due_days),
    ...(s.who === 'Project role' ? { project_role: s.project_role } : s.who === 'Staff role' ? { staff_role: s.staff_role } : { people: emails(s.people).join('\n') }),
    ...(s.condition === 'Cost above' ? { amount: Number(s.amount) } : s.condition === 'Days above' ? { days: Number(s.days) } : {}),
  }))),
})

// preview's arguments: the saved steps alone, or tried on one record of that kind.
export const previewBody = (kind, sample = '') => ({ route: kind, ...(sample.trim() ? { sample: sample.trim() } : {}) })

// --- the tab's filters -------------------------------------------------------------------------------------------------
// FILTERS stays as P3-80 had it; the tab shows "Internal review" and "Waiting on me" after "Waiting".
export const TAB_FILTERS = ['waiting', 'internal_review', 'waiting_on_me', ...FILTERS.slice(1)]
export const rowsFor = (rows, show) => (rows || []).filter((r) => (show === 'waiting_on_me' ? r.waiting_on_me : r.group === show))

// --- the Ask sheet -----------------------------------------------------------------------------------------------------
// The route's steps that run for this record ("applies" is "0" for a step a condition skips; "" is a Decision's step
// decided by the client's option), and the steps only the sender can do (the warning before Send, §14.1).
export const runSteps = (route) => (route?.steps || []).filter((s) => s.applies !== '0')
export const samePersonSteps = (route) => runSteps(route).filter((s) => s.same_person)

// --- the step sheet ----------------------------------------------------------------------------------------------------
// An after-client step only acknowledges; a before-client step approves or is returned with a reason. No signature.
export function sheetButtons(sheet) {
  if (!sheet?.can) return []
  return sheet.action === 'acknowledge' ? ['acknowledge'] : ['approve', 'return']
}
export const REASON_MAX = 1000 // routes.REASON_MAX
// What the server's `state` answer says, as a words key.
export const STATE_WORD = { waiting: 'ss_done_waiting', sent: 'ss_done_sent', done: 'ss_done_done', returned: 'ss_done_returned', replaced: 'ss_done_replaced' }
export const sheetPath = (key) => ({ approve: 'routes.step_approve', acknowledge: 'routes.step_acknowledge', return: 'routes.step_return' })[key]
export const sheetBody = (request, sheet, reason = '') => ({ request, step: sheet.step, terms_hash: sheet.terms_hash, ...(reason ? { reason: reason.trim() } : {}) })

// --- the request page --------------------------------------------------------------------------------------------------
// One line per step: who does it and, once done, who did it and when; the "same person" flag per signer.
export const stepState = (s) => (s.done ? 'done' : s.current ? 'current' : 'later')
// A returned request offers "Edit and send again" (the server's next step) and "Close", which is api.void.
export const closeStep = (page) => (page?.next || []).find((s) => s.key === 'close_request') || null
export const internalStep = (page) => (page?.next || []).find((s) => s.key === 'internal_step') || null
export const CLOSE_REASON = 'Another reason'

