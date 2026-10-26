// P3-21 (D-189, D-235): what the People page shows of the accounts, kept apart from the screen so it is tested.

export function filterPeople(people, filter) {
  if (filter === 'off') return people.filter((p) => !p.enabled)
  if (filter === 'clients') return people.filter((p) => p.enabled && p.kind === 'client')
  return people.filter((p) => p.enabled && p.kind !== 'client') // the team, with the accounts managed in Desk
}

export function countOf(people, filter) {
  return filterPeople(people, filter).length
}

export function projectsLine(person, projects) {
  const names = person.projects.map((n) => projects.find((p) => p.name === n)?.project_name || n)
  if (!names.length) return 'No project'
  return names.length <= 2 ? names.join(', ') : `${names.slice(0, 2).join(', ')} and ${names.length - 2} more`
}
