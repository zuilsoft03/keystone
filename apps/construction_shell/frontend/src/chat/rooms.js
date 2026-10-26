// A project's rooms and their unread counts (P3-64, §14.1, §14.5), shared by the screens that show them: the room list,
// the staff rail's Discuss item and the portal's Discussion tab. One read (discuss.api.threads) per project serves all
// of them, and message events reload it after a short wait, so a burst of messages costs one read.
import { reactive } from 'vue'
import { onEvent } from '../realtime.js'
import { setChatUnread } from '../store.js'
import { MESSAGE_EVENT } from './live.js'

const WAIT = 600 // ms between a message event and the reload it causes
const cache = reactive({}) // project -> { rows, loaded, error }
const readers = {} // project -> host.read of the screen that watches it
const watchers = {} // project -> number of screens watching
const timers = {}
let off = null

export function roomsOf(project) {
  return cache[project] || { rows: [], loaded: false, error: '' }
}

// Rooms are the threads that sit in no room (Team first, then Client, as the server orders them).
export function roomRows(project) {
  return roomsOf(project).rows.filter((t) => !t.in_room)
}

// The badge on the rail and the portal tab: room messages by others not read yet. Replies in threads are counted apart,
// on the thread rows the reader follows (P3-74's inbox shows both, "3 new · 2 in threads").
export function unreadOf(project) {
  return roomRows(project).reduce((n, t) => n + (Number(t.unread) || 0), 0)
}

export async function loadRooms(project) {
  const read = readers[project]
  if (!project || !read) return
  try {
    const rows = await read('threads', { project })
    cache[project] = { rows, loaded: true, error: '' }
    setChatUnread(project, unreadOf(project)) // the rail and the portal tab read the store
  } catch (e) {
    cache[project] = { ...roomsOf(project), loaded: true, error: e.message || 'Could not load the rooms.' }
  }
}

// Watch one project's rooms while a screen shows them; returns the function that stops watching.
export function watchRooms(project, host) {
  if (!project || !host || host.viewer === 'preview') return () => {}
  readers[project] = (op, args) => host.read(op, args)
  watchers[project] = (watchers[project] || 0) + 1
  if (!off) off = onEvent(MESSAGE_EVENT, () => Object.keys(watchers).forEach(later))
  loadRooms(project) // a screen that opens shows the counts as they are now
  return () => {
    watchers[project] -= 1
    if (watchers[project] > 0) return
    delete watchers[project]
    clearTimeout(timers[project])
    if (!Object.keys(watchers).length && off) {
      off()
      off = null
    }
  }
}

// Reload soon: after the reader opened a room (its count drops) or a message arrived.
export function later(project) {
  clearTimeout(timers[project])
  timers[project] = setTimeout(() => loadRooms(project), WAIT)
}

// A room's name at read time (§14.8): staff see "Team" and the client company's name; a client sees the firm's name,
// which the server gives as the room's title.
export function roomName(room, { viewer, company = '', w }) {
  if (!room) return ''
  if (viewer !== 'staff') return room.title
  if (room.audience === 'Internal') return w('core.room_team')
  return company || w('core.room_client')
}
