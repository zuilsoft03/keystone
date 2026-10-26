// What a design event draws (P3-69, design §3.9; canvas "Message cards": System events), from the server's item alone:
// { type: 'event', event, record } where `record` is the same card the tags use (P3-66). The line is one sentence with the
// record's title in it, and the title opens the record. The title comes from the tag card (refs/cards.js), so Simple mode
// follows the same rule: a Project Document, a file and a board are named; a record Simple mode does not offer gets the
// event's neutral word and no link. The server leaves out a card the reader cannot read, so an event with no record draws
// nothing at all (rule 2). No number, state, size or revision is drawn: the card is read now, an old line would show today's. Pure.
import { cardView, openTarget } from '../refs/cards.js'

// The three events of discuss.events (pointer.EVENTS): each has a word (chat.pointer.event.<key>), a sentence with the title
// (<key>_titled) and an icon, written out so Tailwind finds it. The canvas draws its own paths; these are the nearest lucide
// icons (D-196).
export const EVENT_ICONS = {
  document_published: 'lucide-file-check',
  file_revised: 'lucide-file-clock',
  board_saved: 'lucide-layout-dashboard',
}

export const isEvent = (item) => Boolean(item) && item.type === 'event'

// A System message whose pointer items are all design events is drawn as its lines alone (canvas "Events in a thread"). A room
// mirror and a root card point at a thread or a message, so they stay messages.
export const eventsOnly = (message) => {
  const items = [].concat(message.parts?.pointer ?? []).filter(Boolean)
  return message.kind === 'System' && items.length > 0 && items.every((i) => isEvent(i) && EVENT_ICONS[i.event] && i.record)
}

const BY = new Set(['board_saved']) // the canvas names who saved a board (<key>_titled_by); the other two events name no one

// How one event is drawn for this reader: { icon, word, title, target }, or null when there is nothing this reader may see.
// `word` is the key of the line (it holds {title}, and {actor} for a board); `title` is '' for the neutral word; `target` is
// where the title goes (null for the staff preview of the portal, and for the neutral word).
export function eventView(item, { mode = 'simple', portal = false, viewer = 'staff', project = '', actor = '' } = {}) {
  if (!isEvent(item) || !item.record || !EVENT_ICONS[item.event]) return null
  const card = cardView(item.record, { mode, portal })
  const title = card.neutral ? '' : card.title
  return {
    icon: EVENT_ICONS[item.event],
    word: `pointer.event.${item.event}${title ? `_titled${actor && BY.has(item.event) ? '_by' : ''}` : ''}`,
    title,
    target: title ? openTarget(item.record, { viewer, project }) : null,
  }
}
