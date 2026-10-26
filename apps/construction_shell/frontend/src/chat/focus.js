// Focus back on a thread's root (P3-64, the brief's accessibility rules): when a thread closes, the focus returns to
// the reply line under its root message. On a phone the room is drawn again first and reads its messages, so the
// line is looked for over a short while.
export function focusReplyLine(root, { tries = 40, wait = 50 } = {}) {
  if (!root || typeof document === 'undefined') return
  const look = (left) => {
    const line = document.querySelector(`[data-reply-for="${CSS.escape(root)}"]`)
    if (line) {
      line.scrollIntoView({ block: 'center' })
      line.focus()
    } else if (left > 0) setTimeout(() => look(left - 1), wait)
  }
  look(tries)
}
