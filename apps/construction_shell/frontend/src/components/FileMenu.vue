<template>
  <div ref="menu" role="menu" :aria-label="`Actions for ${file.file_name}`" class="z-40 w-[230px] rounded-6 border border-outline-gray-2 bg-surface-base p-1.5 shadow-lg"
    data-testid="row-menu-items" @click.stop @dblclick.stop @contextmenu.prevent>
    <button v-if="viewable" type="button" role="menuitem" :class="ITEM" data-testid="menu-open" @click="emit('open')"><span class="lucide-eye size-4 text-ink-gray-7" aria-hidden="true" />Open</button>
    <a :href="href" target="_blank" rel="noopener" role="menuitem" :class="ITEM" data-testid="menu-new-tab" @click="emit('close')"><span class="lucide-external-link size-4 text-ink-gray-7" aria-hidden="true" />{{ viewable ? 'Open in new tab' : 'Open' }}</a>
    <RouterLink v-if="office" :to="officeRoute" role="menuitem" :class="ITEM" data-testid="edit-office"><span class="lucide-pencil size-4 text-ink-gray-7" aria-hidden="true" />{{ file.from_client ? 'View in Office' : 'Edit in Office' }}</RouterLink>
    <a :href="href" download role="menuitem" :class="ITEM" @click="emit('close')"><span class="lucide-download size-4 text-ink-gray-7" aria-hidden="true" />Download</a>
    <button type="button" role="menuitem" :class="ITEM" data-testid="discuss-this" @click="emit('discuss')"><span class="lucide-messages-square size-4 text-ink-gray-7" aria-hidden="true" />{{ w('refs.discuss_this') }}</button>
    <button type="button" role="menuitem" :class="ITEM" :disabled="busy" data-testid="share" @click="emit('share', !file.client_visible)">
      <span :class="[file.client_visible ? 'lucide-user-x' : 'lucide-user-plus', 'size-4 text-ink-gray-7']" aria-hidden="true" />{{ file.client_visible ? 'Stop sharing with the client' : 'Share with the client' }}
    </button>
    <button v-if="movable" type="button" role="menuitem" :class="ITEM" :disabled="busy" data-testid="move" @click="emit('move')"><span class="lucide-folder-input size-4 text-ink-gray-7" aria-hidden="true" />Move…</button>
    <button type="button" role="menuitem" :class="ITEM" data-testid="copy-link" @click="emit('copy')"><span class="lucide-link size-4 text-ink-gray-7" aria-hidden="true" />Copy link</button>
    <div class="my-1 h-px bg-outline-gray-1" />
    <button type="button" role="menuitem" :class="[ITEM, 'text-ink-red-7']" :disabled="busy" data-testid="trash" @click="emit('trash')"><span class="lucide-trash-2 size-4" aria-hidden="true" />Move to the trash</button>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { wordsFor } from '../chat/words.js'
import { OFFICE } from '../loader.js'
import { useMode } from '../mode.js'
import { viewerOf } from '../viewer.js'

// A file's actions (P3-41), opened from its ⋮ button or by right-clicking the row or card (P3-48, D-315).
const props = defineProps({ file: { type: Object, required: true }, href: String, project: String, busy: Boolean, movable: Boolean })
const emit = defineEmits(['open', 'close', 'share', 'move', 'copy', 'trash', 'discuss'])
const ITEM = 'flex h-8 w-full items-center gap-2.5 rounded-4 px-2 text-left text-base text-ink-gray-9 no-underline hover:bg-surface-gray-2 disabled:cursor-not-allowed disabled:text-ink-gray-4'
const w = wordsFor(useMode()) // "Discuss this" (P3-66, design §3.5)
const viewable = computed(() => !!viewerOf(props.file.file_name))
const office = computed(() => OFFICE.test(props.file.file_name))
const menu = ref(null)
onMounted(() => menu.value?.querySelector('[role="menuitem"]')?.focus({ preventScroll: true })) // keyboard users start on its first item; a scroll would close it
const officeRoute = computed(() => ({ name: 'section', params: { project: props.project, section: 'files', item: props.file.name, action: 'edit' } }))
</script>
