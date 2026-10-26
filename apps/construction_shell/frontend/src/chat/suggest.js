// The message box's two lists (P3-66, design §3.4, §3.5): "@" offers the people of this conversation and "#" the files and
// records the reader may tag. This is the state and the calls behind them; Suggest.vue draws it and Composer.vue owns the
// keys. The server answers each list for the thread and this reader only (parts.mentions.people, parts.refs.picker), so
// nothing here decides who or what is offered. Reads are debounced and the latest one wins.
import { getCurrentScope, onScopeDispose, reactive } from 'vue'
import { groupItems } from './parts/refs/cards.js'
import { addMark, mentionMark, refMark, spans, triggerAt } from './tokens.js'

export const COMPOSE_KEY = Symbol('cc-chat-compose') // what the box lends its tool buttons: { begin(char), has(char) }
export const WAIT_MS = 150

// The people of a conversation as options: the project team first, then the client's contacts.
export function personOptions(people) {
  const list = (Array.isArray(people) ? people : []).filter((p) => p && p.user)
  const rank = (p) => (p.team ? 0 : 1)
  return list.map((p, i) => ({ p, i })).sort((a, b) => rank(a.p) - rank(b.p) || a.i - b.i).map(({ p }) => ({
    key: `u:${p.user}`, kind: 'mention', user: p.user, name: p.name || p.user, image: p.image || '', team: Boolean(p.team),
    group: p.team ? 'team' : 'client',
  }))
}

// The picker's cards as options, files and boards first, then the project's records (Advanced mode).
export function itemOptions(items) {
  const list = (Array.isArray(items) ? items : []).filter((c) => c && c.doctype)
  return groupItems(list).flatMap((g) => g.items.map((c) => ({
    ...c, key: `r:${c.doctype}:${c.doctype === 'File' ? c.url : c.name}`, kind: 'ref', group: g.key,
  })))
}

// Replaces the trigger and what was typed after it with the picked label and one space, and says where the caret goes.
export function insertPick(text, trigger, caret, label) {
  const after = String(text).slice(caret)
  const gap = /^\s/.test(after) ? '' : ' '
  const head = `${String(text).slice(0, trigger.start)}${label}${gap}`
  return { text: `${head}${after}`, caret: head.length + (gap ? 0 : 1) }
}

// `ctx`: () => { host, thread (the conversation's name), mode ('simple' | 'advanced'), chars ('@#' that the box offers) }.
export function useSuggest(ctx, { wait = WAIT_MS } = {}) {
  const state = reactive({ open: false, char: '', start: 0, query: '', items: [], active: 0, loading: false, error: false })
  let timer = null
  let seq = 0
  let dismissed = null
  if (getCurrentScope()) onScopeDispose(() => clearTimeout(timer))

  function close() {
    clearTimeout(timer)
    seq++
    Object.assign(state, { open: false, items: [], active: 0, loading: false, error: false })
  }

  // The box changed or the caret moved: open, move or close the list for what is typed before the caret. A trigger inside
  // a picked chip's label is no trigger (the label is a name, not something being typed).
  function update(text, caret, marks = []) {
    const { chars } = ctx()
    let hit = triggerAt(text, caret, chars)
    if (hit && spans(text, marks).some((s) => s.start <= hit.start && hit.start < s.end)) hit = null
    if (dismissed && !(hit && dismissed.char === hit.char && dismissed.start === hit.start)) dismissed = null
    if (!hit) return close()
    if (dismissed) return // closed with Escape: stays closed for that trigger
    const same = state.open && state.char === hit.char && state.start === hit.start
    if (same && state.query === hit.query) return
    Object.assign(state, { open: true, char: hit.char, start: hit.start, query: hit.query })
    if (!same) Object.assign(state, { items: [], active: 0 })
    schedule(same ? wait : 0)
  }

  function schedule(delay) {
    clearTimeout(timer)
    const run = () => load()
    if (delay) timer = setTimeout(run, delay)
    else run()
  }

  async function load() {
    const { host, thread, mode } = ctx()
    const mine = ++seq
    const char = state.char
    const q = state.query
    if (!host || !thread) return close()
    state.loading = true
    try {
      const args = char === '@' ? { thread, q } : { thread, q, ...(mode === 'advanced' ? { mode: 'advanced' } : {}) }
      const answer = await host.read(char === '@' ? 'people' : 'picker', args)
      if (mine !== seq) return
      const items = char === '@' ? personOptions(answer?.people) : itemOptions(answer?.items)
      // A list that found nothing for a phrase with a space is prose ("#1 priority"), not a search: it closes by itself.
      if (!items.length && /\s/.test(q)) return close()
      Object.assign(state, { items, active: 0, error: false })
    } catch {
      if (mine === seq) Object.assign(state, { items: [], error: true })
    } finally {
      if (mine === seq) state.loading = false
    }
  }

  function move(step) {
    if (!state.items.length) return
    state.active = (state.active + step + state.items.length) % state.items.length
  }

  function dismiss() {
    dismissed = { char: state.char, start: state.start }
    close()
  }

  // The picked option as the text to put in the box and the marks to keep: { text, caret, marks }.
  function pick(option, text, caret, marks) {
    if (!option) return null
    const mark = option.kind === 'mention' ? mentionMark(option) : refMark(option)
    const added = addMark(marks, mark)
    const next = insertPick(text, { start: state.start }, caret, added.label)
    dismissed = null
    close()
    return { ...next, marks: added.marks }
  }

  return { state, update, move, close, dismiss, pick, current: () => state.items[state.active] || null }
}
