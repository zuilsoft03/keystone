// The portal's tabs (P2-10, D-127): the live design's four (Home, Discussion, Approvals, Files), each holding the
// client-visible sections of construction_core's Workspace Config as groups. A section the team switched off for this
// project (D-098) hides its group, and a tab whose groups are all off; Home always shows. The server already refuses
// the data of a switched-off section: this only hides it. Simple mode (D-154, D-163) also leaves out the groups it does
// not list, so a Simple client has no Approvals tab; a tab opened from a link still shows. The group labels are in the
// glossary (words.js).
import { showsGroup } from '../words.js'

export const TABS = [
  { key: 'home', label: 'Home', icon: 'lucide-house', groups: [] },
  { key: 'discuss', label: 'Discussion', icon: 'lucide-message-circle', groups: ['discuss'] },
  { key: 'approvals', label: 'Approvals', icon: 'lucide-square-check', groups: ['submittals', 'variations', 'rfi'] },
  { key: 'files', label: 'Files', icon: 'lucide-folder', groups: ['files', 'documents', 'whiteboards'] },
]

// A link from before P2-10 named a section as the tab (?tab=rfi): it opens the tab that now holds it.
const TAB_OF_SECTION = Object.fromEntries(TABS.flatMap((t) => t.groups.map((g) => [g, t.key])))

// `open` is the tab on screen: it keeps its groups whatever the mode, so a link to a hidden one still works. Not the
// Approvals tab once it has its own group: there only Advanced mode keeps the record groups (design §3.12; A2, B3).
// `approvals` (P3-79, design §3.12; D-163 amended): the project's Portal approvals switch and approvals section are both
// on, so the Approvals tab carries its one "approvals" group in Simple and Advanced mode alike, ahead of the record
// groups. Off by default: the staff preview and every caller that does not ask see the tabs as before.
export function visibleTabs(sectionsOff, mode = 'advanced', open = '', approvals = false) {
  const off = new Set(sectionsOff || [])
  return TABS.map((t) => ({ ...t, groups: (approvals && t.key === 'approvals' ? ['approvals', ...t.groups] : t.groups)
    .filter((g) => (g === 'approvals' ? approvals : !off.has(g) && ((t.key === open && !(approvals && t.key === 'approvals')) || showsGroup(g, mode)))) }))
    .filter((t) => t.key === 'home' || t.groups.length)
}

export function tabOf(query, sectionsOff, mode = 'advanced', approvals = false) {
  const asked = String(query || 'home')
  const tab = TABS.some((t) => t.key === asked) ? asked : TAB_OF_SECTION[asked] || 'home'
  return visibleTabs(sectionsOff, mode, tab, approvals).some((t) => t.key === tab) ? tab : 'home'
}

// The group a tab opens on: the one asked for (?group=, or an old ?tab=<section>) when it shows, else all of them. A
// tab named by its own key opens on all its groups: ?tab=files is the Files tab, not its "Shared files" group (P3-01;
// until then the Files tab opened on that one group and hid the documents and boards). So the "approvals" group cannot
// be asked for alone; its section is on the page whenever "all" is.
export function groupOf(tab, query, sectionsOff, mode = 'advanced', approvals = false) {
  const groups = visibleTabs(sectionsOff, mode, tab, approvals).find((t) => t.key === tab)?.groups || []
  return query !== tab && groups.includes(query) ? query : 'all'
}

// Where a board link goes: the portal's own board page, or, in the staff preview of a client's portal (P3-05), the
// preview's board panel. The portal views take one of these, so both apps draw them unchanged.
export function portalBoardLink(project, board) {
  return { name: 'portal-board', params: { project, board } }
}

export function previewBoardLink(project, board) {
  return { query: { tab: 'files', group: 'whiteboards', board } }
}

// The staff entry to the preview (D-136): nothing without a client contact (D-058), the preview itself with one, a
// list to choose from with several. `contacts` is portal_preview.contacts' answer, in its order.
export function clientViewEntry(project, contacts) {
  const route = (c) => ({ name: 'section', params: { project, section: 'client-view', item: c.contact } })
  if (!contacts || !contacts.length) return null
  if (contacts.length === 1) return { route: route(contacts[0]) }
  return { options: contacts.map((c) => ({ label: c.name, route: route(c) })) }
}

// P3-07 (D-140, D-158): what the client may send comes from the payload (`upload`, the server's own list), so the
// browser's file picker offers the same types the server checks.
export function acceptOf(upload) {
  return upload?.types?.length ? `.${upload.types.join(',.')}` : ''
}

// P3-75 (D-417): the size a client may send depends on the type: model files (the payload's `model_types`) up to
// `max_bytes`, every other type up to `max_other_bytes`. The server decides again; this saves a long upload.
const MB = 1024 * 1024
export function limitFor(upload, fileName) {
  const ext = String(fileName || '').split('.').pop().toLowerCase()
  const other = upload?.max_other_bytes || upload?.max_bytes || 0
  return (upload?.model_types || []).includes(ext) ? upload.max_bytes || other : other
}

// "250 MB": whole megabytes, as the server words its limits (client_files.size_text).
export const limitText = (bytes) => (bytes % MB === 0 || bytes >= 10 * MB ? `${Math.round(bytes / MB)} MB` : `${(bytes / MB).toFixed(1)} MB`)

// The values of the "up to" hint under Send a file; null when the server names no model types or one limit only.
export function sizeHintValues(upload) {
  const types = (upload?.model_types || []).map((t) => t.toUpperCase())
  if (!types.length || !upload.max_bytes || !upload.max_other_bytes) return null
  return { types: types.join(', '), model: limitText(upload.max_bytes), other: limitText(upload.max_other_bytes) }
}

// A file the client sent is seen by them and the team until the team shares it; anything else was shared with them.
export function fileStatus(f) {
  if (f.mine) return f.shared ? 'Sent by you · shared' : 'Sent by you'
  return 'Shared with you'
}

// A message that only carries a file has the file's name as its text: the card says it already.
export function messageText(m) {
  return m.attachment && m.text === m.attachment.file_name ? '' : m.text
}

const TYPE_LABELS = { pdf: 'PDF', jpg: 'JPEG image', jpeg: 'JPEG image', png: 'PNG image', webp: 'WebP image', docx: 'Word',
  xlsx: 'Excel', pptx: 'PowerPoint', dwg: 'DWG drawing', dxf: 'DXF drawing' }
export function typeLabel(name) {
  const ext = String(name || '').split('.').pop().toLowerCase()
  return TYPE_LABELS[ext] || 'File'
}

export function greeting(hour, name) {
  const part = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
  const first = String(name || '').split(/\s+/)[0]
  return first ? `${part}, ${first}` : part
}

// The latest client-visible messages across the project's threads, newest first.
export function latestMessages(threads, n = 3) {
  const all = []
  for (const t of threads || []) for (const m of t.messages || []) all.push({ ...m, thread: t.title, threadName: t.name })
  return all.slice(-50).reverse().slice(0, n)
}
