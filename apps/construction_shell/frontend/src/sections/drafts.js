// Chat composer helpers (P3-61, H-F; unit-tested in tests/discuss.test.js). The staff Discuss and the client portal share
// them. The first half is pure over an injected storage; the second half is the few DOM reads the composer needs.

import { getCurrentScope, onScopeDispose, ref } from 'vue'

const PREFIX = 'cc-draft:'

// A draft is the text typed and the staff-only choice, kept per person and per thread for the tab's life (sessionStorage).
// It never moves between threads (F4: text written in an Internal thread must not reach a client), and it goes at sign-out.
export const keyOf = (user, thread) => `${PREFIX}${user}:${thread}`

export function draftStorage() {
  try {
    return window.sessionStorage
  } catch {
    return null // storage blocked: drafts then live only in the open page
  }
}

export function saveDraft(storage, user, thread, { text = '', staffOnly = false, marks = [] } = {}) {
  if (!storage || !user || !thread) return
  try {
    // Nothing typed and no staff-only choice made is no draft. `marks` (P3-66): the people and items picked into the text.
    if (!text && !staffOnly) storage.removeItem(keyOf(user, thread))
    else storage.setItem(keyOf(user, thread), JSON.stringify({ text, staffOnly: Boolean(staffOnly), ...(marks.length ? { marks } : {}) }))
  } catch { /* storage full or blocked */ }
}

export function loadDraft(storage, user, thread) {
  const none = { text: '', staffOnly: false }
  if (!storage || !user || !thread) return none
  try {
    const d = JSON.parse(storage.getItem(keyOf(user, thread)) || 'null')
    return d && typeof d.text === 'string' ? { text: d.text, staffOnly: d.staffOnly === true, ...(Array.isArray(d.marks) && d.marks.length ? { marks: d.marks } : {}) } : none
  } catch {
    return none
  }
}

export function clearDraft(storage, user, thread) {
  if (!storage || !user || !thread) return
  try { storage.removeItem(keyOf(user, thread)) } catch { /* storage blocked */ }
}

function draftKeys(storage) {
  const keys = []
  for (let i = 0; i < storage.length; i++) {
    const k = storage.key(i)
    if (k && k.startsWith(PREFIX)) keys.push(k)
  }
  return keys
}

// At start: another person's drafts (a shared computer, a session that ended without a sign-out) are removed.
export function clearOtherUsers(storage, user) {
  if (!storage) return
  try {
    for (const k of draftKeys(storage)) if (!user || !k.startsWith(`${PREFIX}${user}:`)) storage.removeItem(k)
  } catch { /* storage blocked */ }
}

// At sign-out: every draft.
export function clearAllDrafts(storage) {
  if (!storage) return
  try {
    for (const k of draftKeys(storage)) storage.removeItem(k)
  } catch { /* storage blocked */ }
}

// What a key press in the composer does, as team chats do it. 'send': Enter alone. 'newline': Shift+Enter, and Enter on a
// touch phone (its Send button sends); the browser makes the line, so a caller does nothing. null: any other key, and
// Enter while an input method is composing (isComposing; key code 229 is the same on Safari), so accented and Asian
// input works.
export function composerKey(event, { touch = false } = {}) {
  if (event.key !== 'Enter') return null
  if (event.isComposing || event.keyCode === 229) return null
  if (touch || event.shiftKey) return 'newline'
  if (event.ctrlKey || event.metaKey || event.altKey) return null
  return 'send'
}

// True when the reader is within `slack` px of the end of the list.
export function nearBottom({ scrollHeight, scrollTop, clientHeight }, slack = 120) {
  return scrollHeight - scrollTop - clientHeight <= slack
}

// --- the page (these read the browser, so tests/discuss.test.js does not call them) ---

const media = (query) => typeof window !== 'undefined' && Boolean(window.matchMedia) && window.matchMedia(query).matches
// A touch phone or tablet: the main pointer is a finger and no mouse or trackpad is attached, whatever the width (a large
// phone on its side is 900 px wide). A touch laptop has a fine pointer, so it still sends on Enter.
export const isTouchPhone = () => media('(pointer: coarse)') && !media('(any-pointer: fine)')

// The same as a flag for a template (the "Enter to send" hint), kept current while the component lives.
export function useTouchPhone() {
  const touch = ref(isTouchPhone())
  if (typeof window !== 'undefined' && window.matchMedia) {
    const update = () => (touch.value = isTouchPhone())
    const queries = ['(pointer: coarse)', '(any-pointer: fine)'].map((q) => window.matchMedia(q))
    queries.forEach((q) => q.addEventListener?.('change', update))
    if (getCurrentScope()) onScopeDispose(() => queries.forEach((q) => q.removeEventListener?.('change', update)))
  }
  return touch
}

// The composer grows with its text from one line to `lines` lines, then scrolls.
export function fitComposer(el, lines = 8) {
  if (!el) return
  const css = getComputedStyle(el)
  const line = parseFloat(css.lineHeight) || parseFloat(css.fontSize) * 1.5
  const max = line * lines + parseFloat(css.paddingTop) + parseFloat(css.paddingBottom)
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, max)}px`
  el.style.overflowY = el.scrollHeight > max ? 'auto' : 'hidden'
}

// Focus the composer, never taking focus from something the reader is using. After a send the focus must be on nothing,
// the composer, or the composer's own form (its Send button). When a thread has just opened (`opening`) the click that
// opened it left focus on its row in the thread list ([data-thread-list]), which may go; nothing else does. Not on a
// phone, where focus would raise the keyboard. `force` (P3-68, Edit) takes it: the reader just asked for this box.
export function focusComposer(el, { opening = false, force = false } = {}) {
  if (!el || isTouchPhone()) return
  const now = document.activeElement
  const free = !now || now === document.body || now === el || Boolean(el.form?.contains(now))
  if (free || force || (opening && now.closest?.('[data-thread-list]'))) el.focus({ preventScroll: true })
}

// The list scrolls itself when it overflows (staff Discuss); otherwise the page does (the portal's card grows).
function scrollerOf(list) {
  if (list && list.scrollHeight > list.clientHeight + 1 && /auto|scroll/.test(getComputedStyle(list).overflowY)) return list
  return document.scrollingElement || document.documentElement
}

export function readerNearBottom(list, slack = 120) {
  return nearBottom(scrollerOf(list), slack)
}

export function scrollToNewest(list) {
  const s = scrollerOf(list)
  s.scrollTop = s.scrollHeight
}
