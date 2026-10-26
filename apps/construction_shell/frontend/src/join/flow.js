// The join page's logic (P3-17, P3-18; D-214, D-219, D-220), kept apart from its screens so it is tested on its own.
// The link is /join#k=<token>: the token is read from the fragment (never sent to a server, a log or a Referer), kept
// in this tab's sessionStorage so a reload or a trip to the mail app resumes, and removed from the address bar. The
// person's request and the proof a right code answers are kept the same way, and forgotten with the token.

export const KEY = 'cc_join_k'
export const REQUEST_KEY = 'cc_join_r'
export const PROOF_KEY = 'cc_join_p'
const TOKEN = /^[A-Za-z0-9_-]{43}$/
const REQUEST = /^[A-Za-z0-9]{1,64}$/
const METHOD = 'construction_core.onboarding.join.'
export const MIN_PASSWORD = 8 // D-219: simple for clients; the server refuses only the commonest and their own name
export const MIN_TEAM_PASSWORD = 10 // a team account keeps the site's policy (D-235)

export function readToken(loc, storage, history) {
  const match = /(?:^|[#&])k=([A-Za-z0-9_-]{43})(?:&|$)/.exec(loc.hash || '')
  let token = match ? match[1] : null
  try {
    if (token && storage.getItem(KEY) !== token) {
      storage.removeItem(REQUEST_KEY) // another link: nothing of the last one carries over
      storage.removeItem(PROOF_KEY)
    }
    if (token) storage.setItem(KEY, token)
    else token = storage.getItem(KEY)
  } catch {
    // a browser that keeps no storage: the token lives only in this page
  }
  if (match && history && typeof history.replaceState === 'function') history.replaceState(null, '', '/join')
  return token && TOKEN.test(token) ? token : null
}

export function remember(storage, key, value) {
  try {
    if (value) storage.setItem(key, value)
    else storage.removeItem(key)
  } catch {
    // kept in this page only
  }
}

export function recall(storage, key) {
  try {
    const value = storage.getItem(key)
    if (key === PROOF_KEY) return value && TOKEN.test(value) ? value : null
    return value && REQUEST.test(value) ? value : null
  } catch {
    return null
  }
}

export function forget(storage) {
  for (const key of [KEY, REQUEST_KEY, PROOF_KEY]) {
    try {
      storage.removeItem(key)
    } catch {
      // nothing kept
    }
  }
}

// Chat apps' own browsers (Messenger, Instagram, Line, Viber...) may lose this tab when the person leaves to read mail.
export function inAppBrowser(ua) {
  return /FBAN|FBAV|FB_IAB|Instagram|Line\/|Viber|MicroMessenger|; wv\)/i.test(ua || '')
}

export async function post(name, args) {
  let res
  try {
    res = await fetch(`/api/method/${METHOD}${name}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(args),
      credentials: 'same-origin',
    })
  } catch {
    return { state: 'offline' }
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok || !data.message) return { state: res.status === 429 ? 'try_later' : 'invalid' }
  return data.message
}

// Where a person resumes: the server's stage. 'finish' is an approved person's own link: only the password is left.
export function stepOf(stage) {
  return { code: 'code', details: 'details', waiting: 'waiting', finish: 'password' }[stage] || 'welcome'
}

// The numbered steps a person goes through, by the kind of link (the welcome and the last screen are not counted).
export function stepsFor(kind, existing, team = false) {
  if (team) return kind === 'mailed' ? ['details', 'password'] : ['code', 'details', 'password'] // D-235
  if (kind === 'open') return ['email', 'code', 'details', 'privacy']
  if (kind === 'approved') return existing ? [] : ['password']
  const own = existing ? ['details', 'privacy'] : ['details', 'password', 'privacy']
  return kind === 'mailed' ? own : ['code', ...own]
}

export function stepLabel(kind, existing, step, team = false) {
  const steps = stepsFor(kind, existing, team)
  const at = steps.indexOf(step)
  return at < 0 || steps.length < 2 ? '' : `Step ${at + 1} of ${steps.length}`
}

// The 6 code boxes: only digits, at most one each; a paste or a phone's autofill fills them from the box it lands in.
export function digitsOf(text) {
  return String(text ?? '').replace(/\D/g, '').slice(0, 6)
}

export function fillBoxes(boxes, at, text) {
  const out = [...boxes]
  const digits = digitsOf(text)
  if (!digits) {
    out[at] = ''
    return { boxes: out, focus: at }
  }
  let i = digits.length >= 6 ? 0 : at // a whole code always fills from the first box
  for (const d of digits) {
    if (i > 5) break
    out[i++] = d
  }
  return { boxes: out, focus: Math.min(i, 5) }
}

export const SAYS = {
  invalid: 'This link no longer works. Ask the person who sent it for a new one.',
  signed_in: 'You are signed in to another account. Sign out first, then open the link again.',
  try_later: 'Too many tries for now. Please try again later.',
  offline: 'We could not reach the server. Check your internet connection and try again.',
  too_many_codes: 'Too many codes were sent for this link. Ask the person who sent it for a new one.',
  full: 'This link has already been used by as many people as it allows. Ask the person who sent it for a new one.',
  email_invalid: 'Please check your email address. Example: maria.santos@example.com',
  code_expired: 'That code has expired. Tap "Send a new code".',
  locked: 'Too many wrong codes. Tap "Send a new code".',
  verify_again: 'Your check has timed out. Please ask for a new code.',
  consent_needed: 'Please read the privacy note and tick "I agree".',
  name_needed: 'Please enter your full name.',
  mobile_needed: 'Please enter your mobile number, so the team can call you.',
  mobile_invalid: 'Please enter a mobile number with digits only. Example: 0917 123 4567',
  not_needed: '',
}

export function say(result) {
  if (!result) return SAYS.invalid
  if (result.state === 'wrong') return `That code is not right. ${result.left} ${result.left === 1 ? 'try' : 'tries'} left.`
  if (result.state === 'wait') return `Please wait ${result.seconds} seconds before asking for another code.`
  if (result.state === 'weak') return [result.warning, ...(result.suggestions || [])].filter(Boolean).join(' ')
  return SAYS[result.state] ?? SAYS.invalid
}

export function consentText(company, privacyEmail) {
  const who = company || 'The project team'
  const write = privacyEmail ? `write to ${privacyEmail}` : 'tell the project team'
  return `${who} keeps your name, email, mobile number and company name to give you access to your project and to contact you about it. The project team and our administrators see these details. Other client contacts on the same project see your name and email. We keep your mobile number and company name while you have access and for 2 years after you leave your last project, then delete them. Your name and email stay in the project's records. To see, correct or delete your details, ${write}.`
}
