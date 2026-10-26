// Threads in rooms (P3-64, R-32 §14.1, §14.5): what the screens draw from the project's thread rows (discuss.api.threads):
// the reply line under a root message, the staff's "Team discussing" marker, and the room's thread lists. Pure.
import { plain } from './tokens.js'

// The thread whose root is `message` in its own room: its reply line is drawn there, never in another room (§14.1).
export function lineOf(rows, room, message) {
  return (rows || []).find((t) => t.in_room === room && t.root === message) || null
}

// The Team-room threads about a client message ("Discuss with team"), for the staff marker (QR-3).
export function teamThreadsAbout(rows, teamRoom, message) {
  if (!teamRoom) return []
  return (rows || []).filter((t) => t.in_room === teamRoom && t.about === message)
}

// A room's open threads, newest activity first.
export function activeThreads(rows, room) {
  return (rows || []).filter((t) => t.in_room === room && t.status !== 'Locked' && t.status !== 'Resolved')
    .sort((a, b) => String(b.last_message_on || '').localeCompare(String(a.last_message_on || '')))
}

// The threads the reader follows (§14.5), in any room, newest activity first.
export function followedThreads(rows) {
  return (rows || []).filter((t) => t.in_room && t.following)
    .sort((a, b) => String(b.last_message_on || '').localeCompare(String(a.last_message_on || '')))
}

// A thread's name: the first line of the message it hangs off, else the word for that message's kind (a photo has no
// text of its own, P3-65), else its stored title (a record's, or "Conversation"). `w`: the reader's chat words.
export function threadTitle(row, w) {
  // P3-66: a title made from a message's text carries its tokens as words ("@someone"), never the raw token
  const title = row?.topic || (row?.topic_kind && w ? w(`kind.${row.topic_kind}`) : '') || row?.title || ''
  return w ? plain(title, w) : title
}

// The threads that mention the reader (P3-66, §14.6): an unread mention, as the thread row says it (`mentioned`).
export function mentionedThreads(rows) {
  return (rows || []).filter((t) => t.mentioned)
}

// Unread replies count only for a thread the reader follows (§14.5).
export function newReplies(row) {
  return row && row.following ? Number(row.unread) || 0 : 0
}

// "5 replies · last by Maria, 10:42" and its accessible name "5 replies, 2 new, last by Maria at 10:42".
export function replyLine(row, w, time = (v) => v) {
  const count = Number(row?.replies) || 0
  const replies = count === 1 ? w('core.replies_one') : w('core.replies', { count })
  const fresh = newReplies(row)
  const name = row?.last_by?.name
  const when = row?.last_on ? time(row.last_on) : ''
  const text = name ? `${replies} · ${w('core.last_by', { name, time: when })}` : replies
  const aria = [replies, fresh ? w('core.replies_new', { count: fresh }) : '', name ? w('core.last_by_aria', { name, time: when }) : '']
    .filter(Boolean).join(', ')
  return { text, aria, fresh }
}
