// What a file request's card and page draw (P3-71, design §3.10; canvas "Message cards": File requests), from the server's
// card alone: { request, title, due_on, status, received, total, role: 'staff'|'recipient'|'other', asked, may_upload, items[
// { item, required, status, description?, reason?, held?, uploaded_by?, can_accept?, can_ask_again?, mine?, may_upload? }],
// requested_by?, recipients?, can_nudge?, can_cancel? }. The page adds `thread`, `message`, `files_left_today`, and each item's
// `example` and `file` ({ file_name, url } | null). Pure functions: the server decides every right again, so a flag the
// reader did not get is simply false here.
export const MAX_ITEMS = 20
export const MAX_TITLE = 140
export const MAX_DESCRIPTION = 200
export const MAX_REASON = 300
export const MAX_DUE_DAYS = 90
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// "Fri 24 Oct": the site's date as written (a date has no zone, so the reader's clock never moves it).
export function dayText(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value || ''))
  if (!m) return ''
  const at = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  return `${DAYS[at.getDay()]} ${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}`
}

// "Acme Corp, Maria Santos +2": the people asked, as many as fit.
export function whoLine(recipients, limit = 2) {
  const names = (recipients || []).map((p) => p?.name).filter(Boolean)
  return names.length > limit ? `${names.slice(0, limit).join(', ')} +${names.length - limit}` : names.join(', ')
}

// The bar and the count: Received and Accepted both count as received (the server's own number).
export function progressOf(card) {
  const total = Number(card?.total) || 0
  const received = Math.min(total, Number(card?.received) || 0)
  return { received, total, percent: total ? Math.round((received / total) * 100) : 0 }
}

// An item's state as the reader sees it: a Waiting item that carries a reason was asked for again.
export function stateOf(item) {
  if (item.status === 'Accepted') return 'accepted'
  if (item.status === 'Received') return 'received'
  return item.reason ? 'again' : 'waiting'
}

// The card for one reader. `can` says what this screen could do at all (the staff preview of a portal can do nothing):
// { act, upload }. A button shows only when the server's flag and the screen agree.
export function cardView(card, can = {}) {
  const open = card?.status === 'Open'
  const staff = card?.role === 'staff'
  const act = Boolean(can.act)
  const sends = Boolean(can.upload && act && card?.asked && card?.may_upload && open)
  return {
    open,
    staff,
    sends,
    // staff open the page to see the whole request; a person asked opens it to send, or to look once nothing is waited for
    opens: act && (staff || Boolean(card?.asked)) && !sends,
    nudges: act && staff && Boolean(card?.can_nudge),
    cancels: act && staff && Boolean(card?.can_cancel),
    items: (card?.items || []).map((item, i) => ({
      ...item,
      n: i + 1,
      state: stateOf(item),
      accepts: act && staff && Boolean(item.can_accept),
      asksAgain: act && staff && Boolean(item.can_ask_again),
      reviews: act && staff && Boolean(item.held && !item.held.checking && !item.held.refused),
    })),
  }
}

// An item's name: its description, or "File 3" for a reader the server gave no description (not asked, not staff).
export function itemName(item, w) {
  return item.description || w('file_requests.file_n', { n: item.n ?? 1 })
}

// The slot of the request page for one item, with the upload in progress (`busy`: { progress } | null).
// 'uploading' (this device is sending), 'checking' (the server scans it), 'refused' (the scan said no: send another),
// then the item's own state.
export function slotState(item, busy = null) {
  if (busy) return 'uploading'
  if (item.held?.checking) return 'checking'
  if (item.held?.refused && item.status === 'Received') return 'refused'
  return stateOf(item)
}

// A slot takes a file when the server says so for this item and the project's daily cap (D-182) has room.
export function slotOpen(item, page) {
  return Boolean(item.may_upload && page?.may_upload && page.status === 'Open' && page.files_left_today !== 0)
}

// The cap line for a client asked: how many more files can go today; null for anyone else.
export function capWord(left) {
  if (!Number.isInteger(left)) return null
  if (left <= 0) return { key: 'file_requests.cap_zero', values: {} }
  return left === 1 ? { key: 'file_requests.cap_one', values: {} } : { key: 'file_requests.cap', values: { count: left } }
}

// Nudge's answer, { reminded, at_cap }, as words: [{ key, values }] (one or two lines; none waiting says so).
export function nudgeWords(answer) {
  const sent = Number(answer?.reminded) || 0
  const used = Number(answer?.at_cap) || 0
  const out = []
  if (sent) out.push({ key: sent === 1 ? 'file_requests.nudge_sent_one' : 'file_requests.nudge_sent', values: { count: sent } })
  if (used) out.push({ key: used === 1 ? 'file_requests.nudge_used_one' : 'file_requests.nudge_used', values: { count: used } })
  return out.length ? out : [{ key: 'file_requests.nudge_none', values: {} }]
}

// Whether a page is still waiting on a scan, so it is read again until the server has an answer.
export function scanning(page) {
  return (page?.items || []).some((i) => i.held?.checking)
}
