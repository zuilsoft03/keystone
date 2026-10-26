// Calls to the server. The server checks every call (DR-5); this only carries the CSRF token and reads errors.
export class ApiError extends Error {
  constructor(message, type, status) {
    super(message)
    this.type = type || ''
    this.status = status
  }
}

export function messageOf(data) {
  try {
    const first = JSON.parse(JSON.parse(data._server_messages)[0])
    return first.message || ''
  } catch {
    return data.exception ? String(data.exception).split(':').slice(1).join(':').trim() : ''
  }
}

// A multipart POST (a file and its form fields), as Frappe reads it into the method's arguments.
export async function upload(method, fields, file) {
  const body = new FormData()
  for (const [k, v] of Object.entries(fields)) body.append(k, v)
  body.append('file', file, file.name)
  const res = await fetch(`/api/method/${method}`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'X-Frappe-CSRF-Token': window.csrf_token },
    body,
    credentials: 'same-origin',
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(messageOf(data) || res.statusText, data.exc_type, res.status)
  return data.message
}

// Update fields of one document (Frappe's REST update merges them into the stored document; `frappe.client.save`
// would rebuild the document from what is sent and blank the rest). Sending `modified` makes the server refuse a save
// over a newer version (TimestampMismatchError).
export async function updateDoc(doctype, name, values) {
  const res = await fetch(`/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-Frappe-CSRF-Token': window.csrf_token },
    body: JSON.stringify(values),
    credentials: 'same-origin',
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(messageOf(data) || res.statusText, data.exc_type, res.status)
  return data.data
}

export async function call(method, args = {}, { post = false } = {}) {
  const url = `/api/method/${method}`
  const headers = { Accept: 'application/json' }
  let res
  if (post) {
    headers['Content-Type'] = 'application/json'
    headers['X-Frappe-CSRF-Token'] = window.csrf_token
    res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(args), credentials: 'same-origin' })
  } else {
    const query = new URLSearchParams(
      Object.entries(args).map(([k, v]) => [k, typeof v === 'string' ? v : JSON.stringify(v)]),
    )
    res = await fetch(`${url}?${query}`, { headers, credentials: 'same-origin' })
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(messageOf(data) || res.statusText, data.exc_type, res.status)
  return data.message
}
