// The chat's words (P3-64, design §13.2 F5): chat.core.*, chat.kind.* and chat.<part>.* in words.json, in the reader's
// Simple or Advanced mode, with the portal's own word where a client sees it. A {name} is filled with a value; the
// sentence is always the glossary's. Vue draws the result with {{ }}, so a value is never markup.
import glossary from '@shell/words.json'
import { normal } from '../words.js'

export const CHAT = glossary.chat

// chatWord('core.send', { mode, portal, values }) -> "Send". An unknown key answers itself, so a gap shows as a key.
export function chatWord(key, { mode, portal = false, values = {} } = {}) {
  const entry = key.split('.').reduce((at, k) => (at && typeof at === 'object' ? at[k] : undefined), CHAT)
  if (!entry || typeof entry !== 'object') return key
  const word = (portal && typeof entry.portal === 'string' ? entry.portal : entry[normal(mode)]) ?? key
  return word.replace(/\{(\w+)\}/g, (all, name) => (name in values ? String(values[name] ?? '') : all))
}

// A word function bound to one reader, for a component: w('core.send'), w('core.typing', { name }).
export function wordsFor(modeRef, portal = false) {
  return (key, values = {}) => chatWord(key, { mode: modeRef?.value ?? modeRef, portal, values })
}
