// The frame's state: the user's projects and their live counts. The server decides what is in it.
import { reactive } from 'vue'
import { call } from './api.js'

export const state = reactive({ projects: [], lastProject: null, canCreate: false, loaded: false, error: '', counts: {}, frames: {}, chatUnread: {}, inboxUnread: {} })

export async function loadProjects() {
  try {
    const data = await call('construction_shell.api.projects')
    state.projects = data.projects
    state.lastProject = data.last_project
    state.canCreate = data.can_create
    for (const p of data.projects) state.counts[p.name] = p.counts
    if (data.inbox_unread) setInboxUnread(data.inbox_unread, true)
    state.error = ''
  } catch (e) {
    state.error = e.message || 'Could not load your projects.'
  } finally {
    state.loaded = true
  }
}

export function countsOf(project) {
  return state.counts[project] || {}
}

export function setCounts(project, counts) {
  state.counts[project] = counts
}

// P3-64: the reader's unread room messages per project, for the rail's Discuss item and the portal's Discussion tab. The
// frame brings the first count; a page's chat host (chat/rooms.js) keeps it current. Display only.
export function chatUnreadOf(project) {
  return Number(state.chatUnread[project]) || 0
}

export function setChatUnread(project, count) {
  if (project) state.chatUnread[project] = Number(count) || 0
}

// P3-74: the top bar's Discussion inbox count, rooms with something new per active member project. The frame brings
// the first counts (api.projects); a live page host keeps them current: the inbox page (all its projects) and the
// Discuss page (its own). No app-wide chat host reads it (F1). Display only.
export function inboxUnreadTotal() {
  return Object.values(state.inboxUnread).reduce((n, c) => n + (Number(c) || 0), 0)
}

export function setInboxUnread(byProject, replace = false) {
  if (replace) state.inboxUnread = {}
  for (const [project, count] of Object.entries(byProject || {})) state.inboxUnread[project] = Number(count) || 0
}

export async function rememberProject(project) {
  if (state.lastProject === project) return
  state.lastProject = project
  try {
    await call('construction_shell.api.set_last_project', { project }, { post: true })
  } catch {
    // Not remembered: the dashboard then orders by the last change instead. Nothing else depends on it.
  }
}

// One project's frame (api.project: header, rail, counts). Kept per project, so the dashboard's rail can show the last
// project's sections as the design draws it (P2-09) without asking twice.
export async function fetchFrame(project) {
  const data = await call('construction_shell.api.project', { project })
  state.frames[project] = data
  setCounts(project, data.counts)
  if ('chat_unread' in data) setChatUnread(project, data.chat_unread)
  return data
}
