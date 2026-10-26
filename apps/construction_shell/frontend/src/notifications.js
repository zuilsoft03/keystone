// The staff notification bell (P3-06; D-139, D-175). The server words every notice in the reader's mode and checks
// every call (construction_shell.notifications); this keeps the list and the unread count, and reloads them when a
// notice arrives, when another tab marks one read, and after a reconnect.
import { reactive } from 'vue'
import { call } from './api.js'

export const NOTICES_EVENT = 'cc_notices' // construction_core.notifications.NOTICES_EVENT: the reader's notices changed
const LIVE = ['notification', NOTICES_EVENT, 'connect'] // a new notice (Frappe's own event), a change elsewhere, a reconnect
const METHOD = 'construction_shell.notifications.'

export const bell = reactive({ items: [], unread: 0, more: false, loaded: false, error: '' })

// The badge: nothing at 0, then the count; past the server's cap it reads "20+".
export function badgeText(unread, more = false) {
  if (!unread) return ''
  return more ? `${unread}+` : String(unread)
}

export function bellLabel(unread, more = false) {
  if (!unread) return 'Notifications'
  return more ? `Notifications, more than ${unread} unread` : `Notifications, ${unread} unread`
}

let mode = ''
let running = null
let again = false

const withMode = (args = {}) => (mode ? { ...args, mode } : args)

function take(data) {
  bell.unread = data?.unread || 0
  bell.more = Boolean(data?.more)
}

// One call at a time: events that arrive during a load ask for one more load after it, however many they are.
export function load(nextMode) {
  if (nextMode) mode = nextMode
  if (running) {
    again = true
    return running
  }
  running = (async () => {
    try {
      do {
        again = false
        const data = await call(`${METHOD}feed`, withMode())
        bell.items = data?.items || []
        take(data)
        bell.loaded = true
        bell.error = ''
      } while (again)
    } catch (e) {
      bell.error = 'Notifications could not be loaded.'
    } finally {
      running = null
    }
  })()
  return running
}

export async function markRead(item) {
  if (!item || item.read) return
  item.read = true
  bell.unread = Math.max(0, bell.unread - 1)
  try {
    take(await call(`${METHOD}mark_read`, withMode({ name: item.name }), { post: true }))
  } catch {
    load()
  }
}

export async function markAll() {
  for (const item of bell.items) item.read = true
  bell.unread = 0
  bell.more = false
  try {
    take(await call(`${METHOD}mark_all_read`, withMode(), { post: true }))
  } catch {
    load()
  }
}

// Wires the live updates through the app's socket (realtime.onEvent); returns the one function that removes them.
export function attach(onEvent, reload) {
  const offs = LIVE.map((event) => onEvent(event, () => reload()))
  return () => offs.forEach((off) => off())
}
