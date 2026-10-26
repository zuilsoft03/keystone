// The chat host (P3-64, design §13.2 F1): what one page lets its chat screens do, for one viewer. Only the pages make a
// host (Discuss.vue, portal/Project.vue, ClientView.vue; the partner page with P3-32) and provide it under HOST_KEY;
// the chat components inject it and never name an endpoint themselves. The server checks every call again (DR-5).
import { call, messageOf } from '../api.js'

export const HOST_KEY = Symbol('cc-chat-host')
// P3-68: what a room gives its messages and their parts: { thread, merge(message), say(text), fail(text) } (ChatRoom provides it).
export const ROOM_KEY = Symbol('cc-chat-room')
export const VIEWERS = ['staff', 'client', 'preview'] // 'partner' joins with P3-32 (D-409)

const CORE = 'construction_core.discuss.api.'
const PREVIEW = 'construction_core.portal_preview.'
const FILES = 'construction_core.discuss.parts.attachments.' // P3-65: the attachments part's own endpoints
const MENTIONS = 'construction_core.discuss.parts.mentions.' // P3-66: the @ list
const REFS = 'construction_core.discuss.parts.refs.' // P3-66: the # picker
const EDIT = 'construction_core.discuss.edit.' // P3-68: edit, remove and the earlier texts
const ACTIONS = 'construction_core.discuss.actions.' // P3-68: the Agreed mark and its list
const BOARDS = 'construction_core.whiteboard.api.' // P3-70: the Canvas board a picture is marked up on
const REQUESTS = 'construction_core.discuss.parts.file_requests.' // P3-71: a file request's page, uploads and held files
const READS = ['messages', 'message', 'threads', 'resolve', 'discussion_inbox', 'gallery', 'checking', 'people', 'picker', 'history', 'agreed', 'page'] // discussion_inbox: P3-74, never the preview's
const PART_READS = { gallery: FILES, checking: FILES, people: MENTIONS, picker: REFS, history: EDIT, agreed: ACTIONS, page: REQUESTS } // reads a part serves itself (P3-65's Files in this conversation; P3-75's large files being checked; P3-66's @ list and # picker)
const STAFF_FILES = { tree: 'tree', list: 'list_files', view: 'list_view' } // P3-65: "From project files", staff only
const WRITES = { staff: ['mark_read', 'typing', 'set_pinned', 'discuss_with_team', 'open_thread'], client: ['mark_read', 'typing', 'open_thread'] }

// createHost({ viewer, base, transport, sender }) -> { viewer, readOnly, read, send, write, act, upload, files, links }.
// base: { project, links?, contact? (preview) }; project and contact may be functions. send, write, act, upload and
// files are undefined when the viewer may not use them, so a component tests for the function, not the viewer.
// sender: the upload transport (P3-65), a function (method, fields, file, { onProgress }) -> { done, abort }.
export function createHost({ viewer, base = {}, transport = call, sender = sendWithProgress }) {
  if (!VIEWERS.includes(viewer)) throw new Error(`Unknown chat viewer: ${viewer}`)
  return viewer === 'preview' ? previewHost(base, transport) : liveHost(viewer, base, transport, sender)
}

function liveHost(viewer, base, transport, sender) {
  const writes = WRITES[viewer]
  return Object.freeze({
    viewer,
    readOnly: false,
    get project() { return projectOf(base) },
    // P3-79: whether the page offers approvals to this viewer at all (the portal: the project's switch and section are on). The
    // attach menu lists "Attach an approval…" only then; a page that says nothing offers it (staff).
    get approvals() { return typeof base.approvals === 'function' ? Boolean(base.approvals()) : true },
    read(op, args = {}) {
      if (!READS.includes(op)) return Promise.reject(new Error(`Unknown chat read: ${op}`))
      return transport((PART_READS[op] || CORE) + op, args)
    },
    send({ thread, text, client_id, parts, also_room }) {
      const args = { thread, text, client_id }
      if (parts && Object.keys(parts).length) args.parts = JSON.stringify(parts)
      if (also_room) args.also_room = 1
      return transport(CORE + 'send', args, { post: true })
    },
    write(op, args = {}) {
      if (!writes.includes(op)) return Promise.reject(new Error(`Not a ${viewer} write: ${op}`))
      if (op === 'open_thread') return openThread(viewer, projectOf(base), args, transport)
      return transport(CORE + op, args, { post: true })
    },
    // P3-68: the author's edit (text and the mentions and refs parts it keeps) and remove; staff mark a message Agreed.
    // Each answers the message as the caller now reads it. A client edits and removes their own message too.
    edit({ message, text, parts }) {
      return transport(EDIT + 'edit', { message, text, parts: JSON.stringify(parts || {}) }, { post: true })
    },
    remove(message) {
      return transport(EDIT + 'remove', { message }, { post: true })
    },
    agree: viewer === 'staff' ? (message, agreed) => transport(ACTIONS + 'set_agreed', { message, agreed: agreed ? 1 : 0 }, { post: true }) : undefined,
    // From H-6 a part's own operations: construction_core.discuss.parts.<part>.<op>.
    act(part, op, args = {}) {
      return transport(`construction_core.discuss.parts.${part}.${op}`, args, { post: true })
    },
    // P3-65 (design §3.2): one file staged for `thread`; the send claims it by the id this answers. Never a File id.
    // P3-67: `voice` stages a recording as a voice note (the server reads its type from its bytes and checks its length).
    upload(thread, file, { onProgress, takenOn, voice } = {}) {
      const fields = { thread, ...(takenOn ? { taken_on: takenOn } : {}), ...(voice ? { voice: 1 } : {}) }
      return sender(FILES + 'upload', fields, file, { onProgress })
    },
    // P3-71: one file for a request's item (the person asked); answers the request page. The item's `held` file is checked
    // like any upload (the server's pipeline) and waits for staff to accept it or ask again.
    requestUpload(item, file, { onProgress, takenOn } = {}) {
      return sender(REQUESTS + 'upload', { item, ...(takenOn ? { taken_on: takenOn } : {}) }, file, { onProgress })
    },
    // Staff only (P3-71): the held file of a Received item, opened for review (a photo shows, any other type downloads), and
    // the saved checklists of "Use a template" (they hold no project, person or file).
    heldUrl: viewer === 'staff' ? (item) => `/api/method/${REQUESTS}held?item=${encodeURIComponent(item)}` : undefined,
    templates: viewer === 'staff' ? {
      list: () => transport('frappe.client.get_list', { doctype: 'File Request Template', fields: ['name', 'title', 'items'], order_by: 'creation desc', limit_page_length: 50 }),
      save: (title, items) => transport('frappe.client.insert', { doc: { doctype: 'File Request Template', title: String(title).slice(0, 140), items: JSON.stringify(items) } }, { post: true }),
    } : undefined,
    // "From project files" (staff): the folders, a folder's files and the newest files, read as the reader.
    files: viewer === 'staff' ? (op, args = {}) => {
      if (!STAFF_FILES[op]) return Promise.reject(new Error(`Unknown files read: ${op}`))
      return transport(`construction_core.files.api.${STAFF_FILES[op]}`, { project: projectOf(base), ...args })
    } : undefined,
    // Staff only (P3-65): the File a sent card opens, for the P3-48 viewer. A client's card never names a File.
    fileOf: viewer === 'staff' ? (attachment) => transport(FILES + 'file_of', { attachment }) : undefined,
    // Staff only (P3-70, "Mark up on a Canvas"): a new team-only board that holds `scene`, answered by its name. The board's
    // own endpoints, as Canvas's "New board" and the editor use them; a save that fails leaves the empty board.
    markup: viewer === 'staff' ? async (title, scene) => {
      const board = await transport('frappe.client.insert', { doc: { doctype: 'Whiteboard', project: projectOf(base), title: String(title).slice(0, 140), client_visible: 0 } }, { post: true })
      await transport(BOARDS + 'save', { name: board.name, scene: JSON.stringify(scene), base_version: board.version }, { post: true })
      return board.name
    } : undefined,
    links: base.links || {},
  })
}

// One multipart POST with upload progress, which fetch cannot report (P3-65's tray): { done, abort }. `done` resolves
// to the server's answer and rejects with its message; abort() stops the upload and rejects `done` as cancelled.
export function sendWithProgress(method, fields, file, { onProgress } = {}) {
  const xhr = new XMLHttpRequest()
  const done = new Promise((resolve, reject) => {
    const body = new FormData()
    for (const [k, v] of Object.entries(fields)) body.append(k, v)
    body.append('file', file, file.name)
    xhr.open('POST', `/api/method/${method}`)
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.setRequestHeader('X-Frappe-CSRF-Token', globalThis.csrf_token || '')
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total)
    xhr.onload = () => {
      let data = {}
      try { data = JSON.parse(xhr.responseText || '{}') } catch { /* not the server's own answer */ }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(data.message)
      reject(Object.assign(new Error(messageOf(data) || xhr.statusText || 'Upload failed'), { status: xhr.status }))
    }
    xhr.onerror = () => reject(new Error('Upload failed'))
    xhr.onabort = () => reject(Object.assign(new Error('Cancelled'), { cancelled: true }))
    xhr.send(body)
  })
  return { done, abort: () => xhr.abort() }
}

// The staff preview of a client's portal (P3-05, D-136): GET only, the client's own reads in the core shape, each
// limited to what the caller reads (portal_preview.preview_threads, preview_messages, preview_message; audit F1).
const PREVIEW_READS = { threads: 'preview_threads', messages: 'preview_messages', message: 'preview_message' }

function previewHost(base, transport) {
  return Object.freeze({
    viewer: 'preview',
    readOnly: true,
    get project() { return projectOf(base) },
    read(op, args = {}) {
      if (!PREVIEW_READS[op]) return Promise.reject(new Error(`The preview reads no ${op}`))
      const contact = typeof base.contact === 'function' ? base.contact() : base.contact
      return transport(PREVIEW + PREVIEW_READS[op], { project: projectOf(base), contact, ...args })
    },
    send: undefined,
    write: undefined,
    act: undefined,
    edit: undefined,
    remove: undefined,
    agree: undefined,
    upload: undefined,
    files: undefined,
    fileOf: undefined,
    markup: undefined,
    requestUpload: undefined,
    heldUrl: undefined,
    templates: undefined,
    links: base.links || {},
  })
}

// "Reply in thread" on a message of a room (§14.1): the thread's name. A client opens it through the portal's endpoint
// (QR-2); staff insert it, and the server places it in the message's room and refuses a second open thread on it.
async function openThread(viewer, project, { message, audience, title }, transport) {
  if (viewer === 'client') return transport('construction_core.portal_api.open_thread', { message }, { post: true })
  const doc = await transport('frappe.client.insert', { doc: {
    doctype: 'Discuss Thread', project, audience, anchor_doctype: 'Discuss Message', anchor_name: message,
    title: String(title || message).slice(0, 140),
  } }, { post: true })
  return doc.name
}

// base.project may be a function, for a page whose route names the project (the portal's project page).
function projectOf(base) {
  return typeof base.project === 'function' ? base.project() : base.project
}
