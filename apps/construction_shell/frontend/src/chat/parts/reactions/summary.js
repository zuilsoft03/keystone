// The reactions part's view (P3-68, design §3.8), as plain functions. The server keeps four reactions and says, per
// message, [{ key, count, people, mine }] in its fixed order. Staff and partners may use all four; a client only Noted and
// Question, so no client reaction reads as an approval (L-6, PD-11). The server refuses any other, so this only decides what
// to offer.
export const ORDER = ['noted', 'done', 'looking', 'question']
export const CLIENT_SET = ['noted', 'question']
export const GLYPHS = { noted: '👍', done: '✅', looking: '👀', question: '❓' }

// The reactions a reader may add: by the host's viewer. The staff preview is read-only and adds none.
export function offered(host) {
  if (!host || host.readOnly || !host.act) return []
  return host.viewer === 'client' ? CLIENT_SET : ORDER
}

// The pills under a message. `w` is the reader's chat words. `names` is who reacted, as the server named them (people the
// reader may see, L-17); `label` is the whole sentence a screen reader says for the pill.
export function pills(items, w) {
  return (Array.isArray(items) ? items : [])
    .filter((r) => r && ORDER.includes(r.key) && Number(r.count) > 0)
    .map((r) => {
      const names = (r.people || []).map((p) => p.name).filter(Boolean)
      const name = w(`reactions.${r.key}`)
      const count = Number(r.count)
      const who = names.length ? w('reactions.who', { names: names.join(', ') }) : ''
      const label = [w(count === 1 ? 'reactions.pill_one' : 'reactions.pill', { name, count }), who, r.mine ? w('reactions.you_reacted') : ''].filter(Boolean).join('. ')
      return { key: r.key, glyph: GLYPHS[r.key], count, mine: Boolean(r.mine), name, names, label }
    })
}

// The picker's entries: one per reaction the reader may add. One they already made reads "Take back …".
export function choices(items, set, w) {
  const mine = new Set((Array.isArray(items) ? items : []).filter((r) => r && r.mine).map((r) => r.key))
  return set.map((key) => ({
    id: key, // a menu entry's id
    key,
    on: mine.has(key),
    glyph: GLYPHS[key],
    label: mine.has(key) ? w('reactions.take_back', { name: w(`reactions.${key}`) }) : w(`reactions.${key}`),
  }))
}

// The polite line said once after the reader's own change: "Reacted: Noted" or "Took back: Noted".
export function said(key, on, w) {
  return w(on ? 'reactions.said_on' : 'reactions.said_off', { name: w(`reactions.${key}`) })
}
