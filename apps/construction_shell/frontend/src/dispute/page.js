// The "This was not me" page's logic (P3-78 behaviour, drawn to the canvas in P3-79): the receipt's token stays in the link's
// fragment, which never reaches the server. `view` reads what the link's answer was and records nothing; the one button posts
// the token to dispute it, once. Pure of the screen, so a test drives it with a fake fetch.
import { reactive } from 'vue'

export const BROKEN = 'This link does not work. It may have been used already. If you need help, contact the team.'
const NEXT_READY = 'If you did not give this answer, press the button. The team is told at once and your account is signed out everywhere.'
const THANKS = 'Thank you. We told the team and signed your account out everywhere.'
const THANKS_NEXT = 'From now on the team does not rely on this approval until it is resolved. The team will contact you.'

export const tokenOf = (hash) => new URLSearchParams(String(hash || '').replace(/^#/, '')).get('t') || ''

// phase: 'checking' | 'ready' | 'broken' | 'done'. `summary` is the server's sentence about the answer.
export function createPage({ token, fetcher = fetch, csrf = '' }) {
  const page = reactive({ phase: 'checking', summary: '', next: '', busy: false })

  async function post(method) {
    const response = await fetcher(`/api/method/construction_core.approvals.dispute.${method}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrf },
      body: JSON.stringify({ token }),
      credentials: 'same-origin',
    }).catch(() => null)
    return response && response.ok ? (await response.json()).message : null
  }

  async function load() {
    const found = await post('view')
    if (!found?.summary) return Object.assign(page, { phase: 'broken', summary: BROKEN })
    Object.assign(page, { phase: 'ready', summary: found.summary, next: NEXT_READY })
  }

  // Once: the button goes whatever the answer, so a second press never posts the token again.
  async function confirm() {
    if (page.phase !== 'ready' || page.busy) return
    page.busy = true
    const done = await post('not_me')
    page.busy = false
    if (done) Object.assign(page, { phase: 'done', summary: THANKS, next: THANKS_NEXT })
    else Object.assign(page, { phase: 'broken', summary: BROKEN, next: '' })
  }

  return { page, load, confirm }
}
