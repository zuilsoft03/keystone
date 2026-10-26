// The chat's three screen registries (P3-64, design §13.2 F2…F4), each a static list (rule 14: no loader). Their keys
// match the server's registries one for one: construction_shell/tests/chat_registry.json holds both sides, and
// tests/chat.test.js and test_chat_registry.py check it in both directions.
import { defineAsyncComponent } from 'vue'

// F2: a view per registered part key. The core MessageItem draws the frame; a part draws only its own items.
export const PART_VIEWS = {
  attachments: defineAsyncComponent(() => import('./parts/attachments/AttachmentCard.vue')),
  pointer: defineAsyncComponent(() => import('./parts/PointerCard.vue')),
  mentions: defineAsyncComponent(() => import('./parts/mentions/MentionsView.js')), // P3-66: the chips live in the text (MessageText.vue)
  refs: defineAsyncComponent(() => import('./parts/refs/RefCards.vue')), // P3-66: a card under the message for each tagged item
  voice: defineAsyncComponent(() => import('./parts/voice/VoiceCard.vue')), // P3-67: the player of a voice note
  polls: defineAsyncComponent(() => import('./parts/polls/PollCard.vue')), // P3-68: the poll card (vote, results, close)
  reactions: defineAsyncComponent(() => import('./parts/reactions/ReactionBar.vue')), // P3-68: the pills under a message
  file_requests: defineAsyncComponent(() => import('./parts/file_requests/RequestCard.vue')), // P3-71: the checklist of files asked for
  approval: defineAsyncComponent(() => import('./parts/approval/ApprovalCard.vue')), // P3-78: the live card of a client approval (no button: a mention never approves)
}

// F3: what the message box offers. An action shows only when the view can write, the thread's capabilities include
// its part and its env allows it. Attach stages files through the host's upload, and the send claims them (P3-65).
export const COMPOSER_ACTIONS = [
  { id: 'attach', part: 'attachments', slot: 'tools', word: 'attachments.attach', order: 10,
    component: defineAsyncComponent(() => import('./actions/AttachAction.vue')),
    env: (host) => typeof host.upload === 'function' },
  // P3-66: Mention someone and Tag a file or record open the box's @ list and # picker (the Composer owns the list).
  { id: 'mention', part: 'mentions', slot: 'tools', word: 'mentions.mention', order: 20,
    component: defineAsyncComponent(() => import('./actions/MentionAction.vue')) },
  { id: 'tag', part: 'refs', slot: 'tools', word: 'refs.tag', order: 30,
    component: defineAsyncComponent(() => import('./actions/TagAction.vue')) },
  // P3-67: the microphone. It shows wherever the thread offers voice and the host can upload; on a page that cannot record
  // (plain http, no MediaRecorder) the action itself says so in a plain note instead of the button (design §3.6).
  { id: 'voice', part: 'voice', slot: 'tools', word: 'voice.mic', order: 50,
    component: defineAsyncComponent(() => import('./actions/VoiceAction.vue')),
    env: (host) => typeof host.upload === 'function' },
  // P3-68: Make a poll (staff; the thread offers the polls part to them only). The builder replaces the box while open.
  { id: 'poll', part: 'polls', slot: 'tools', word: 'polls.tool', order: 60,
    component: defineAsyncComponent(() => import('./parts/polls/PollAction.vue')),
    env: (host) => typeof host.send === 'function' },
  // P3-68: React sits in the message's toolbar, not the box (slot 'message'): the thread's `reactions` capability turns it on
  // and the viewer's set decides what it offers (parts/reactions/summary.js). It is listed here so the part is registered once.
  { id: 'react', part: 'reactions', slot: 'message', word: 'reactions.react', order: 70 },
  // P3-71: Request files (staff; the thread offers the part to staff in an open thread). Its builder is a dialog the button opens.
  { id: 'request', part: 'file_requests', slot: 'tools', word: 'file_requests.tool', order: 65,
    component: defineAsyncComponent(() => import('./parts/file_requests/RequestAction.vue')),
    env: (host) => typeof host.send === 'function' },
  // P3-79 (§3.14, N10): "Attach an approval…" is an item of the attach menu (slot 'attach'; AttachAction lists it), not a button
  // of its own. It sends a # tag through the refs part, so the thread offers it where it offers refs. Its picker is the dialog.
  { id: 'approval', part: 'refs', slot: 'attach', word: 'approval.attach', hint: 'approval.attach_hint', icon: 'lucide-square-check', order: 15,
    component: defineAsyncComponent(() => import('./parts/approval/ApprovalPicker.vue')),
    env: (host) => typeof host.read === 'function' && host.approvals !== false },
]

// F4: what a message offers. Shown only when the view can write, the message is not removed and its `can` names it.
export const MESSAGE_ACTIONS = [
  { id: 'pin', word: (m) => (m.pinned ? 'core.unpin' : 'core.pin'), icon: 'lucide-pin', order: 10,
    run: (host, m) => host.write('set_pinned', { message: m.name, pinned: m.pinned ? 0 : 1 }) },
  // P3-68: the author's and the manager's actions, in the More menu (`menu`), listed in the order the server's `can` names them
  // (the menu's own order is `order`). Edit, Remove and History open a screen of their
  // own (`open`); Agreed is one call. `can` (the server's) says who gets which, so the screen never decides it.
  { id: 'edit', word: 'core.edit', icon: 'lucide-pencil', order: 20, menu: true, open: 'edit' },
  { id: 'remove', word: 'core.remove', icon: 'lucide-trash-2', order: 50, menu: true, open: 'remove' },
  { id: 'agree', word: (m) => (m.agreed ? 'core.unagree' : 'core.agree'), icon: 'lucide-badge-check', order: 40, menu: true,
    run: (host, m) => host.agree(m.name, !m.agreed) },
  { id: 'history', word: 'core.history', icon: 'lucide-history', order: 30, menu: true, open: 'history' },
]

// Discuss Message.kind's options (the server's closed Select), each with a chat.kind.* word.
export const KINDS = ['Text', 'Files', 'Voice', 'Poll', 'System']

export function composerActions(host, thread) {
  if (!host || host.readOnly || !thread) return []
  const capable = thread.capabilities || []
  return COMPOSER_ACTIONS.filter((a) => a.slot === 'tools' && capable.includes(a.part) && (!a.env || a.env(host)))
    .sort((a, b) => a.order - b.order)
}

// P3-79: the actions the attach menu adds to its own choices (Attach an approval…), in the thread's capabilities.
export function attachActions(host, thread) {
  if (!host || host.readOnly || !thread) return []
  const capable = thread.capabilities || []
  return COMPOSER_ACTIONS.filter((a) => a.slot === 'attach' && capable.includes(a.part) && (!a.env || a.env(host))).sort((a, b) => a.order - b.order)
}

export function messageActions(host, message) {
  if (!host || host.readOnly || !message || message.removed) return []
  const can = message.can || []
  return MESSAGE_ACTIONS.filter((a) => can.includes(a.id)).sort((a, b) => a.order - b.order)
}

// P3-68: whether the thread offers reactions to this reader (the message toolbar's React button).
// A removed message and a System card (a room mirror) take none: the server refuses any action on them.
export function reactionsOffered(host, thread, message) {
  if (message && (message.removed || message.kind === 'System')) return false
  return Boolean(host && !host.readOnly && thread && (thread.capabilities || []).includes('reactions'))
}

export function runAction(host, action, message) {
  return action.run ? action.run(host, message) : host.write(action.op, { message: message.name })
}

// The parts of a message the screen can draw, in the registry's order, and the keys it cannot (a neutral line each).
export function partsOf(message) {
  const parts = message?.parts || {}
  const known = Object.keys(PART_VIEWS).filter((k) => parts[k] != null)
  const unknown = Object.keys(parts).filter((k) => !(k in PART_VIEWS))
  return { known, unknown }
}
