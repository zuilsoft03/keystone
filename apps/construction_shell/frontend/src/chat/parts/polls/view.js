// What the poll card draws (P3-68, design §3.7; canvas "Message cards": Poll, team room and client room), from the server's
// card alone: { question, multiple, anonymous, closes_on, closed, people, options[{ key, text, picture, votes, mine,
// voters? }], can_vote, can_close }. Pure functions.
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const WEEK = 7 * 24 * 3600 * 1000

// "Fri 17:00" within a week, else "12 Nov 17:00": the site's wall time as written.
export function closesText(value, now = new Date()) {
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(String(value || ''))
  if (!m) return ''
  const at = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]))
  const time = `${m[4]}:${m[5]}`
  if (at - now < WEEK && at - now > -WEEK) return `${DAYS[at.getDay()]} ${time}`
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${time}`
}

// The pictures of a message's options by attachment id: { id: { src, name } } for those whose preview is ready.
export function picturesOf(attachments) {
  const out = {}
  for (const c of Array.isArray(attachments) ? attachments : []) {
    if (c && c.attachment) out[c.attachment] = { src: c.preview?.state === 'ready' ? c.preview.src || '' : '', name: c.file_name || '' }
  }
  return out
}

// The attachments of a poll message that are not its options' pictures (the attachments part draws only those).
export function withoutPictures(message) {
  const poll = message?.parts?.polls
  const files = message?.parts?.attachments
  if (!poll || !Array.isArray(files)) return files
  const used = new Set((poll.options || []).map((o) => o.picture).filter(Boolean))
  return files.filter((c) => !used.has(c.attachment))
}

// The bar of an option: its share of all votes (several choices: of the people who voted), a whole percent.
export function share(poll, option) {
  const all = (poll.options || []).reduce((n, o) => n + (Number(o.votes) || 0), 0)
  const base = poll.multiple ? Number(poll.people) || 0 : all
  return base > 0 ? Math.min(100, Math.round(((Number(option.votes) || 0) / base) * 100)) : 0
}

// The keys the reader's vote becomes when they press `key`: one choice replaces (or takes back the same one); several
// choices toggle that option.
export function nextVote(poll, key) {
  const mine = (poll.options || []).filter((o) => o.mine).map((o) => o.key)
  if (!poll.multiple) return mine.includes(key) ? [] : [key]
  return mine.includes(key) ? mine.filter((k) => k !== key) : [...mine, key]
}

// The names of an option's voters (a named poll), as many as fit, then "+n".
export function voterLine(option, limit = 4) {
  const names = (option.voters || []).map((v) => v.name).filter(Boolean)
  if (!names.length) return ''
  return names.length > limit ? `${names.slice(0, limit).join(', ')} +${names.length - limit}` : names.join(', ')
}
