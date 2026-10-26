// The Files screen's logic (P3-41, D-292, D-294), kept apart from its markup so it is tested on its own: the folder
// tree as the design draws it, file kinds and their icons, sorting, the filter chips and the selection.

// File kinds, one colour family each, as the design's type tiles (soft badge colours of the design system).
export const KINDS = {
  cad: { label: 'Drawing', icon: 'lucide-drafting-compass', tile: 'bg-surface-violet-2 text-ink-violet-7' },
  pdf: { label: 'PDF document', icon: 'lucide-file-text', tile: 'bg-surface-red-2 text-ink-red-7' },
  doc: { label: 'Document', icon: 'lucide-align-left', tile: 'bg-surface-blue-2 text-ink-blue-7' },
  sheet: { label: 'Spreadsheet', icon: 'lucide-sheet', tile: 'bg-surface-green-2 text-ink-green-7' },
  slides: { label: 'Presentation', icon: 'lucide-presentation', tile: 'bg-surface-amber-2 text-ink-amber-7' },
  image: { label: 'Image', icon: 'lucide-image', tile: 'bg-surface-amber-2 text-ink-amber-7' },
  archive: { label: 'Archive', icon: 'lucide-archive', tile: 'bg-surface-gray-2 text-ink-gray-7' },
  other: { label: 'File', icon: 'lucide-file', tile: 'bg-surface-gray-2 text-ink-gray-7' },
}
const BY_EXT = {
  dxf: 'cad', dwg: 'cad', ifc: 'cad', rvt: 'cad', rfa: 'cad', skp: 'cad', pdf: 'pdf', doc: 'doc', docx: 'doc', odt: 'doc', rtf: 'doc', txt: 'doc', md: 'doc',
  xls: 'sheet', xlsx: 'sheet', ods: 'sheet', csv: 'sheet', ppt: 'slides', pptx: 'slides', odp: 'slides',
  jpg: 'image', jpeg: 'image', png: 'image', webp: 'image', gif: 'image', zip: 'archive', rar: 'archive', '7z': 'archive',
}

export function extOf(name) {
  const m = /\.([A-Za-z0-9]+)$/.exec(String(name || ''))
  return m ? m[1].toLowerCase() : ''
}

export function kindOf(name) {
  return BY_EXT[extOf(name)] || 'other'
}

export function typeLabel(name) {
  const ext = extOf(name)
  return ext ? `${ext.toUpperCase()} ${KINDS[kindOf(name)].label.toLowerCase()}` : KINDS.other.label
}

export function initials(name) {
  return String(name || '?').split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?'
}

// The tree as rows to draw: each folder with its depth, whether it has children and is open, and its count. A closed
// folder hides everything below it. The root is always open.
export function treeRows(nodes, open) {
  const children = new Map()
  for (const n of nodes) {
    if (n.parent === null || n.parent === undefined) continue
    if (!children.has(n.parent)) children.set(n.parent, [])
    children.get(n.parent).push(n)
  }
  const rows = []
  const walk = (path, depth) => {
    for (const n of (children.get(path) || []).sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }))) {
      const kids = (children.get(n.path) || []).length > 0
      const isOpen = kids && open.has(n.path)
      rows.push({ ...n, depth, hasChildren: kids, open: isOpen })
      if (isOpen) walk(n.path, depth + 1)
    }
  }
  const root = nodes.find((n) => n.path === '')
  if (root) rows.push({ ...root, depth: 0, hasChildren: true, open: true })
  walk('', 1)
  return rows
}

// The folders to open so a path shows: every parent of it.
export function parentsOf(path) {
  const parts = String(path || '').split('/').filter(Boolean)
  return parts.slice(0, -1).map((_, i) => parts.slice(0, i + 1).join('/'))
}

export function totalCount(nodes) {
  return nodes.reduce((sum, n) => sum + (Number(n.count) || 0), 0)
}

// The breadcrumb of a folder path: "Project files", then each folder, the last one being the current.
export function crumbsOf(path, nodes) {
  const byPath = new Map(nodes.map((n) => [n.path, n]))
  const parts = String(path || '').split('/').filter(Boolean)
  const crumbs = [{ label: 'Project files', folder: byPath.get('')?.folder || '', path: '' }]
  parts.forEach((_, i) => {
    const p = parts.slice(0, i + 1).join('/')
    crumbs.push({ label: parts[i], folder: byPath.get(p)?.folder || '', path: p })
  })
  return crumbs
}

export function sortFiles(rows, key, dir) {
  const sign = dir === 'asc' ? 1 : -1
  const value = {
    name: (r) => String(r.file_name || '').toLowerCase(),
    owner: (r) => String(r.owner_name || '').toLowerCase(),
    modified: (r) => String(r.modified || ''),
    size: (r) => Number(r.file_size) || 0,
  }[key] || ((r) => String(r.modified || ''))
  return [...rows].sort((a, b) => {
    const x = value(a)
    const y = value(b)
    return x < y ? -sign : x > y ? sign : 0
  })
}

// The design's filter chips: Type, People, Modified and Client access (a file a client sent counts as "Sender only").
export const MODIFIED = [
  { value: '', label: 'Any time' }, { value: '1', label: 'Today' }, { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
]
export const ACCESS = [
  { value: '', label: 'Anyone' }, { value: 'shared', label: 'Shared with the client' }, { value: 'staff', label: 'Team only' },
  { value: 'sender', label: 'Sent by a client' },
]

export function accessOf(f) {
  if (f.client_visible) return 'shared'
  return f.from_client ? 'sender' : 'staff'
}

export function filterFiles(rows, { query = '', type = '', owner = '', modified = '', access = '' } = {}, now = new Date()) {
  const q = query.trim().toLowerCase()
  const since = modified ? new Date(now.getFullYear(), now.getMonth(), now.getDate() - (Number(modified) - 1)) : null
  return rows.filter((f) => (!q || String(f.file_name).toLowerCase().includes(q))
    && (!type || kindOf(f.file_name) === type)
    && (!owner || f.owner_name === owner)
    && (!since || new Date(String(f.modified).replace(' ', 'T')) >= since)
    && (!access || accessOf(f) === access))
}

export function typeOptions(rows) {
  const kinds = [...new Set(rows.map((f) => kindOf(f.file_name)))].sort()
  return [{ value: '', label: 'Any type' }, ...kinds.map((k) => ({ value: k, label: KINDS[k].label }))]
}

export function ownerOptions(rows) {
  const owners = [...new Set(rows.map((f) => f.owner_name).filter(Boolean))].sort()
  return [{ value: '', label: 'Anyone' }, ...owners.map((o) => ({ value: o, label: o }))]
}

// Selection as Drive does it: a click picks one, Ctrl or Cmd adds or removes, Shift takes the range from the last pick.
export function nextSelection(selected, ordered, name, { ctrl = false, shift = false } = {}, anchor = null) {
  if (shift && anchor && ordered.includes(anchor)) {
    const [a, b] = [ordered.indexOf(anchor), ordered.indexOf(name)].sort((x, y) => x - y)
    return new Set([...(ctrl ? selected : []), ...ordered.slice(a, b + 1)])
  }
  if (ctrl) {
    const next = new Set(selected)
    if (next.has(name)) next.delete(name)
    else next.add(name)
    return next
  }
  return new Set([name])
}

// A link to a file inside the workspace, for Copy link: it opens the folder with the file selected.
export function fileLink(origin, project, folder, file) {
  const q = new URLSearchParams({ folder: folder || '', file })
  return `${origin}/workspace/${encodeURIComponent(project)}/files?${q.toString()}`
}

// A file's date as the design's list writes it: "Today 09:12", "Yesterday", "12 Oct" ("12 Oct 2025" in another year).
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export function modifiedLabel(value, now = new Date()) {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(String(value || ''))
  if (!m) return ''
  const [y, mo, d] = [+m[1], +m[2], +m[3]]
  const day = new Date(y, mo - 1, d)
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const days = Math.round((today - day) / 86400000)
  if (days === 0) return m[4] ? `Today ${m[4]}:${m[5]}` : 'Today'
  if (days === 1) return 'Yesterday'
  return y === now.getFullYear() ? `${d} ${MONTHS[mo - 1]}` : `${d} ${MONTHS[mo - 1]} ${y}`
}

// P3-43 (D-301, D-302, D-303): file versions. Letters run as spreadsheet columns: A..Z, then AA.
export function revNumber(rev) {
  return String(rev || 'A').toUpperCase().split('').reduce((n, c) => n * 26 + (c.charCodeAt(0) - 64), 0)
}
export function revLetter(n) {
  let out = ''
  for (let k = Math.max(1, n); k > 0; k = Math.floor((k - 1) / 26)) out = String.fromCharCode(65 + ((k - 1) % 26)) + out
  return out
}
export const nextRev = (rev) => revLetter(revNumber(rev) + 1)
export const revLabel = (rev) => `Rev ${rev || 'A'}`
export const versionCount = (n) => (n === 1 ? '1 version' : `${n} versions`)

// A file keeps its address through its revisions, so a browser may hold the old bytes: the content's hash in the
// link asks for the current ones (the server ignores the parameter).
export function freshUrl(url, hash) {
  if (!url || !hash) return url || ''
  return `${url}${url.includes('?') ? '&' : '?'}v=${encodeURIComponent(String(hash).slice(0, 12))}`
}

// What Compare can show side by side: pictures and PDFs; other kinds are compared by their facts.
export function previewOf(name) {
  const kind = kindOf(name)
  return kind === 'image' || kind === 'pdf' ? kind : ''
}

export const sameType = (a, b) => extOf(a) === extOf(b)

// D-302: what happens to a takeoff measured on the file's current revision, in the owner's words.
export const TAKEOFF_CHOICES = [
  { value: 'reuse', label: 'Reuse it on Rev {new}', detail: 'The takeoff moves to Rev {new} as it is, with its points and scale. Check them if the drawing changed.' },
  { value: 'copy', label: 'Edit a copy on Rev {new}', detail: 'Rev {old} keeps its takeoff. A copy goes onto Rev {new} for you to adjust, and opens in Takeoff afterwards.' },
  { value: 'new', label: 'Start new on Rev {new}', detail: 'Rev {old} keeps its takeoff. Rev {new} starts with none.' },
]
export const fillRev = (text, old, next) => text.replaceAll('{old}', old).replaceAll('{new}', next)
