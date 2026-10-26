// P3-08 (D-139, D-243): the global search's logic, kept apart from the palette so it is tested on its own.

export const METHOD = 'construction_shell.search.search'
export const MIN_QUERY = 2

// The palette's groups, in the rail's order; their words come from words.js in the person's mode (D-154).
export const GROUPS = ['documents', 'rfi', 'submittals', 'variations', 'discuss', 'whiteboards', 'takeoff', 'boq', 'files']

export function grouped(results, label = (s) => s) {
  return GROUPS.map((section) => ({ section, label: label(section), items: results.filter((r) => r.section === section) }))
    .filter((g) => g.items.length)
}

// Where a result opens: the record's own page, or the project's Files for a file.
export function routeOf(r) {
  if (r.section === 'files') return { name: 'section', params: { project: r.project, section: 'files' } }
  return { name: 'section', params: { project: r.project, section: r.section, item: r.name } }
}

// Ctrl K (Cmd K on a Mac) opens the search, except inside the Canvas, where the keys belong to the drawing.
export function isOpenKey(event, route) {
  const key = (event.key || '').toLowerCase()
  if (key !== 'k' || !(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return false
  return !(route?.params?.section === 'whiteboards' && route?.params?.item)
}

// The palette's flat order, for the arrow keys.
export function flat(groups) {
  return groups.flatMap((g) => g.items)
}

// The awesome bar's places to go (D-245): the project's sections whose name matches what was typed, then the dashboard.
export function placesFor(query, project, sections, label) {
  const q = (query || '').trim().toLowerCase()
  if (!q) return []
  const out = []
  if (project) {
    for (const [key, spec] of Object.entries(sections)) {
      if (spec.rail === false) continue
      const name = label(key)
      if (name.toLowerCase().includes(q) || key.includes(q)) {
        out.push({ kind: 'place', title: name, hint: 'Go to', route: { name: 'section', params: { project, section: key } } })
      }
    }
  }
  if ('projects dashboard'.includes(q)) out.push({ kind: 'place', title: 'Project Dashboard', hint: 'Go to', route: { name: 'projects' } })
  return out.slice(0, 5)
}
