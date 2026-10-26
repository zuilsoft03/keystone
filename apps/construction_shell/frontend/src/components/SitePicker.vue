<template>
  <!-- P3-39 (D-285): a small map to drop a project's site pin. Click to place it, click again to move it; Ctrl (⌘) and
       the wheel zoom as on the dashboard map (D-279). With the site's map turned off (D-157), only the place shows. -->
  <div v-if="tiles" class="flex flex-col gap-1.5">
    <div ref="el" class="isolate h-[220px] w-full overflow-hidden rounded-4 border border-outline-gray-2 bg-surface-blue-1" role="application"
      aria-label="Map: click to place the site pin" data-testid="site-picker" />
    <div class="flex flex-wrap items-center gap-2 text-xs text-ink-gray-7">
      <span v-if="modelValue" data-testid="site-coords">Pin at {{ modelValue.lat.toFixed(5) }}, {{ modelValue.lng.toFixed(5) }}</span>
      <span v-else>Click the map where the site is. Hold {{ MAC ? '⌘' : 'Ctrl' }} and scroll to zoom.</span>
      <button v-if="modelValue" type="button" class="text-ink-blue-8 underline underline-offset-2" data-testid="site-clear" @click="clear">Remove the pin</button>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { boot } from '../boot.js'

const props = defineProps({ modelValue: { type: Object, default: null } })
const emit = defineEmits(['update:modelValue'])
const tiles = boot.map_tiles || null
const MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || '')
const START = [12.8797, 121.774] // the Philippines, before a pin is placed
const el = ref(null)
let map = null
let pin = null
let wheel = 0

function place(at) {
  if (!pin) pin = L.circleMarker(at, { radius: 8, className: 'cw-pin cw-pin-active' }).addTo(map)
  else pin.setLatLng(at)
}

function clear() {
  pin?.remove()
  pin = null
  emit('update:modelValue', null)
}

function onWheel(e) {
  if (!map || !(e.ctrlKey || e.metaKey)) return
  e.preventDefault()
  wheel += e.deltaY
  if (Math.abs(wheel) < 40) return
  const step = wheel < 0 ? 1 : -1
  wheel = 0
  map.setZoomAround(map.mouseEventToContainerPoint(e), Math.max(map.getMinZoom(), Math.min(map.getMaxZoom(), map.getZoom() + step)))
}

onMounted(async () => {
  await nextTick()
  if (!el.value || !tiles) return
  map = L.map(el.value, { scrollWheelZoom: false, attributionControl: true })
  const credit = String(tiles.attribution).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  L.tileLayer(tiles.url, { attribution: credit, maxZoom: 18 }).addTo(map)
  if (props.modelValue) {
    map.setView([props.modelValue.lat, props.modelValue.lng], 15)
    place([props.modelValue.lat, props.modelValue.lng])
  } else map.setView(START, 5)
  map.on('click', (e) => {
    const at = { lat: Math.round(e.latlng.lat * 1e6) / 1e6, lng: Math.round(e.latlng.wrap().lng * 1e6) / 1e6 }
    place([at.lat, at.lng])
    emit('update:modelValue', at)
  })
  el.value.addEventListener('wheel', onWheel, { passive: false })
  setTimeout(() => map && map.invalidateSize(), 200) // the dialog finishes opening after the map is made
})
onBeforeUnmount(() => {
  el.value?.removeEventListener('wheel', onWheel)
  map?.remove()
  map = null
})
</script>
