// The frame's pure rules (P2-03), kept apart from components so they are unit-tested (tests/frame.test.js).
import { SECTIONS } from './paths.js'
import { ADVANCED, normal, sectionLabel, shows } from './words.js'

// Construction Project.status -> what the design shows (live in Claude Design, D-124; version 1791648865-5845, Main).
export const STATUS = {
  Open: { label: 'Active', theme: 'green' },
  'On hold': { label: 'On hold', theme: 'amber' },
  Completed: { label: 'Closed', theme: 'gray' },
  Cancelled: { label: 'Cancelled', theme: 'gray' },
}
export const FILTERS = [
  ['all', 'All'],
  ['Open', 'Active'],
  ['On hold', 'On hold'],
  ['Completed', 'Closed'],
]
// A project's badge is a square frappe-ui Avatar in one of the design system's six themes (D-125).
const THEMES = ['blue', 'green', 'amber', 'violet', 'red', 'gray']

export function statusOf(status) {
  return STATUS[status] || { label: status || '—', theme: 'gray' }
}

// A stable theme per project, from its name.
export function themeOf(name) {
  let h = 0
  for (const c of String(name || '')) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return THEMES[h % THEMES.length]
}

export function initials(text) {
  const words = String(text || '').split(/\s+/).filter(Boolean)
  return words.slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?'
}

export function handoverText(days) {
  if (days === null || days === undefined) return ''
  if (days > 1) return `Handover in ${days} days`
  if (days === 1) return 'Handover tomorrow'
  if (days === 0) return 'Handover today'
  return `Handover was ${-days} days ago`
}

// A date as the design writes it: "16 Oct" ("16 Oct 2027" outside this year). Dates arrive as YYYY-MM-DD.
export function shortDate(iso, today = new Date()) {
  if (!iso) return ''
  const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number)
  if (!y || !m || !d) return ''
  const month = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m - 1]
  return y === today.getFullYear() ? `${d} ${month}` : `${d} ${month} ${y}`
}

export function dueText(days) {
  if (days === null || days === undefined) return ''
  if (days > 1) return `In ${days} days`
  if (days === 1) return 'Tomorrow'
  if (days === 0) return 'Due today'
  return `${-days} days late`
}

export function filterCount(projects, filter) {
  return projects.filter((p) => filter === 'all' || p.status === filter).length
}

// The dashboard's search box: the project's name, code or a client contact, in the browser (P2-09).
export function matchesQuery(p, query) {
  const q = String(query || '').trim().toLowerCase()
  return !q || [p.project_name, p.name, ...(p.clients || [])].some((v) => String(v || '').toLowerCase().includes(q))
}

export function shownProjects(projects, filter, sort, query = '') {
  const shown = projects.filter((p) => (filter === 'all' || p.status === filter) && matchesQuery(p, query))
  const byName = (a, b) => (a.project_name || a.name).localeCompare(b.project_name || b.name)
  if (sort === 'name') return [...shown].sort(byName)
  // Handover date: the nearest first, projects without one last.
  return [...shown].sort((a, b) => {
    const x = a.handover_in_days ?? Infinity
    const y = b.handover_in_days ?? Infinity
    return x === y ? byName(a, b) : x - y
  })
}

// The dashboard's figures. Simple mode (D-154) leaves out the project-management ones (RFIs, submittals, variations).
export function kpis(projects, countsOf, mode = ADVANCED) {
  const sum = (key) => projects.reduce((n, p) => n + ((countsOf(p.name) || {})[key] || 0), 0)
  const active = projects.filter((p) => p.status === 'Open').length
  const other = projects.length - active
  const tiles = [{ label: 'Active projects', value: String(active), sub: other ? `${other} on hold or closed` : 'all active' }]
  if (normal(mode) !== ADVANCED) return tiles
  return [
    ...tiles,
    { label: 'Open RFIs', value: String(sum('rfi_open')), sub: 'issued, awaiting an answer' },
    { label: 'Submittals pending', value: String(sum('submittal_open')), sub: 'under review' },
    { label: 'Open variations', value: String(sum('vo_open')), sub: 'change order requests' },
  ]
}

// The user's last project first, then the most recently changed ones.
export function recentProjects(projects, last, n = 3) {
  const first = projects.filter((p) => p.name === last)
  return [...first, ...projects.filter((p) => p.name !== last)].slice(0, n)
}

// The rail in this person's mode (D-154, D-161): Simple lists only its sections, with its words. The section open now
// stays listed, so a link to a hidden one still shows where the person is. The server's rail is unchanged.
export function visibleRail(rail, mode, current = '') {
  return (rail || [])
    .filter((item) => shows(item.section, mode) || item.section === current)
    .map((item) => ({ ...item, label: sectionLabel(item.section, mode) }))
}

// The staff rail in the design's groups (sections.json `group`), with a divider where a group starts. Workspace Config
// still decides which sections show and their order inside a group (D-130).
export function railGroups(rail) {
  const group = (i) => SECTIONS[i.section]?.group ?? 9
  const sorted = rail.map((item, at) => ({ item, at })).sort((a, b) => group(a.item) - group(b.item) || a.at - b.at)
  return sorted.map(({ item }, i) => ({ ...item, divider: i > 0 && group(item) !== group(sorted[i - 1].item) }))
}

// The dashboard tile's line: "8 projects · 6 active".
export function portfolioLine(projects) {
  const n = projects.length
  const active = projects.filter((p) => p.status === 'Open').length
  return `${n} ${n === 1 ? 'project' : 'projects'} · ${active} active`
}

// Switching project keeps the section (not the record: it belongs to the old project), or goes home when the new
// project's rail does not have it.
export function switchTarget(section, rail) {
  const keep = Boolean(section && SECTIONS[section] && (!rail || rail.some((i) => i.section === section)))
  return keep ? section : 'home'
}

// Until a section is built into the shell (P2-04, P2-05), it opens in Desk, which stays available.
export function deskLink(section, project) {
  const q = encodeURIComponent(project)
  return {
    files: `/app/file?cc_project=${q}`,
    documents: `/app/project-document?project=${q}`,
    rfi: `/app/rfi?project=${q}`,
    submittals: `/app/submittal?project=${q}`,
    variations: `/app/variation-order?project=${q}`,
    discuss: `/app/discuss-thread?project=${q}`,
    whiteboards: `/app/whiteboard?project=${q}`,
    takeoff: `/app/cad-drawing?project=${q}`,
    boq: `/app/boq?project=${q}`,
    settings: `/app/workspace-config/${q}`,
  }[section]
}

// P3-09 (D-138, D-157): the project map's pins (only projects with a site) and the way there.
export function pinsOf(projects) {
  return (projects || []).filter((p) => p.site && Number.isFinite(+p.site.lat) && Number.isFinite(+p.site.lng)
    && +p.site.lat && +p.site.lng)
}

export function directionsUrl(site) {
  const at = `${Number(site.lat).toFixed(6)},${Number(site.lng).toFixed(6)}`
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(at)}`
}
