// The mentions part (P3-66, design §3.4): the chips are drawn inside the message's text (MessageText.vue), so the part
// has no block of its own. The registry still lists it, so a message that carries it is a message the screen knows.
export default {
  name: 'MentionsView',
  props: { items: { type: [Array, Object], default: () => [] }, message: Object, portal: Boolean, prefix: { type: String, default: '' } },
  render: () => null,
}
