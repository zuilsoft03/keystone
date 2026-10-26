<template>
  <!-- P3-09 (D-138, D-157): the design's "Project map" and "Selected site" cards (Main frame, D-124): the projects with
       a site as pins coloured by status, and the selected one's card with real data only and Directions. P3-35
       (D-279): zoom with + and -, a double-click, a pinch, or Ctrl (⌘) and the wheel; Zoom to site; All sites. -->
  <section v-if="tiles && pins.length" aria-labelledby="map-h" class="cw-card flex min-w-0 flex-col overflow-hidden" data-testid="project-map">
    <div class="flex flex-wrap items-center gap-2.5 border-b border-outline-gray-1 px-4 py-3">
      <h2 id="map-h" class="cw-card-title">Project map</h2>
      <span class="text-sm text-ink-gray-7" data-testid="map-count">{{ pins.length }} {{ pins.length === 1 ? 'site' : 'sites' }}</span>
      <span class="ml-auto flex flex-wrap gap-1.5">
        <Badge label="Active" theme="green" /><Badge label="On hold" theme="amber" /><Badge label="Closed" theme="gray" />
      </span>
    </div>
    <!-- isolate: Leaflet's panes and controls (z-index 400 to 1000) stay inside the card, under any dialog (P3-39) -->
    <div class="relative isolate">
      <div ref="el" class="h-[420px] w-full bg-surface-blue-1" role="application" aria-label="Map of project sites" :data-zoom="zoom" data-testid="map" />
      <!-- P3-35 (D-279): zoom with Ctrl (or ⌘) and the wheel or a trackpad pinch; a plain scroll keeps scrolling the page -->
      <div v-if="hint" class="pointer-events-none absolute inset-0 z-[999] grid place-items-center text-base font-medium text-white" style="background: rgba(0, 0, 0, 0.38)" role="status" data-testid="map-zoom-hint">
        {{ MAC ? 'Hold ⌘ and scroll to zoom the map' : 'Hold Ctrl and scroll to zoom the map' }}
      </div>
      <button type="button" class="absolute left-3 top-[84px] z-[1000] inline-flex h-7 items-center gap-1.5 rounded-4 border border-outline-gray-3 bg-surface-base px-2 text-sm text-ink-gray-8 shadow-sm hover:bg-surface-gray-2"
        aria-label="Zoom out to all sites" data-testid="map-all" @click="fitAll(true)">
        <span class="lucide-maximize-2 size-3.5" aria-hidden="true" />All sites
      </button>
      <!-- D-248: the selected site as a panel over the map's right side, closed with its button, opened by a pin -->
      <aside v-if="selected && panelOpen" class="absolute right-3 top-3 z-[1000] flex max-h-[calc(100%-24px)] w-[280px] max-w-[calc(100%-24px)] flex-col gap-3 overflow-y-auto rounded-6 border border-outline-gray-2 bg-surface-base p-4 shadow-lg"
        aria-label="Selected site" data-testid="site-card">
        <div class="flex items-center">
          <div class="flex-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-gray-6">Selected site</div>
          <button type="button" class="grid size-7 place-items-center rounded-4 text-ink-gray-7 hover:bg-surface-gray-2" aria-label="Close the site panel" data-testid="site-close" @click="panelOpen = false">
            <span class="lucide-x size-4" aria-hidden="true" />
          </button>
        </div>
        <div class="flex items-start gap-2.5">
          <ProjectBadge :name="selected.name" :label="selected.project_name" size="xl" />
          <div class="min-w-0">
            <div class="font-semibold text-ink-gray-9" data-testid="site-name">{{ selected.project_name }}</div>
            <div class="text-sm text-ink-gray-7">{{ selected.site.place }}</div>
          </div>
        </div>
        <div class="text-sm leading-[1.8] text-ink-gray-7">
          {{ [selected.name, ...(selected.clients || [])].join(' · ') }}<br>
          {{ [statusOf(selected.status).label, selected.cc_phase, handoverText(selected.handover_in_days)].filter(Boolean).join(' · ') }}
          <template v-if="advanced"><br>{{ counts.rfi_open || 0 }} open {{ sectionLabel('rfi', ADVANCED) }} · {{ counts.submittal_open || 0 }} {{ sectionLabel('submittals', ADVANCED).toLowerCase() }} pending</template>
        </div>
        <div class="mt-auto flex flex-col gap-2">
          <Button variant="solid" theme="blue" size="md" class="w-full justify-center" label="Open project" data-testid="site-open" @click="$emit('open', selected)" />
          <Button variant="outline" size="md" class="w-full justify-center" icon-left="lucide-zoom-in" label="Zoom to site" data-testid="site-zoom" @click="zoomTo(selected)" />
          <a :href="directionsUrl(selected.site)" target="_blank" rel="noopener noreferrer"
            class="inline-flex h-8 items-center justify-center rounded-5 bg-surface-gray-2 text-base text-ink-gray-8 no-underline hover:bg-surface-gray-3" data-testid="site-directions">Directions to site</a>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Badge, Button } from 'frappe-ui'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import ProjectBadge from './ProjectBadge.vue'
import { boot } from '../boot.js'
import { directionsUrl, handoverText, pinsOf, statusOf } from '../frame.js'
import { ADVANCED, sectionLabel } from '../words.js'

const props = defineProps({ projects: Array, countsOf: Function, advanced: Boolean })
defineEmits(['open'])
const tiles = boot.map_tiles || null // off by site config, or no source we can credit: no map (D-157)
const el = ref(null)
const pins = computed(() => pinsOf(props.projects))
const chosen = ref('')
const panelOpen = ref(true)
const selected = computed(() => pins.value.find((p) => p.name === chosen.value) || pins.value[0] || null)
const counts = computed(() => (selected.value && props.countsOf ? props.countsOf(selected.value) : {}) || {})
const PIN = { Open: 'cw-pin-active', 'On hold': 'cw-pin-hold' }
let map = null
let layer = null
let fitted = ''
const zoom = ref(0)
const hint = ref(false)
const MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || '')
const SITE_ZOOM = 16
let hintTimer = null
let wheel = 0

// Ctrl (or ⌘) with the wheel zooms around the pointer; a trackpad pinch arrives the same way. A plain scroll still
// scrolls the page, with a short hint, so the dashboard never gets stuck under the map (D-279).
function onWheel(e) {
  if (!map) return
  if (!(e.ctrlKey || e.metaKey)) {
    hint.value = true
    clearTimeout(hintTimer)
    hintTimer = setTimeout(() => { hint.value = false }, 1200)
    return
  }
  e.preventDefault() // the map's zoom, not the browser's page zoom
  hint.value = false
  wheel += e.deltaY
  if (Math.abs(wheel) < 40) return // a pinch sends many small steps
  const step = wheel < 0 ? 1 : -1
  wheel = 0
  map.setZoomAround(map.mouseEventToContainerPoint(e), Math.max(map.getMinZoom(), Math.min(map.getMaxZoom(), map.getZoom() + step)))
}

function fitAll(animate = false) {
  if (!map) return
  const points = pins.value.map((p) => [+p.site.lat, +p.site.lng])
  if (points.length === 1) map.setView(points[0], 13, { animate })
  else if (points.length) map.fitBounds(points, { padding: [32, 32], maxZoom: 13, animate })
}

function zoomTo(p) {
  if (map && p) map.flyTo([+p.site.lat, +p.site.lng], SITE_ZOOM, { duration: 0.6 })
}

function draw() {
  if (!el.value || !tiles) return
  if (!map) {
    map = L.map(el.value, { zoomControl: true, attributionControl: true, scrollWheelZoom: false })
    map.on('zoomend', () => { zoom.value = map.getZoom() })
    el.value.addEventListener('wheel', onWheel, { passive: false })
    // Leaflet writes the attribution as HTML: the site config's text goes in escaped, as text only.
    const credit = String(tiles.attribution).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    L.tileLayer(tiles.url, { attribution: credit, maxZoom: 18 }).addTo(map)
    layer = L.layerGroup().addTo(map)
  }
  layer.clearLayers()
  for (const p of pins.value) {
    const at = [+p.site.lat, +p.site.lng]
    L.circleMarker(at, { radius: p.name === selected.value?.name ? 10 : 7, className: `cw-pin ${PIN[p.status] || 'cw-pin-closed'}` })
      // Leaflet writes a string tooltip as HTML: a text node keeps the name and place as text (P3-35 audit S1).
      .bindTooltip(document.createTextNode(`${p.project_name}${p.site.place ? ' · ' + p.site.place : ''}`))
      .on('click', () => { chosen.value = p.name; panelOpen.value = true })
      .addTo(layer)
  }
  // The view is fitted to the sites only when they change, so choosing a pin keeps the zoom the person picked.
  const key = pins.value.map((p) => `${p.name}:${p.site.lat}:${p.site.lng}`).join('|')
  if (key !== fitted) {
    fitted = key
    fitAll()
  }
  zoom.value = map.getZoom()
}

watch([pins, () => selected.value?.name], () => nextTick(draw), { immediate: true, deep: true })
onBeforeUnmount(() => {
  clearTimeout(hintTimer)
  el.value?.removeEventListener('wheel', onWheel)
  map?.remove()
  map = null
})
</script>

<style>
/* The pins' colours are the design system's tokens (no fixed hues, theme.test.js). */
.cw-pin { stroke: var(--surface-base); stroke-width: 2; fill-opacity: 1; }
.cw-pin-active { fill: var(--ink-green-6, currentColor); }
.cw-pin-hold { fill: var(--ink-amber-6, currentColor); }
.cw-pin-closed { fill: var(--ink-gray-5, currentColor); }
</style>
