// What a tagged item's card draws (P3-66, design §3.5, §13.1 S-resolver; canvas "Message cards": Records from tags), from
// the server's card alone: { pos, type, doctype, name?, title, state, number, simple, section, url?, size? }. The server
// leaves out an item the viewer cannot read, so a token with no card draws the neutral card (rule 2). Pure.
import { requestRoute } from '../../../approvals/staff/request.js'
import { approvalLink } from '../../../approvals/terms.js'
import { formatSize } from '../../../sections/util.js'
import { portalStateLabel, stateLabel } from '../../../words.js'
import { chatWord } from '../../words.js'

// The type word's key (chat.refs.<key>) is the card's own `type`; each has an icon (written out so Tailwind finds it).
export const ICONS = {
  file: 'lucide-file-text',
  board: 'lucide-layout-dashboard',
  document: 'lucide-book-open',
  question: 'lucide-circle-help',
  review: 'lucide-clipboard-check',
  change: 'lucide-git-compare',
  drawing: 'lucide-ruler',
  approval: 'lucide-square-check',
}
export const NEUTRAL_ICON = 'lucide-lock'

// Simple mode hides the project-management items (a question, an item for review, a change) but keeps the published
// documents (rule 13, D-163; lead's provisional decision, for the owner): a Project Document draws in full in Simple mode.
// P3-79: so does an approval request, because the Approvals tab shows in both modes (design §3.12) and a client mostly reads Simple.
const SIMPLE_KEEPS = ['Project Document', 'Approval Request']
export const hiddenInSimple = (item) => Boolean(item) && item.simple === false && !SIMPLE_KEEPS.includes(item.doctype)

// An approval request's status as the card's state key (chat.approval.state.*) and the badge's colour. The picker and the
// tag carry the stored status; the live card's own state words come from the server (approvals.card.state).
const APPROVAL_STATE = { Open: 'waiting', Approved: 'approved', Returned: 'returned', Superseded: 'replaced', Voided: 'voided', Draft: 'draft' }
const APPROVAL_THEME = { waiting: 'amber', approved: 'green', returned: 'amber', disputed: 'red' }
export const approvalState = (status) => APPROVAL_STATE[status] || 'waiting'
export const approvalTheme = (state) => APPROVAL_THEME[state] || 'gray'

// How one card is drawn for this reader. Simple mode never shows a record number, and draws an item that Simple mode
// does not offer as the neutral card (rule 13, D-152, D-154). A client's state is worded by the portal table (D-166).
// `neutral` is the card that names nothing.
export function cardView(item, { mode = 'simple', portal = false } = {}) {
  if (!item) return { neutral: true }
  const advanced = mode === 'advanced'
  if (!advanced && hiddenInSimple(item)) return { neutral: true }
  const approval = item.doctype === 'Approval Request'
  const kept = approval ? approvalState(item.state) : ''
  const state = approval ? chatWord(`approval.state.${kept}`, { mode, portal })
    : item.state ? (portal ? portalStateLabel(item.state, mode) : stateLabel(item.state, mode)) : ''
  return {
    neutral: false,
    key: ICONS[item.type] ? item.type : 'file',
    icon: ICONS[item.type] || ICONS.file,
    title: item.title || '',
    state,
    stateRaw: item.state || '',
    theme: approval ? approvalTheme(kept) : '',
    number: (advanced || approval) && item.number ? item.number : '', // an approval is known by its reference (VO-0007) in every mode
    size: item.type === 'file' && item.size ? formatSize(item.size) : '',
    file: item.doctype === 'File',
  }
}

// Where Open goes (design §3.5, L-9). A file opens at its address. Staff open the record's page in the workspace; a
// client opens the portal's board page for a board, or the portal tab of the item's section. The portal has no
// highlight for an item, so a client lands on the tab. Answers { href } or { to } (a router location), or null when this
// viewer has nowhere to go (the staff preview of the portal).
export function openTarget(item, { viewer, project }) {
  if (!item || viewer === 'preview') return null
  if (item.doctype === 'File') return item.url ? { href: item.url } : null
  // P3-79 (§3.14): a client's chip and card open the approval sheet. P3-80 (O3): a staff member's open the request page.
  if (item.doctype === 'Approval Request') {
    if (!project || !item.name) return null
    return viewer === 'client' ? { to: { name: 'portal-project', params: { project }, query: approvalLink(item.name).query } } : { to: requestRoute(project, item.name) }
  }
  if (viewer === 'client') {
    if (item.doctype === 'Whiteboard') return { to: { name: 'portal-board', params: { project, board: item.name } } }
    return item.section ? { to: { name: 'portal-project', params: { project }, query: { tab: item.section } } } : null
  }
  return item.section ? { to: { name: 'section', params: { project, section: item.section, item: item.name } } } : null
}

// The people-and-things in a picker list, in groups: the approvals (the canvas draws them first), files and boards (all
// that Simple mode offers), then the project's records (Advanced mode). Answers [{ key, items }].
export function groupItems(items) {
  const approvals = items.filter((i) => i.type === 'approval')
  const first = items.filter((i) => i.simple !== false && (i.type === 'file' || i.type === 'board'))
  const rest = items.filter((i) => !first.includes(i) && !approvals.includes(i))
  return [{ key: 'approvals', items: approvals }, { key: 'files', items: first }, { key: 'records', items: rest }].filter((g) => g.items.length)
}
