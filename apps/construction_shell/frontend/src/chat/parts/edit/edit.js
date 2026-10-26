// Edit and remove (P3-68, design §3.8), as pure functions. A stored message holds tokens (@[u:1], #[r:1]) and the chips
// the server read for this reader. The box shows labels and keeps a mark for each one (tokens.js); `editDraft` is the
// inverse of tokens.build, and `editPayload` is build again, so a person or an item the author does not touch comes back
// as the same token and the same part, and an edit never loses a chip. The server refuses an edit that names a token its
// parts do not carry, so the mentions and refs parts are always resent.
import { addMark, build, mentionMark, parse, partsOf, refMark } from '../../tokens.js'

// { text, marks } for the box: the message's own words with a label for each chip. `w` is the reader's chat words: a
// token that has no chip (an item the reader may not read, a person who left) is worded, never left as a token.
export function editDraft(message, w) {
  const files = message?.parts?.attachments || []
  if (files.length === 1 && files[0].file_name === message.text) return { text: '', marks: [] } // a file's name is not a caption
  let marks = []
  let text = ''
  for (const p of parse(message?.text || '', { mentions: message?.parts?.mentions, refs: message?.parts?.refs })) {
    if (p.type === 'text') text += p.text
    else if (p.type === 'mention') text += label(p.item && p.item.user ? mentionMark(p.item) : null, '@' + w('mentions.someone'))
    else text += label(p.item ? refMark(p.item) : null, '#' + w('refs.unavailable'))
  }
  return { text, marks }

  function label(mark, neutral) {
    if (!mark) return neutral
    const added = addMark(marks, mark)
    marks = added.marks
    return added.label
  }
}

// What the edit sends for the box's text and marks: the text with its tokens, and the parts those tokens number.
export function editPayload(text, marks) {
  const built = build(text, marks)
  return { text: built.text, parts: partsOf(built.mentions, built.refs) }
}

// Whether the text or its chips changed: Save is offered only then.
export function changed(draft, text, marks) {
  return text !== draft.text || JSON.stringify(marks.map((m) => m.label)) !== JSON.stringify(draft.marks.map((m) => m.label))
}

// The earlier texts of an edited message, newest first, for the history dialog: tokens read as words, never raw.
// `history` is the server's { versions: [{ text, written_on, edited_on, edited_by: { name } }] } (oldest first).
export function versionsOf(history, plain) {
  return (history?.versions || []).map((v) => ({
    text: plain(v.text || ''),
    written: v.written_on || '',
    replaced: v.edited_on || '',
    by: v.edited_by?.name || '',
  })).reverse()
}
