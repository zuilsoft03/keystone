// The sign-in page's logic (P3-24, D-251, D-252), kept apart from its screens so it is tested on its own. Every call
// is one of Frappe's own; this only decides what to show and where to go.

export const LOGIN = '/api/method/login'
export const RESET = '/api/method/frappe.core.doctype.user.user.reset_password'
export const UPDATE = '/api/method/frappe.core.doctype.user.user.update_password'
export const STRENGTH = '/api/method/frappe.core.doctype.user.user.test_password_strength'

// After sign-in: the redirect-to of the address when it resolves to this site, else Frappe's home for the person.
// Resolved as the browser would (it drops tabs and newlines, so "/<tab>/evil" is "//evil"), then the origin compared,
// as Frappe's sanitise_redirect does (P3-24 audit S1). A full URL on this site is kept: Frappe's OAuth authorize and
// Connected App send one.
const HERE = typeof location !== 'undefined' ? location.origin : 'https://site.invalid'

export function safeRedirect(target, origin = HERE) {
  // eslint-disable-next-line no-control-regex
  if (typeof target !== 'string' || !target || /[\u0000-\u001f\u007f\\]/.test(target)) return null
  let url
  try {
    url = new URL(target, origin)
  } catch {
    return null
  }
  // A path that normalises to "//host" ("/.//evil", "/a/..//evil") would leave the site as a protocol-relative URL.
  if (url.origin !== new URL(origin).origin || url.pathname.startsWith('//')) return null
  if (/^\/(login|update-password|portal\/login)(\/|$)/.test(url.pathname)) return null // never back to a sign-in page
  return url.pathname + url.search + url.hash
}

export function nextPlace(data, search) {
  const asked = safeRedirect(new URLSearchParams(search || '').get('redirect-to'))
  return asked || safeRedirect(data && data.home_page) || '/'
}

export async function post(url, body, csrf = '') {
  let res
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...(csrf ? { 'X-Frappe-CSRF-Token': csrf } : {}) },
      body: JSON.stringify(body),
      credentials: 'same-origin',
    })
  } catch {
    return { status: 0, data: {} }
  }
  return { status: res.status, data: await res.json().catch(() => ({})) }
}

// Frappe's own message, when it sent one, as plain text (its messages may carry markup).
export function serverMessage(data) {
  let text = data && typeof data.message === 'string' ? data.message : ''
  try {
    const first = JSON.parse(JSON.parse(data._server_messages)[0])
    text = first.message || text
  } catch {
    // no queued message
  }
  return String(text || '').replace(/<[^>]*>/g, '').trim()
}

// What a sign-in answer means for the page.
export function signInResult({ status, data }) {
  if (status === 0) return { kind: 'offline' }
  if (data && data.verification && data.tmp_id) return { kind: 'code', tmpId: data.tmp_id }
  if (status === 200 && data && ['Logged In', 'No App'].includes(data.message)) return { kind: 'done', data }
  if (status === 429) return { kind: 'error', text: 'Too many tries. Please wait a minute, then try again.' }
  const text = serverMessage(data)
  if (status === 401 && (!text || /invalid login|incorrect|not allowed/i.test(text))) return { kind: 'wrong' }
  return { kind: 'error', text: text || 'Sign-in did not work. Please try again.' }
}

export const STRENGTH_WORDS = ['Too easy', 'Weak', 'Fair', 'Good', 'Strong']

export function strengthOf(result) {
  // With the site's password policy off, Frappe answers an empty object: nothing to pass, so the server decides.
  const policyOff = !!result && typeof result === 'object' && Object.keys(result).length === 0
  const score = Math.max(0, Math.min(4, Number(result && result.score) || 0))
  const passed = policyOff || !!(result && result.feedback && result.feedback.password_policy_validation_passed)
  return { score, word: STRENGTH_WORDS[score], passed, hint: (result && result.feedback && result.feedback.warning) || '' }
}

export function initials(text) {
  return String(text || '').split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('')
}

// A sign-in picture's public copy (P3-34, D-273): the only picture address a visitor is given.
export function pictureUrl(id) {
  return `/api/method/construction_core.signin_pictures.image?picture=${encodeURIComponent(String(id || ''))}`
}
