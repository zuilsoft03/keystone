// "Attach an approval…" (P3-79, approvals design §3.14; canvas ApprovalChat): the requests of this conversation's project that
// this reader may tag. The list is the server's # picker (refs.picker), which already limits it to what the reader and the
// room's readers may read; here it is only narrowed to approvals. Simple mode's # list leaves approvals out, so this
// asks in Advanced mode, which only widens the types and changes nothing about who may read what.
// shortcut: the picker returns the newest 6 matches of a type and searches the title only; search narrows, but the
// reference (VO-0007) is not searched until the server's picker looks at it.
export async function loadApprovals(host, thread, q = '') {
  const answer = await host.read('picker', { thread, q: q.trim(), mode: 'advanced' })
  return (Array.isArray(answer?.items) ? answer.items : []).filter((i) => i && i.type === 'approval' && i.doctype === 'Approval Request' && i.name)
}
