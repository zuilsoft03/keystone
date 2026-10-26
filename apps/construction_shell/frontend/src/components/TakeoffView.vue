<template>
  <div class="flex min-h-0 flex-1 flex-col gap-3.5 px-6 py-5" data-testid="takeoff-view">
    <div class="flex flex-wrap items-end gap-3">
      <div class="min-w-0 flex-[1_1_320px]">
        <div class="text-xs text-ink-gray-7"><router-link :to="{ name: 'section', params: { project, section: 'takeoff' } }" class="text-ink-gray-7 no-underline hover:text-ink-gray-9">← {{ sectionLabel('takeoff', mode) }}</router-link></div>
        <div class="mt-1 flex flex-wrap items-baseline gap-2.5">
          <h1 class="m-0 text-3xl-semibold text-ink-gray-9">{{ d?.title || 'Drawing' }}</h1>
          <span v-if="d" class="text-sm text-ink-gray-7">{{ d.source || 'DXF' }}<template v-if="d.geometry?.layers?.length"> · {{ d.geometry.layers.length }} layers</template></span>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <a v-if="d" :href="`/api/method/construction_core.takeoff.api.export?name=${encodeURIComponent(name)}`" class="inline-flex h-8 items-center gap-1 rounded-4 bg-surface-blue-6 px-2.5 text-base font-medium text-ink-base no-underline hover:bg-surface-blue-7 active:bg-surface-blue-8">
          <span class="lucide-download size-4" aria-hidden="true" />Export to Excel
        </a>
      </div>
    </div>
    <p v-if="error" class="text-ink-red-7" role="alert" data-testid="error">{{ error }}</p>
    <p v-if="notice" class="text-ink-green-7" data-testid="notice">{{ notice }}</p>
    <div class="flex min-h-0 flex-1 flex-wrap gap-3">
      <div class="cw-card flex min-w-0 flex-[999_1_520px] flex-col overflow-hidden">
        <div role="toolbar" aria-label="Measure tools" class="flex flex-wrap items-center gap-1 border-b border-outline-gray-1 px-2 py-1.5">
          <button v-for="[id, label, icon] in tools" :key="id" type="button" class="inline-flex h-[30px] items-center gap-1.5 rounded-4 px-2.5 text-sm"
            :class="tool === id ? 'bg-surface-gray-3 text-ink-gray-9' : 'text-ink-gray-7 hover:bg-surface-gray-2'"
            :aria-pressed="tool === id" :data-testid="id === 'calibrate' ? 'calibrate' : `tool-${id}`" @click="pickTool(id)">
            <span :class="icon" class="size-4" aria-hidden="true" />{{ label }}
          </button>
          <Button class="ml-auto" variant="ghost" icon-left="lucide-maximize" label="Fit" @click="canvas && canvas.fit()" />
        </div>
        <!-- The engine paints its own white sheet (D-126: the takeoff canvas keeps its light look). -->
        <div class="relative min-h-[60vh] min-w-0 flex-1">
          <div ref="host" class="absolute inset-0" data-testid="takeoff-canvas" />
        </div>
        <div class="flex flex-wrap gap-4 bg-surface-gray-10 px-3 py-1.5 font-mono text-[11px] text-ink-gray-3" data-testid="hud">{{ hud }}</div>
      </div>
      <aside class="cw-card flex flex-[1_1_280px] flex-col gap-2 overflow-y-auto p-3 text-sm md:max-w-[320px]">
        <h2 class="cw-label m-0 text-ink-gray-7">Takeoffs</h2>
        <div v-for="t in d?.takeoffs || []" :key="t.name" class="cursor-pointer rounded-5 border px-3 py-2"
          :class="active === t.name ? 'border-outline-blue-6 ring-1 ring-outline-blue-6' : 'border-outline-gray-1 hover:border-outline-gray-3'" data-testid="takeoff" @click="activate(t.name)">
          <div class="flex items-center gap-1.5"><span class="size-2.5 rounded-1" :style="{ background: t.color }" /><b class="font-semibold text-ink-gray-9">{{ t.title }}</b></div>
          <div class="text-xs text-ink-gray-7" data-testid="takeoff-total">{{ t.kind }} · {{ num(t.total) }} {{ t.unit }} · {{ t.items.length }} items<template v-if="(drafts[t.name] || []).length"> (+{{ drafts[t.name].length }} unsaved)</template></div>
          <div v-if="active === t.name" class="mt-2 flex gap-1.5">
            <Button size="sm" variant="solid" theme="blue" label="Save" data-testid="save-takeoff" @click.stop="save(t)" />
            <Button size="sm" label="Undo last" @click.stop="undo(t)" />
            <Button size="sm" variant="ghost" theme="red" label="Delete" @click.stop="remove(t)" />
          </div>
        </div>
        <form v-if="creating" class="flex flex-col gap-2 rounded-5 border border-outline-gray-1 p-2.5" @submit.prevent="create">
          <input v-model="draft.title" required placeholder="Title" aria-label="Takeoff title" class="form-input w-full" data-testid="takeoff-title" />
          <select v-model="draft.kind" aria-label="Kind" class="form-select w-full py-0" data-testid="takeoff-kind">
            <option>Length</option><option>Area</option><option>Count</option>
          </select>
          <label class="flex items-center gap-2 text-xs text-ink-gray-7">Colour <input v-model="draft.color" type="color" /></label>
          <Button type="submit" variant="solid" theme="blue" label="Create" data-testid="create-takeoff" />
        </form>
        <Button v-else class="w-full" variant="outline" icon-left="lucide-plus" label="New takeoff" data-testid="new-takeoff" @click="creating = true" />
        <form v-if="calibrating" class="flex flex-col gap-2 rounded-5 border border-outline-amber-2 bg-surface-amber-1 p-2.5" @submit.prevent="finishCalibration">
          <label class="text-xs text-ink-gray-8" for="real-length">Real distance between the two points (m)</label>
          <input id="real-length" v-model.number="realLength" type="number" step="any" min="0" required class="form-input w-full" data-testid="real-length" />
          <Button type="submit" variant="solid" theme="blue" label="Calibrate" />
        </form>
        <h2 class="cw-label m-0 mt-2 text-ink-gray-7">Layers</h2>
        <label v-for="layer in d?.geometry.layers || []" :key="layer" class="flex items-center gap-2 truncate text-xs text-ink-gray-8">
          <input type="checkbox" class="form-checkbox rounded-1" checked @change="canvas.setLayerVisible(layer, $event.target.checked)" /> {{ layer }}
        </label>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Button } from 'frappe-ui'
import { call } from '../api.js'
import { ENGINES, loadScript } from '../loader.js'
import { useMode } from '../mode.js'
import { sectionLabel } from '../words.js'

// DXF and PDF takeoff on the same engine (takeoff_canvas.js) and API as the Desk page (P1-16, P1-18). The browser
// only previews; the server computes every saved quantity.
const TK = 'construction_core.takeoff.api.'
const PDF_MAX_PX = 6000
const TOOL_OF = { Length: 'length', Area: 'area', Count: 'count' }
const UNIT_OF = { length: 'm', area: 'm²', count: 'pcs' }
const props = defineProps({ name: { type: String, required: true }, project: String })
const mode = useMode()
const host = ref(null)
const d = ref(null)
const active = ref(null)
const drafts = reactive({})
const hud = ref('')
const error = ref('')
const notice = ref('')
const creating = ref(false)
const draft = reactive({ title: '', kind: 'Length', color: '#e8590c' })
const calibrating = ref(false)
// The design's tool bar (D-124, version 1791648865-5845): Pan, the active takeoff's own measuring tool, and Calibrate.
// A measurement belongs to a takeoff of one kind, so the bar offers that kind's tool only.
const tool = ref('pan')
const tools = computed(() => {
  const t = active.value && d.value?.takeoffs.find((x) => x.name === active.value)
  const measure = t ? [[TOOL_OF[t.kind], t.kind, { length: 'lucide-ruler', area: 'lucide-square-dashed', count: 'lucide-hash' }[TOOL_OF[t.kind]]]] : []
  return [['pan', 'Pan', 'lucide-hand'], ...measure, ['calibrate', 'Calibrate', 'lucide-scale-3d']]
})
const realLength = ref(null)
let canvas = null
let calibrationPoints = null
let bgKey = null

const num = (v) => Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 3 })

function status() {
  const g = d.value.geometry.pdf
  if (!d.value.unit_to_m) {
    hud.value = g ? `PDF page ${g.page} of ${g.pages}: calibrate on a known distance first` : 'Units unknown: calibrate first'
    return
  }
  hud.value = `Scale: ${d.value.unit_to_m} m per unit (${d.value.calibrated ? 'calibrated' : d.value.units || '?'})`
}

function overlays() {
  canvas.setOverlays(d.value.takeoffs.map((t) => ({
    color: t.color, kind: t.kind,
    shapes: t.items.map((i) => i.points).concat((drafts[t.name] || []).map((i) => i.points)),
  })))
}

async function render(data) {
  d.value = data
  if (!canvas) {
    canvas = new window.CcTakeoffCanvas(host.value, { onPreview: preview, onFinish: finished })
  }
  canvas.setGeometry(data.geometry)
  if (data.source !== 'PDF') {
    canvas.background = null
    bgKey = null
  }
  for (const k of Object.keys(drafts)) delete drafts[k]
  overlays()
  status()
  if (data.source === 'PDF') loadPdf(data)
}

// PDF.js draws the page once, at up to PDF_MAX_PX on its longest side, as the canvas background (P1-18).
async function loadPdf(data) {
  const g = data.geometry.pdf
  const key = `${data.file}#${g.page}`
  if (bgKey === key) return
  bgKey = key
  hud.value = 'Loading the PDF page…'
  try {
    const pdfjs = await import(/* @vite-ignore */ ENGINES.pdfjs + 'pdf.min.js')
    pdfjs.GlobalWorkerOptions.workerSrc = ENGINES.pdfjs + 'pdf.worker.min.js'
    const doc = await pdfjs.getDocument({
      url: data.file, isEvalSupported: false, cMapUrl: ENGINES.pdfjs + 'cmaps/', cMapPacked: true,
      standardFontDataUrl: ENGINES.pdfjs + 'standard_fonts/',
    }).promise
    try {
      const pg = await doc.getPage(g.page)
      const unit = pg.getViewport({ scale: 1 })
      const vp = pg.getViewport({ scale: Math.min(4, PDF_MAX_PX / Math.max(unit.width, unit.height)) })
      const image = document.createElement('canvas')
      image.width = Math.floor(vp.width)
      image.height = Math.floor(vp.height)
      await pg.render({ canvasContext: image.getContext('2d'), viewport: vp }).promise
      if (bgKey !== key || !canvas) return
      canvas.background = { image, x: 0, y: 0, w: unit.width, h: unit.height }
      canvas.draw()
    } finally {
      doc.destroy()
    }
    status()
  } catch (e) {
    bgKey = null
    error.value = `The PDF page could not be shown: ${e.message || e}`
  }
}

function setTool(name) {
  tool.value = name
  canvas.setTool(name)
}

function pickTool(name) {
  if (name === 'calibrate') return startCalibration()
  setTool(name)
  if (name === 'pan') hud.value = 'Pan: drag to move, scroll to zoom.'
}

function activate(name) {
  active.value = name
  const t = d.value.takeoffs.find((x) => x.name === name)
  setTool(TOOL_OF[t.kind])
  hud.value = `${t.title}: click points, double-click to finish a measurement. Shift-drag pans.`
}

function preview(tool, pts) {
  if (tool === 'calibrate') {
    hud.value = pts.length ? 'Pick the second point' : 'Pick the first point of a known distance'
    return
  }
  const s = d.value.unit_to_m
  if (!pts.length || !s) return
  const C = window.CcTakeoffCanvas
  const v = tool === 'area' ? C.area(pts) * s * s : tool === 'count' ? pts.length / 2 : C.length(pts) * s
  hud.value = `${num(v)} ${UNIT_OF[tool]}`
}

function finished(tool, pts) {
  if (tool === 'calibrate') {
    calibrationPoints = pts
    calibrating.value = true
    // Two points make a calibration: park on Pan while the distance is typed, so a habitual double-click (as with the
    // Length tool) cannot start a second, zero-length calibration over this one (found by the P2-07 PDF case).
    setTool('pan')
    hud.value = 'Type the real distance between the two points'
    return
  }
  if (!active.value) {
    error.value = 'Pick or create a takeoff first.'
    return
  }
  ;(drafts[active.value] = drafts[active.value] || []).push({ label: '', points: pts })
  overlays()
}

async function run(job) {
  error.value = ''
  notice.value = ''
  try {
    await job()
  } catch (e) {
    error.value = e.message || 'That did not work.'
  }
}

async function reload() {
  const keep = active.value
  const data = await call(TK + 'drawing', { name: props.name })
  d.value = data
  for (const k of Object.keys(drafts)) delete drafts[k]
  overlays()
  if (keep && data.takeoffs.find((x) => x.name === keep)) activate(keep)
}

function create() {
  run(async () => {
    const r = await call(TK + 'save_takeoff', { drawing: props.name, title: draft.title, kind: draft.kind, color: draft.color, items: '[]' }, { post: true })
    creating.value = false
    draft.title = ''
    active.value = r.name
    await reload()
    activate(r.name)
  })
}

function save(t) {
  run(async () => {
    const items = t.items.map((i) => ({ label: i.label, points: i.points })).concat(drafts[t.name] || [])
    const r = await call(TK + 'save_takeoff', {
      drawing: props.name, takeoff: t.name, title: t.title, kind: t.kind, color: t.color, items: JSON.stringify(items),
    }, { post: true })
    notice.value = `Saved: ${num(r.total)} ${r.unit}`
    await reload()
  })
}

function undo(t) {
  const list = drafts[t.name] || []
  if (list.length) list.pop()
  else if (t.items.length) t.items.pop() // removed from the saved list on the next Save
  overlays()
}

function remove(t) {
  if (!window.confirm(`Delete takeoff ${t.title}?`)) return
  run(async () => {
    await call(TK + 'delete_takeoff', { name: t.name }, { post: true })
    active.value = null
    await reload()
  })
}

function startCalibration() {
  setTool('calibrate')
  hud.value = 'Pick the first point of a known distance'
}

function finishCalibration() {
  run(async () => {
    await call(TK + 'calibrate', { name: props.name, points: JSON.stringify(calibrationPoints), real_length_m: realLength.value }, { post: true })
    calibrating.value = false
    realLength.value = null
    notice.value = 'Calibrated; every takeoff was recomputed.'
    const t = active.value && d.value.takeoffs.find((x) => x.name === active.value)
    setTool(t ? TOOL_OF[t.kind] : 'pan')
    await render(await call(TK + 'drawing', { name: props.name }))
  })
}

onMounted(() => run(async () => {
  await loadScript(ENGINES.takeoff)
  await render(await call(TK + 'drawing', { name: props.name }))
}))

onBeforeUnmount(() => {
  bgKey = null
  canvas = null // the engine keeps no global state; its element goes with this component
})
</script>
