<template>
  <div v-if="state.open" class="absolute bottom-full left-0 z-40 mb-2 w-[300px] max-w-[calc(100vw-24px)] rounded-6 border border-outline-gray-2 bg-surface-base p-1.5 shadow-lg max-md:w-[min(340px,calc(100vw-24px))]"
    :data-testid="`${prefix}suggest`" :data-char="state.char" @pointerdown.prevent>
    <div v-if="groups.length" :id="listId" role="listbox" :aria-label="label" class="max-h-[min(320px,50vh)] overflow-y-auto">
      <div v-for="(g, gi) in groups" :key="g.key" role="group" :aria-label="g.heading" :class="gi ? 'mt-1 border-t border-outline-gray-1 pt-1' : ''">
        <div class="px-2 pb-1 pt-1.5 text-xs text-ink-gray-7" aria-hidden="true">{{ g.heading }}</div>
        <button v-for="o in g.options" :id="`${listId}-${o.index}`" :key="o.item.key" type="button" role="option" :aria-selected="o.index === state.active ? 'true' : 'false'"
          class="flex min-h-9 w-full cursor-pointer items-center gap-2.5 rounded-4 border-0 px-2 py-1 text-left max-md:min-h-12"
          :class="o.index === state.active ? 'bg-surface-gray-2' : 'bg-transparent hover:bg-surface-gray-2'"
          :data-testid="`${prefix}suggest-option`" :data-key="o.item.key" @mousemove="state.active = o.index" @click="emit('pick', o.item)">
          <Avatar v-if="o.item.kind === 'mention'" :image="o.item.image || undefined" :label="o.item.name" size="lg" :theme="themeOf(o.item.user)" />
          <span v-else class="grid size-6 flex-none place-items-center text-ink-gray-7" aria-hidden="true"><span :class="[iconOf(o.item), 'size-4']" /></span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-base text-ink-gray-9">{{ o.item.kind === 'mention' ? o.item.name : o.item.title }}</span>
            <span v-if="o.item.kind !== 'mention'" class="block truncate text-xs text-ink-gray-7">{{ subOf(o.item) }}</span>
          </span>
        </button>
      </div>
    </div>
    <p v-else class="m-0 px-2 py-1.5 text-sm text-ink-gray-7" role="status" :data-testid="`${prefix}suggest-empty`">{{ state.loading ? w(`${scope}.searching`) : w(`${scope}.none`) }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Avatar } from 'frappe-ui'
import { themeOf } from '../frame.js'
import { useMode } from '../mode.js'
import { ICONS, approvalState } from './parts/refs/cards.js'
import { portalStateLabel, stateLabel } from '../words.js'
import { wordsFor } from './words.js'

// The "@" list and the "#" picker (P3-66; canvas "The composer": frames 3 and 4): a list above the box in groups, the team
// then the client's people, or files and boards then the project's records. The box holds focus and the keys; this only
// draws the options and reports a click. On a phone each row is 48 px.
const props = defineProps({ state: { type: Object, required: true }, listId: { type: String, required: true }, portal: Boolean, prefix: { type: String, default: '' } })
const emit = defineEmits(['pick'])
const mode = useMode()
const w = wordsFor(mode, props.portal)
const scope = computed(() => (props.state.char === '@' ? 'mentions' : 'refs'))
const label = computed(() => w(props.state.char === '@' ? 'mentions.list' : 'refs.tag'))
const groups = computed(() => {
  const out = []
  props.state.items.forEach((item, index) => {
    let g = out.find((x) => x.key === item.group)
    if (!g) out.push((g = { key: item.group, heading: w(HEADING[item.group] || 'refs.group_records'), options: [] }))
    g.options.push({ item, index })
  })
  return out
})
const HEADING = { team: 'mentions.role_team', client: 'mentions.role_client', files: 'refs.group_files', records: 'refs.group_records', approvals: 'refs.group_approvals' }
const iconOf = (item) => ICONS[item.type] || ICONS.file
// A person's group is the heading above them; an item says what it is, its state and (Advanced mode) its number.
function subOf(item) {
  if (item.type === 'approval') return [item.number, w(`approval.state.${approvalState(item.state)}`)].filter(Boolean).join(' · ') // known by its reference in every mode
  const state = item.state ? (props.portal ? portalStateLabel(item.state, mode.value) : stateLabel(item.state, mode.value)) : ''
  return [w(`refs.${item.type}`), state, mode.value === 'advanced' ? item.number : ''].filter(Boolean).join(' · ')
}
</script>
