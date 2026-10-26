// "Discuss this" (P3-66, design §3.5, D-413, D-418, R-32): the project team opens a file's or a record's conversation. The
// Team room always has one; the Client room only when the project's clients may read the item now. The server decides
// both and answers "Not found" for an item the caller cannot read. Pages call these; the chat host is not involved.
import { call } from './api.js'

const REFS = 'construction_core.discuss.parts.refs.'

// The rooms the item can be discussed in: [{ room: 'Internal' | 'Client', thread: name | null }], Team first.
export async function discussRooms(doctype, name) {
  const answer = await call(`${REFS}discuss_rooms`, { doctype, name })
  return (answer?.rooms || []).filter((r) => r && (r.room === 'Internal' || r.room === 'Client'))
}

// Opens the item's one open thread in that room, making it on first use: { thread, room } (the room's name).
export function discussThis(doctype, name, room) {
  return call(`${REFS}discuss_this`, { doctype, name, room }, { post: true })
}

// Where the thread is: the project's Discussion at that room, with the thread beside it.
export function threadRoute(project, answer) {
  return { name: 'section', params: { project, section: 'discuss', item: answer.room }, query: { thread: answer.thread } }
}
