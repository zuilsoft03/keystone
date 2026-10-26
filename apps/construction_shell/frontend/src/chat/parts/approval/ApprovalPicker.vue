<template>
  <Dialog v-model:open="shown" size="xl" :title="w('approval.picker_title')">
    <div class="flex flex-col gap-2.5" :data-testid="`${prefix}approval-picker`">
      <p class="m-0 text-xs text-ink-gray-7">{{ w(thread?.audience === 'Client' ? 'approval.picker_client' : 'approval.picker_team') }}</p>
      <label class="sr-only" :for="`${prefix}approval-search`">{{ w('approval.search') }}</label>
      <input :id="`${prefix}approval-search`" v-model="search" type="search" class="form-input h-8 min-w-0 text-base max-md:h-12" :placeholder="w('approval.search')"
        :data-testid="`${prefix}approval-search`" />
      <p v-if="error" class="m-0 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert">{{ w('approval.error') }}</p>
      <p v-else-if="loading && !items.length" class="m-0 py-3 text-sm text-ink-gray-7" role="status">{{ w('approval.loading') }}</p>
      <p v-else-if="!items.length" class="m-0 py-3 text-sm text-ink-gray-7" role="status" :data-testid="`${prefix}approval-none`">{{ w('approval.none') }}</p>
      <ul class="m-0 flex max-h-[360px] list-none flex-col gap-1 overflow-y-auto p-0" role="listbox" :aria-label="w('approval.picker_title')">
        <li v-for="i in items" :key="i.name">
          <button type="button" role="option" :aria-selected="chosen?.name === i.name ? 'true' : 'false'"
            class="flex min-h-12 w-full cursor-pointer items-center gap-2.5 rounded-5 border bg-transparent px-3 py-2 text-left hover:bg-surface-gray-2"
            :class="chosen?.name === i.name ? 'border-outline-blue-6 bg-surface-blue-1' : 'border-outline-gray-2'" :data-testid="`${prefix}approval-option`" @click="chosen = i">
            <span class="min-w-0 flex-1">
              <span class="block truncate text-base font-medium text-ink-gray-9">{{ i.title }}</span>
              <span class="block truncate text-xs text-ink-gray-7">{{ [i.number, stateOf(i)].filter(Boolean).join(' · ') }}</span>
            </span>
          </button>
        </li>
      </ul>
    </div>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="w('core.cancel')" class="max-md:!h-12" @click="shown = false" />
        <Button variant="solid" theme="blue" class="max-md:!h-12" :label="w('approval.attach_go')" :disabled="!chosen" :data-testid="`${prefix}approval-attach`" @click="attach" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, inject, onUnmounted, ref, watch } from 'vue'
import { Button, Dialog } from 'frappe-ui'
import { useMode } from '../../../mode.js'
import { HOST_KEY } from '../../host.js'
import { wordsFor } from '../../words.js'
import { approvalState } from '../refs/cards.js'
import { loadApprovals } from './picker.js'

// The picker of "Attach an approval…" (canvas ApprovalChat 1, 5; phone): the project's requests this reader may tag, with a
// search. Choosing one hands the card back (`picked`); the box puts its tag in the text and the send posts the live card
// under the message through the refs part (never a copy). Nothing here answers anything.
const props = defineProps({ open: Boolean, thread: { type: Object, default: null }, portal: Boolean, prefix: { type: String, default: '' } })
const emit = defineEmits(['update:open', 'picked'])
const host = inject(HOST_KEY)
const w = wordsFor(useMode(), props.portal)
const shown = computed({ get: () => props.open, set: (v) => emit('update:open', v) })
const items = ref([])
const search = ref('')
const chosen = ref(null)
const loading = ref(false)
const error = ref(false)
const stateOf = (i) => w(`approval.state.${approvalState(i.state)}`)

let timer = null
let seq = 0
async function load() {
  const mine = ++seq
  loading.value = true
  error.value = false
  try {
    const found = await loadApprovals(host, props.thread?.name, search.value)
    if (mine === seq) items.value = found
  } catch {
    if (mine === seq) {
      items.value = []
      error.value = true
    }
  } finally {
    if (mine === seq) loading.value = false
  }
}

function attach() {
  emit('picked', chosen.value)
  shown.value = false
}

watch(() => props.open, (open) => {
  if (!open) return
  search.value = ''
  chosen.value = null
  items.value = []
  load()
})
watch(search, () => {
  clearTimeout(timer)
  timer = setTimeout(load, 200)
})
onUnmounted(() => clearTimeout(timer))
</script>
