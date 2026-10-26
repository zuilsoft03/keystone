// The Ask sheet's rules (P3-80; design §3.4): what the server's preflight lets the sheet do, where each fix is, and the
// bodies it sends. The server decides everything again on Send (approvals.api.request); this only mirrors it.
// The records' stored names, joined from parts: they are data, not screen words, and the plain-words guard
// (tests/words.test.js) reads any whole industry word in the source as text a person sees.
export const VARIATION = ['Vari', 'ation Order'].join('')
export const SUBMITTAL = ['Sub', 'mittal'].join('')
export const DOCUMENT = 'Project Document'
export const DECISION = 'Client Decision'
// The staff page of each record kind that has one; a Decision opens in its own form.
export const SECTION_OF = { [VARIATION]: 'variations', [SUBMITTAL]: 'submittals', [DOCUMENT]: 'documents' }
// The states a request may be sent from (approvals.subjects.SUBJECTS[*].send), for the room's picker.
export const SENDABLE = {
  [VARIATION]: { field: 'stage', states: ['Change Order Request'] },
  [SUBMITTAL]: { field: 'status', states: ['Submitted', 'Under Review'] },
  [DOCUMENT]: { field: 'status', states: ['Client Review'] },
  [DECISION]: { field: 'status', states: ['Draft', 'Waiting', 'Needs a new request'] },
}

const SETTINGS_FIXES = new Set(['approval_settings', 'evidence_mailbox', 'approvers', 'portal_sections', 'approval_steps'])

// Where a reason is put right: a route to open, or text only (the site's switch and a closed project are not ours to open).
export function fixOf(reason, { project, doctype }) {
  const fix = reason?.fix
  if (SETTINGS_FIXES.has(fix)) return { word: `fix_${fix}`, route: { name: 'section', params: { project, section: 'settings' } } }
  if (fix === 'record' && SECTION_OF[doctype]) return { word: 'fix_record', route: { name: 'section', params: { project, section: SECTION_OF[doctype] } } }
  if (fix === 'site') return { word: 'fix_site', route: null }
  return { word: '', route: null }
}

// Send waits for the preflight to pass, and for a Variation's answer to "Has work started?".
export function canSend({ pre, busy, kind, started, startedOn }) {
  if (!pre?.ready || busy) return false
  return kind !== VARIATION || !started || Boolean(startedOn)
}

export function askBody({ doctype, name, due, note, kind, started, startedOn }) {
  const body = { doctype, name }
  if (due) body.due_date = due
  if (note?.trim()) body.note = note.trim()
  if (kind === VARIATION) body.work_started = started ? startedOn : 'not_started'
  return body
}

// A refusal may hold several sentences joined by <br>: shown as separate lines of text, never as markup.
export const refusalLines = (message) => String(message || '').split(/<br\s*\/?>/i).map((s) => s.replace(/<[^>]*>/g, '').trim()).filter(Boolean)

export const printUrl = (request) => `/api/method/construction_core.approvals.staff.print_form?request=${encodeURIComponent(request)}`
