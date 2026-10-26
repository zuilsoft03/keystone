// The screens' words in Simple and Advanced mode (P3-01; D-154, D-155, D-161…D-163), from the same words.json the
// server reads (construction_shell/words.py). Display only: stored values, Desk and record numbers keep their words.
import glossary from '@shell/words.json'

export const SIMPLE = 'simple'
export const ADVANCED = 'advanced'

// Only exactly "advanced" is Advanced; anything else is the default Simple (D-154).
export function normal(mode) {
  return mode === ADVANCED ? ADVANCED : SIMPLE
}

// Whether a staff section is on the rail in this mode. A hidden one still opens from a link: a view, not a lock.
export function shows(section, mode) {
  return normal(mode) === ADVANCED || glossary.simple_sections.includes(section)
}

// Whether a portal group shows for a client in this mode (D-163: Simple keeps the final documents).
export function showsGroup(group, mode) {
  return normal(mode) === ADVANCED || glossary.simple_portal_groups.includes(group)
}

const pick = (table, key, mode) => table[key]?.[normal(mode)]

export function sectionLabel(section, mode) {
  return pick(glossary.sections, section, mode) || section
}

export function noun(section, mode) {
  return pick(glossary.nouns, section, mode) || section
}

export function newLabel(section, mode) {
  return pick(glossary.new_labels, section, mode) || 'New'
}

export function groupLabel(group, mode) {
  return pick(glossary.portal_groups, group, mode) || group
}

// A record's state in this mode (D-162). A state the table does not name shows as stored.
export function stateLabel(state, mode) {
  if (normal(mode) === ADVANCED || !state) return state
  return glossary.states[state] || state
}

// A state as the client portal words it: as Simple mode does, except where the word would suggest the client owes a
// decision, which they never do in the portal (D-134, D-165).
export function portalStateLabel(state, mode) {
  if (normal(mode) === ADVANCED || !state) return state
  return glossary.portal_states[state] || stateLabel(state, mode)
}
