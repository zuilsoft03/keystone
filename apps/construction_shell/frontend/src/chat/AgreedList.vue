<template>
  <section v-if="items.length" class="mx-4 mt-2 rounded-5 border border-outline-gray-2 bg-surface-green-2" :aria-label="w('core.agreed_list')" :data-testid="`${prefix}agreed-list`">
    <button type="button" class="flex min-h-9 w-full cursor-pointer items-center gap-2 rounded-5 border-0 bg-transparent px-3 py-1.5 text-left text-sm text-ink-green-8 max-md:min-h-12"
      :aria-expanded="open ? 'true' : 'false'" :data-testid="`${prefix}agreed-toggle`" @click="open = !open">
      <span class="lucide-badge-check size-4 flex-none" aria-hidden="true" />
      <strong class="flex-none font-semibold">{{ w('core.agreed_count', { count: items.length }) }}</strong>
      <span v-if="!open" class="min-w-0 flex-1 truncate text-ink-gray-8">{{ line(items[0]) }}</span>
      <span class="ml-auto size-4 flex-none" :class="open ? 'lucide-chevron-up' : 'lucide-chevron-down'" aria-hidden="true" />
    </button>
    <ul v-if="open" class="m-0 flex max-h-60 list-none flex-col gap-1 overflow-y-auto border-t border-outline-gray-2 p-2">
      <li v-for="m in items" :key="m.name" class="flex items-start gap-2 rounded-4 bg-surface-base px-2.5 py-1.5" :data-testid="`${prefix}agreed-item`">
        <div class="min-w-0 flex-1">
          <p class="m-0 text-xs text-ink-gray-7">{{ m.author.name }} · {{ stamp(m.creation) }}</p>
          <p class="m-0 whitespace-pre-wrap break-words text-base text-ink-gray-9">{{ line(m) }}</p>
        </div>
        <Button size="sm" variant="ghost" class="max-md:!h-12" :label="w('core.agreed_go')" :data-testid="`${prefix}agreed-go`" @click="emit('go', m.name)" />
      </li>
    </ul>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { Button } from 'frappe-ui'
import { useMode } from '../mode.js'
import { stampTime } from '../sections/util.js'
import { readable } from './tokens.js'
import { wordsFor } from './words.js'

// The Agreed list at the top of a Client conversation (design §3.8, D-373, QH-O): the messages the team marked Agreed,
// newest first. It is the team's note that a point is settled, never an approval by the client. Closed, it shows the count
// and the newest line; open, each message with "Show in conversation". The tokens in a line read as words.
const props = defineProps({ items: { type: Array, default: () => [] }, portal: Boolean, prefix: { type: String, default: '' } })
const emit = defineEmits(['go'])
const w = wordsFor(useMode(), props.portal)
const open = ref(false)
const stamp = (value) => stampTime(value)
const line = (m) => readable(m.text, m.parts, w) || w(`kind.${m.kind}`)
</script>
