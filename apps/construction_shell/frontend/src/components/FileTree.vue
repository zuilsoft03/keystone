<template>
  <!-- P3-41 (D-292): the design's folder pane: the New menu, the project's folders as a tree that opens and closes,
       each with its files' count, the shortcuts Shared with client and Recent, and the project's total. -->
  <nav aria-label="Project folders" class="flex min-h-0 flex-col gap-px" data-testid="file-tree">
    <div class="relative mb-2.5">
      <button ref="newButton" type="button" aria-haspopup="menu" :aria-expanded="menuOpen" class="flex h-[46px] w-[165px] items-center gap-2 rounded-5 px-3 text-base font-medium text-ink-base hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-60"
        style="background-color: var(--ink-gray-8)" :disabled="!canAdd" data-testid="files-new" @click="menuOpen = !menuOpen">
        <span class="lucide-plus size-4" aria-hidden="true" />New
        <span class="lucide-chevron-down ml-auto size-4" aria-hidden="true" />
      </button>
      <div v-if="menuOpen" role="menu" aria-label="New" class="absolute left-0 top-[calc(100%+6px)] z-20 w-[220px] rounded-6 border border-outline-gray-2 bg-surface-base p-1.5 shadow-lg" data-testid="files-new-menu">
        <button type="button" role="menuitem" class="flex h-8 w-full items-center gap-2.5 rounded-4 px-2 text-left text-base text-ink-gray-9 hover:bg-surface-gray-2 disabled:cursor-not-allowed disabled:text-ink-gray-4"
          :disabled="!canUpload" data-testid="files-new-upload" @click="choose('upload')">
          <span class="lucide-upload size-4 text-ink-gray-7" aria-hidden="true" />Upload files
        </button>
        <button type="button" role="menuitem" class="flex h-8 w-full items-center gap-2.5 rounded-4 px-2 text-left text-base text-ink-gray-9 hover:bg-surface-gray-2 disabled:cursor-not-allowed disabled:text-ink-gray-4"
          :disabled="!canFolder" data-testid="files-new-folder" @click="choose('folder')">
          <span class="lucide-folder-plus size-4 text-ink-gray-7" aria-hidden="true" />New folder
        </button>
        <p v-if="!canUpload" class="m-0 px-2 pb-1 pt-1.5 text-xs text-ink-gray-7">{{ uploadHint }}</p>
      </div>
    </div>

    <button v-for="f in rows" :key="f.folder" type="button"
      class="flex h-7 w-full items-center gap-2 rounded-4 pr-2 text-left text-sm"
      :class="f.folder === current ? 'bg-surface-elevation-3 font-medium text-ink-gray-9 shadow-sm' : 'text-ink-gray-8 hover:bg-surface-gray-2'"
      :style="{ paddingLeft: `${8 + f.depth * 16}px` }" :aria-current="f.folder === current ? 'page' : undefined"
      :aria-expanded="f.hasChildren && f.path ? f.open : undefined" data-testid="folder" :data-path="f.path" @click="$emit('pick', f.folder)">
      <span v-if="f.path" class="grid size-3 flex-none place-items-center" :class="f.hasChildren ? '' : 'opacity-0'" aria-hidden="true"
        @click.stop="f.hasChildren && $emit('toggle', f.path)">
        <span class="lucide-chevron-right size-3 transition-transform" :class="f.open ? 'rotate-90' : ''" />
      </span>
      <span :class="[f.path ? 'lucide-folder' : 'lucide-hard-drive', 'size-4 flex-none text-ink-gray-7']" aria-hidden="true" />
      <span class="min-w-0 flex-1 truncate">{{ f.label }}</span>
      <Badge v-if="f.client_visible && f.path === '06_Client'" label="Client" theme="blue" size="sm" />
      <span v-if="f.path === '' ? total : f.count" class="text-xs text-ink-gray-7" data-testid="folder-count">{{ f.path === '' ? total : f.count }}</span>
    </button>

    <div class="mx-2 my-2 h-px bg-outline-gray-2" />
    <button v-for="v in VIEWS" :key="v.id" type="button" class="flex h-7 w-full items-center gap-2 rounded-4 pl-7 pr-2 text-left text-sm"
      :class="view === v.id ? 'bg-surface-elevation-3 font-medium text-ink-gray-9 shadow-sm' : 'text-ink-gray-8 hover:bg-surface-gray-2'"
      :aria-current="view === v.id ? 'page' : undefined" :data-testid="`view-${v.id}`" @click="$emit('view', v.id)">
      <span :class="[v.icon, 'size-4 text-ink-gray-7']" aria-hidden="true" />{{ v.label }}
    </button>
    <div class="mt-auto p-3 text-xs text-ink-gray-7" data-testid="files-total">{{ total }} {{ total === 1 ? 'file' : 'files' }} in this project</div>
  </nav>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Badge } from 'frappe-ui'

defineProps({
  rows: { type: Array, default: () => [] },
  current: { type: String, default: '' },
  view: { type: String, default: '' },
  total: { type: Number, default: 0 },
  canAdd: { type: Boolean, default: true },
  canUpload: { type: Boolean, default: true },
  canFolder: { type: Boolean, default: true },
  uploadHint: { type: String, default: '' },
})
const emit = defineEmits(['pick', 'toggle', 'view', 'upload', 'folder'])
const VIEWS = [
  { id: 'shared', label: 'Shared with client', icon: 'lucide-users' },
  { id: 'recent', label: 'Recent', icon: 'lucide-clock' },
]
const menuOpen = ref(false)
const newButton = ref(null)

function choose(what) {
  menuOpen.value = false
  emit(what)
}

function away(e) {
  if (menuOpen.value && !e.target.closest('[data-testid="files-new-menu"]') && e.target !== newButton.value && !newButton.value?.contains(e.target)) menuOpen.value = false
}
onMounted(() => document.addEventListener('click', away))
onBeforeUnmount(() => document.removeEventListener('click', away))
</script>
