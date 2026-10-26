// P3-19 (D-196, D-198, D-209): what Settings → Client contacts shows of a project's invitations, kept apart from the
// screen so it is tested on its own. The server sends no secret: a link exists only in the answer that made it.

const METHOD = 'construction_core.onboarding.invites.'
export const call = (name) => `${METHOD}${name}`

// Chat apps' share addresses, each with the message encoded as one parameter (never pasted into the address raw).
export function shareLinks(link, company) {
  const text = `${company || 'Our team'} invites you to follow your project online: ${link}`
  const t = encodeURIComponent(text)
  return {
    text,
    whatsapp: `https://wa.me/?text=${t}`,
    viber: `viber://forward?text=${t}`,
    messenger: `fb-messenger://share/?link=${encodeURIComponent(link)}`,
  }
}

// An invitation the team still follows: active, or run out and waiting for a new link. Used and cancelled ones are
// history: the person is a contact now, or nobody.
export function invitedOf(invites) {
  return (invites || []).filter((i) => i.status === 'Active' || i.status === 'Expired')
}

// People who proved their address on an open link and wait for a manager, newest first, with their invitation.
export function waitingOf(invites) {
  const out = []
  for (const i of invites || []) {
    for (const r of i.requests || []) if (r.status === 'Waiting') out.push({ ...r, invite: i.name })
  }
  return out.sort((a, b) => String(b.verified_on || '').localeCompare(String(a.verified_on || '')))
}

export function badgeOf(invite) {
  if (invite.status === 'Expired') return { label: 'Link expired', theme: 'gray' }
  if (!invite.email) return { label: 'Open link', theme: 'blue' }
  if (invite.mail_state === 'Failed') return { label: 'Email failed', theme: 'red' }
  return { label: 'Invited', theme: 'amber' }
}

export function whoOf(invite) {
  if (invite.email) return { title: invite.full_name || invite.email, line: invite.email }
  return { title: invite.full_name || 'Open link', line: 'Anyone with the link can ask to join; you approve each person' }
}

export function untilOf(invite, now = new Date()) {
  const until = new Date(String(invite.expires_on || '').replace(' ', 'T'))
  if (Number.isNaN(until.getTime())) return ''
  const day = until.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
  return until < now ? `Ran out ${day}` : `Works until ${day}`
}

export function mailLine(invite) {
  return { Queued: 'Email on its way', Sent: 'Email sent', Failed: 'The email could not be sent' }[invite.mail_state] || ''
}
