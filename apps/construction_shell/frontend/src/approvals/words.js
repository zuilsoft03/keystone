// The client portal's approval words (P3-79; design §3.12, §5): `approvals.*` in words.json, in the client's Simple or
// Advanced mode, with the portal form where the entry has one. A {name} is filled with a value; the sentence is always
// the glossary's, and Vue draws the result with {{ }}, so a value is never markup.
import glossary from '@shell/words.json'
import { normal } from '../words.js'

export const APPROVAL_WORDS = glossary.approvals

export function approvalWord(key, { mode, values = {}, table = APPROVAL_WORDS } = {}) {
  const entry = key.split('.').reduce((at, k) => (at && typeof at === 'object' ? at[k] : undefined), table)
  if (!entry || typeof entry !== 'object') return key
  const word = (typeof entry.portal === 'string' ? entry.portal : entry[normal(mode)]) ?? key
  return word.replace(/\{(\w+)\}/g, (all, name) => (name in values ? String(values[name] ?? '') : all))
}

// A word function bound to one reader's mode, for a component: w('approve'), w('due', { date }).
export function approvalWords(modeRef) {
  return (key, values = {}) => approvalWord(key, { mode: modeRef?.value ?? modeRef, values })
}

// P3-80: the staff screens' words (`approvals_staff`: settings, the Ask sheet, the Decision form), flat keys, no portal form.
export function staffWords(modeRef) {
  return (key, values = {}) => approvalWord(key, { mode: modeRef?.value ?? modeRef, values, table: glossary.approvals_staff })
}
