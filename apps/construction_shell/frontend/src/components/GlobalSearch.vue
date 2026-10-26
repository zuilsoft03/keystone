<template>
  <!-- P3-08 (D-139, D-243, D-245): the search as Frappe's awesome bar: an input in the top bar, results dropping down
       under it as one types (places to go, then records, then all projects). The server decides every record shown. -->
  <div ref="root" class="relative min-w-0 max-w-[460px] flex-[1_1_260px]" data-testid="search-bar">
    <span class="lucide-search pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-ink-gray-6" aria-hidden="true" />
    <input ref="field" v-model="query" type="search" class="form-input h-8 w-full pl-8 pr-14 text-sm" :placeholder="placeholder"
      role="combobox" aria-autocomplete="list" :aria-expanded="showing" aria-controls="search-list" aria-label="Search"
      data-testid="search-input" @focus="focused = true" @keydown="onKey" />
    <kbd v-if="!query" class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded border border-outline-gray-2 px-1.5 text-xs text-ink-gray-6">Ctrl K</kbd>

    <div v-if="showing" id="search-list" role="listbox" aria-label="Search results"
      class="absolute left-0 right-0 top-[calc(100%+4px)] z-50 max-h-[60vh] overflow-y-auto rounded-6 border border-outline-gray-2 bg-surface-base p-1.5 shadow-lg"
      data-testid="search-panel">
      <button v-for="(row, i) in rows" :key="row.key" type="button" role="option" :aria-selected="i === active"
        class="flex w-full items-center gap-2 rounded-4 px-2 py-1.5 text-left" :class="i === active ? 'bg-surface-gray-3' : 'hover:bg-surface-gray-2'"
        :data-testid="row.kind === 'record' ? 'search-result' : row.kind === 'all' ? 'search-everywhere' : 'search-place'"
        @mousedown.prevent="choose(row)" @mouseenter="active = i">
        <span :class="[row.icon, 'size-4 flex-none text-ink-gray-6']" aria-hidden="true" />
        <span v-if="row.hint" class="flex-none text-sm text-ink-gray-6">{{ row.hint }}</span>
        <span class="min-w-0 flex-1 truncate text-base text-ink-gray-9">{{ row.title }}</span>
        <span v-if="row.code" class="flex-none font-mono text-xs text-ink-gray-6">{{ row.code }}</span>
        <span v-if="row.where" class="max-w-[160px] flex-none truncate text-xs text-ink-gray-7">{{ row.where }}</span>
      </button>
      <p v-if="busy && !hits" class="m-0 px-2 py-1.5 text-sm text-ink-gray-7">Searching…</p>
      <p v-else-if="!busy && !hits" class="m-0 px-2 py-1.5 text-sm text-ink-gray-7" data-testid="search-none">{{ everywhere || !project ? 'Nothing found.' : 'Nothing found in this project.' }}</p>
      <p v-if="error" role="alert" class="m-0 px-2 py-1.5 text-sm text-ink-red-7">{{ error }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { call } from '../api.js'
import { SECTIONS } from '../paths.js'
import { MIN_QUERY, METHOD, grouped, isOpenKey, placesFor, routeOf } from '../search.js'
import { useMode } from '../mode.js'
import { sectionLabel } from '../words.js'

const route = useRoute()
const router = useRouter()
const mode = useMode()
const root = ref(null)
const field = ref(null)
const query = ref('')
const focused = ref(false)
const results = ref([])
const busy = ref(false)
const error = ref('')
const everywhere = ref(false)
const active = ref(0)
const project = computed(() => route.params.project || '')
const label = (s) => sectionLabel(s, mode.value)
const placeholder = computed(() => (project.value ? 'Search or go to… (Ctrl K)' : 'Search your projects (Ctrl K)'))
let timer = null
let asked = 0

// The rows in the awesome bar's order: places to go, the records by section, then "search all projects".
const rows = computed(() => {
  const places = placesFor(query.value, project.value, SECTIONS, label)
    .map((p, i) => ({ ...p, key: `p${i}`, icon: 'lucide-arrow-right' }))
  const records = grouped(results.value, label).flatMap((g) => g.items.map((r) => ({
    kind: 'record', key: `${r.doctype}:${r.name}`, icon: r.section === 'files' ? 'lucide-file' : 'lucide-file-text',
    title: r.title, code: r.section === 'files' ? '' : r.name,
    where: everywhere.value || !project.value ? `${g.label} · ${r.project_name}` : g.label, route: routeOf(r),
  })))
  const all = project.value && !everywhere.value && query.value.trim().length >= MIN_QUERY
    ? [{ kind: 'all', key: 'all', icon: 'lucide-search', title: `Search for "${query.value.trim()}" in all projects` }] : []
  return [...places, ...records, ...all]
})
const hits = computed(() => rows.value.filter((r) => r.kind !== 'all').length)
const showing = computed(() => focused.value && query.value.trim().length > 0)

async function run() {
  const q = query.value.trim()
  error.value = ''
  active.value = 0
  if (q.length < MIN_QUERY) {
    results.value = []
    return
  }
  const mine = ++asked
  busy.value = true
  try {
    const args = { q }
    if (project.value && !everywhere.value) args.project = project.value
    const out = await call(METHOD, args)
    if (mine === asked) results.value = out.results || []
  } catch (e) {
    if (mine === asked) error.value = e.message || 'Search did not work.'
  } finally {
    if (mine === asked) busy.value = false
  }
}

watch(query, () => {
  everywhere.value = false
  clearTimeout(timer)
  timer = setTimeout(run, 200)
})
watch(() => route.fullPath, () => close())

function close() {
  focused.value = false
  query.value = ''
  results.value = []
  field.value?.blur()
}

function choose(row) {
  if (row.kind === 'all') {
    everywhere.value = true
    run()
    return
  }
  router.push(row.route)
  close()
}

function onKey(event) {
  const n = rows.value.length
  if (event.key === 'ArrowDown' && n) {
    event.preventDefault()
    active.value = (active.value + 1) % n
  } else if (event.key === 'ArrowUp' && n) {
    event.preventDefault()
    active.value = (active.value - 1 + n) % n
  } else if (event.key === 'Enter' && n) {
    event.preventDefault()
    choose(rows.value[Math.min(active.value, n - 1)])
  } else if (event.key === 'Escape') {
    close()
  }
}

function onGlobalKey(event) {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(event.target?.tagName || '') || event.target?.isContentEditable
  if (isOpenKey(event, route) || (event.key === '/' && !typing && !(route.params.section === 'whiteboards' && route.params.item))) {
    event.preventDefault()
    field.value?.focus()
  }
}

function onOutside(event) {
  // The path as it was when pressed: a row Vue has just removed is still inside the bar.
  if (root.value && !event.composedPath().includes(root.value)) focused.value = false
}

onMounted(() => {
  window.addEventListener('keydown', onGlobalKey)
  document.addEventListener('mousedown', onOutside)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onGlobalKey)
  document.removeEventListener('mousedown', onOutside)
  clearTimeout(timer)
})
</script>
