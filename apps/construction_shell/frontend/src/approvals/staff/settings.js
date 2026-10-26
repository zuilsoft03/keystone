// The project's approval settings (P3-80; design §3.2, the ApprovalSettings frame): the Ready checklist from the server's
// reasons, the set-up body, and which buttons an approver's row offers. The writes are approvals.api's; this builds their bodies.

// Which preflight reasons belong to each checklist item (approvals.staff.READY).
export const ITEM_REASONS = {
  contract: ['portal_approvals', 'contract'],
  client_party: ['client_party'],
  evidence_mailbox: ['evidence_mailbox'],
  approver: ['approver'],
}

// The checklist's items with the reasons of the ones not done, and the badge's state. `others` are reasons no item owns
// (the site's switch, a closed project, the portal's section).
export function checklist(ready) {
  const reasons = ready?.reasons || []
  const items = (ready?.items || []).map((i) => ({ ...i, reasons: i.done ? [] : reasons.filter((r) => (ITEM_REASONS[i.key] || []).includes(r.key)) }))
  const owned = Object.values(ITEM_REASONS).flat()
  return { items, done: ready?.done ?? 0, of: ready?.of ?? items.length, ready: Boolean(ready?.ready), others: reasons.filter((r) => !owned.includes(r.key)) }
}

// The form's starting values from the server's `values` (all text).
export function formOf(values) {
  const v = values || {}
  return {
    portal_approvals: v.portal_approvals === '1', device_location: v.device_location === '1', contract_document: v.contract_document || '',
    contract_date: v.contract_date || '', contract_clause: v.contract_clause || '', contract_file: v.contract_file || '',
    client_legal_name: v.client_legal_name || '', client_address: v.client_address || '',
  }
}

// set_switches' body: all the text fields; the contract file only when it changed (a send freezes it again).
export function switchesBody(project, form, values) {
  const body = {
    project, portal_approvals: form.portal_approvals ? 1 : 0, device_location: form.device_location ? 1 : 0,
    contract_document: form.contract_document, contract_date: form.contract_date, contract_clause: form.contract_clause,
    client_legal_name: form.client_legal_name, client_address: form.client_address,
  }
  if (form.contract_file !== (values?.contract_file || '')) body.contract_file = form.contract_file
  return body
}

// What an approver's row offers a manager: Make approver or Not an approver, Confirm while waiting, and Send reset link
// while the account must reset its password (O2). The server's refusals (the second-staff rule) come back as sentences.
export function contactActions(c) {
  return { make: !c.approver, remove: c.approver, confirm: c.approver && !c.confirmed, reset: c.approver && c.must_reset }
}
