// P3-58: what the Company page and the dashboard card show of the server's page(), kept apart so it is tested.

const YES = (v) => (v ? 'On' : 'Off')

export function healthRows(h) {
  if (!h) return []
  const last = h.last_backup
  return [
    ['Scheduler', YES(h.scheduler_on)],
    ['Emails that failed to send', String(h.mail_queue_errors ?? 0)],
    ['Last backup', last ? (typeof last === 'string' ? last : last.at || (last.ok ? 'OK' : 'Failed')) : 'None yet'],
    ['Disk space free', h.disk_free ?? '—'],
    ['App version', h.app_version ?? '—'],
  ]
}

// A skipped step links to its section; a team step lives on People.
export function checklistLink(item) {
  if (item.section === 'people') return '/workspace/people'
  return item.section === 'projects' ? '/workspace' : `/workspace/company#${item.section}` // a first project is made from the dashboard
}
