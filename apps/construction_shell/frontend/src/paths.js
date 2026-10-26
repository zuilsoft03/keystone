// The workspace's URL shapes, from the same sections.json the server reads (workspace_page.known_path, D-109).
import spec from '@shell/sections.json'

const SEGMENT = new RegExp(spec.segment)
export const SECTIONS = spec.sections

export function knownPath(path) {
  const parts = path.split('/').filter(Boolean)
  if (parts[0] !== 'workspace') return false
  const rest = parts.slice(1)
  if (!rest.length) return true
  if (rest.length > 4 || !rest.every((p) => SEGMENT.test(p))) return false
  if (rest.length === 1) return true
  const section = SECTIONS[rest[1]]
  if (!section) return false
  if (rest.length === 2) return true
  if (!section.item) return false
  return rest.length === 3 || section.actions.includes(rest[3])
}
