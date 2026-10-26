<template>
  <BoardView v-if="item" :key="item" :name="item" :project="project" />
  <div v-else class="flex flex-col gap-3.5 px-6 py-5" data-testid="section-page">
    <PageHead crumb="Workspace / Canvas" title="Canvas" :meta="frame?.project.project_name || project">
      <Button variant="solid" theme="blue" size="md" icon-left="lucide-plus" label="New board" data-testid="new-board" @click="creating = !creating" />
    </PageHead>
    <form v-if="creating" class="cw-card flex flex-wrap items-end gap-3 p-4" @submit.prevent="create">
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Title
        <input v-model="title" required maxlength="140" class="form-input w-72" data-testid="board-title" />
      </label>
      <label class="flex items-center gap-2 text-sm text-ink-gray-8"><input v-model="shared" type="checkbox" class="form-checkbox rounded-1" /> Show to the client</label>
      <Button type="submit" variant="solid" theme="blue" label="Create" data-testid="create-board" />
    </form>
    <p v-if="error" class="text-ink-red-7" role="alert">{{ error }}</p>
    <div class="grid gap-3" style="grid-template-columns: repeat(auto-fill, minmax(260px, 1fr))">
      <router-link v-for="b in boards" :key="b.name" :to="{ name: 'section', params: { project, section: 'whiteboards', item: b.name } }"
        class="cw-card flex flex-col gap-1.5 px-4 py-3.5 text-ink-gray-9 no-underline hover:border-outline-gray-3" data-testid="board-card">
        <!-- P3-75: the board's picture, sent by the editor when the board was last saved; nothing when there is none -->
        <span v-if="thumbOf(b) === 'image'" class="block h-[110px] overflow-hidden rounded-4 bg-surface-gray-2" data-testid="board-thumb-image">
          <img :src="book.src(b.name)" :alt="b.title" class="size-full bg-surface-base object-contain" loading="lazy" @error="lost.add(b.name)" />
        </span>
        <span class="flex items-center gap-2"><span class="lucide-pen-line size-4 text-ink-gray-6" aria-hidden="true" /><span class="truncate text-base font-semibold">{{ b.title }}</span></span>
        <span class="flex flex-wrap items-center gap-1.5 text-xs text-ink-gray-7">Version {{ b.version || 0 }}<Badge v-if="b.client_visible" size="sm" theme="blue" label="Shared with client" /></span>
      </router-link>
    </div>
    <p v-if="!boards.length" class="text-ink-gray-7">No board yet.</p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import BoardView from '../components/BoardView.vue'
import PageHead from '../components/PageHead.vue'
import { call } from '../api.js'
import { PreviewBook } from '../previews.js'

const props = defineProps({ frame: Object, project: String, section: String })
const route = useRoute()
const router = useRouter()
const item = computed(() => route.params.item)
const boards = ref([])
const creating = ref(false)
const title = ref('')
const shared = ref(false)
const error = ref('')
// P3-75: the boards' pictures, read in one batch per list (previews.api.states); a board's version is its stamp, so a
// new save is asked for again.
// A board's picture comes from the editor when it is saved, so a board with none is never waited for: the server answers
// "pending" for it, which is drawn as no picture, and nothing is asked again.
const book = new PreviewBook('board', { again: [] })
const lost = reactive(new Set())
const thumbOf = (b) => {
  const entry = book.of(b.name)
  return entry?.state === 'ready' && !lost.has(b.name) ? 'image' : 'none'
}
onBeforeUnmount(() => book.stop())

async function load() {
  try {
    boards.value = await call('frappe.client.get_list', {
      doctype: 'Whiteboard', filters: { project: props.project }, fields: ['name', 'title', 'version', 'client_visible'],
      order_by: 'modified desc', limit_page_length: 500,
    })
    book.want(boards.value.map((b) => ({ id: b.name, stamp: String(b.version || 0) })))
  } catch (e) {
    error.value = e.message
  }
}

async function create() {
  try {
    const b = await call('frappe.client.insert', {
      doc: { doctype: 'Whiteboard', project: props.project, title: title.value, client_visible: shared.value ? 1 : 0 },
    }, { post: true })
    creating.value = false
    title.value = ''
    router.push({ name: 'section', params: { project: props.project, section: 'whiteboards', item: b.name } })
  } catch (e) {
    error.value = e.message
  }
}

watch(() => [props.project, item.value], () => !item.value && load(), { immediate: true })
</script>
