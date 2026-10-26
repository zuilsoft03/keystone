<template>
  <!-- P3-43 (D-302, D-303): a file's next revision, from an upload or from an earlier version, and what happens to a
       takeoff measured on the drawing. The choices have small pictures in the detailed view; the compact view turns
       them off, and the view chosen is remembered. -->
  <Dialog :open="open" size="xl" :title="title" @update:open="(v) => $emit('update:open', v)">
    <form id="version-form" class="flex flex-col gap-4" data-testid="version-dialog" @submit.prevent="submit">
      <p class="m-0 text-p-base text-ink-gray-7" data-testid="version-description">{{ description }}</p>
      <p v-if="file?.signin" class="m-0 rounded-4 bg-surface-gray-2 px-3 py-2 text-sm text-ink-gray-8" data-testid="version-signin">
        This picture is on the sign-in page. It keeps showing Rev {{ current }} until a manager marks the new revision.
      </p>
      <template v-if="mode === 'upload'">
        <div v-if="preset" class="flex flex-col gap-1.5 text-xs text-ink-gray-7" data-testid="version-preset">The new version
          <span class="flex h-8 items-center gap-2 rounded-4 bg-surface-gray-2 px-2 text-base text-ink-gray-9"><span class="lucide-drafting-compass size-4 text-ink-gray-7" aria-hidden="true" />{{ preset.name }}</span>
          <span v-if="wrongType" class="text-ink-red-7" role="alert">This was saved as {{ extOf(preset.name).toUpperCase() || 'another type' }}. Save it as a {{ ext.toUpperCase() }} file in Open CAD Studio to make a new version.</span>
        </div>
        <label v-else class="flex flex-col gap-1.5 text-xs text-ink-gray-7">The new version
          <input ref="input" type="file" :accept="ext ? `.${ext}` : undefined" class="form-input w-full" data-testid="version-file" @change="pick" />
          <span v-if="wrongType" class="text-ink-red-7" role="alert">Choose a {{ ext.toUpperCase() }} file: a new version keeps the file's type.</span>
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">What changed (optional)
          <textarea v-model="note" maxlength="280" rows="2" class="form-textarea w-full" placeholder="Example: Beam sizes changed on level 2" data-testid="version-note" />
        </label>
      </template>

      <fieldset v-if="takeoffs" class="m-0 flex flex-col gap-2 border-0 p-0" data-testid="takeoff-question">
        <div class="flex items-start justify-between gap-3">
          <legend class="p-0 text-base font-semibold text-ink-gray-9">
            This drawing has {{ takeoffs === 1 ? 'a takeoff' : `${takeoffs} takeoffs` }} on Rev {{ current }}. What happens to {{ takeoffs === 1 ? 'it' : 'them' }}?
          </legend>
          <div class="flex flex-none rounded-4 bg-surface-gray-2 p-0.5" role="radiogroup" aria-label="How the choices are shown">
            <button v-for="v in VIEWS" :key="v.id" type="button" role="radio" :aria-checked="view === v.id"
              class="h-6 rounded-3 px-2 text-xs" :class="view === v.id ? 'bg-surface-base text-ink-gray-9 shadow-sm' : 'text-ink-gray-7 hover:text-ink-gray-8'"
              :data-testid="`takeoff-view-${v.id}`" @click="setView(v.id)">{{ v.label }}</button>
          </div>
        </div>
        <div class="flex flex-col gap-2" role="radiogroup" aria-label="What happens to the takeoff">
          <button v-for="c in TAKEOFF_CHOICES" :key="c.value" type="button" role="radio" :aria-checked="choice === c.value"
            class="flex w-full items-center gap-3 rounded-5 border px-3 text-left" :class="[choice === c.value ? 'border-outline-gray-4 bg-surface-gray-2' : 'border-outline-gray-2 bg-surface-base hover:border-outline-gray-3', view === 'detailed' ? 'py-3' : 'py-2']"
            data-testid="takeoff-choice" :data-value="c.value" @click="choice = c.value">
            <span class="grid size-4 flex-none place-items-center rounded-full border" :class="choice === c.value ? 'border-outline-gray-8' : 'border-outline-gray-3'" aria-hidden="true">
              <span v-if="choice === c.value" class="size-2 rounded-full bg-surface-gray-8" />
            </span>
            <span v-if="view === 'detailed'" class="flex flex-none items-end gap-1.5" aria-hidden="true" data-testid="takeoff-picture">
              <span class="flex flex-col items-center gap-1">
                <span class="relative grid h-12 w-10 place-items-center rounded-3 border border-outline-gray-3 bg-surface-base" :class="c.value === 'reuse' ? 'opacity-50' : ''">
                  <span class="lucide-file size-4 text-ink-gray-5" />
                  <span v-if="c.value !== 'reuse'" class="absolute -right-1.5 -top-1.5 grid size-5 place-items-center rounded-full bg-surface-blue-2 text-ink-blue-7"><span class="lucide-ruler size-3" /></span>
                </span>
                <span class="text-[11px] text-ink-gray-7">Rev {{ current }}</span>
              </span>
              <span :class="[c.value === 'copy' ? 'lucide-copy' : 'lucide-arrow-right', 'mb-6 size-3.5 text-ink-gray-6']" />
              <span class="flex flex-col items-center gap-1">
                <span class="relative grid h-12 w-10 place-items-center rounded-3 border bg-surface-base" :class="c.value === 'new' ? 'border-dashed border-outline-gray-4' : 'border-outline-gray-3'">
                  <span :class="[c.value === 'new' ? 'lucide-plus' : 'lucide-file', 'size-4 text-ink-gray-5']" />
                  <span v-if="c.value !== 'new'" class="absolute -right-1.5 -top-1.5 grid size-5 place-items-center rounded-full bg-surface-blue-2 text-ink-blue-7"><span :class="[c.value === 'copy' ? 'lucide-pencil' : 'lucide-ruler', 'size-3']" /></span>
                </span>
                <span class="text-[11px] font-medium text-ink-gray-9">Rev {{ next }}</span>
              </span>
            </span>
            <span class="min-w-0">
              <span class="block text-base text-ink-gray-9">{{ fillRev(c.label, current, next) }}</span>
              <span v-if="view === 'detailed'" class="mt-0.5 block text-sm text-ink-gray-7">{{ fillRev(c.detail, current, next) }}</span>
            </span>
          </button>
        </div>
      </fieldset>
    </form>
    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button label="Cancel" @click="close" />
        <Button type="submit" form="version-form" variant="solid" theme="blue" :label="mode === 'upload' ? `Upload as Rev ${next}` : `Restore as Rev ${next}`"
          :disabled="busy || !ready" data-testid="version-confirm" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Dialog } from 'frappe-ui'
import { TAKEOFF_CHOICES, extOf, fillRev, nextRev, sameType } from '../files.js'

const props = defineProps({
  open: { type: Boolean, default: false },
  mode: { type: String, default: 'upload' }, // 'upload' or 'restore'
  file: { type: Object, default: null }, // the panel's details: file_name, rev, drawings
  restoring: { type: Object, default: null }, // the earlier version: rev, version
  busy: { type: Boolean, default: false },
  preset: { type: Object, default: null }, // P3-48: a File saved in Open CAD Studio, instead of a picked one
})
const emit = defineEmits(['update:open', 'submit'])

const VIEWS = [{ id: 'compact', label: 'Compact' }, { id: 'detailed', label: 'Detailed' }]
const VIEW_KEY = 'cc.files.takeoffChoices'
const stored = () => { try { return localStorage.getItem(VIEW_KEY) } catch { return null } }
const view = ref(stored() === 'compact' ? 'compact' : 'detailed')
function setView(v) {
  view.value = v
  try { localStorage.setItem(VIEW_KEY, v) } catch { /* private window */ }
}

const input = ref(null)
const chosen = ref(null)
const note = ref('')
const choice = ref('')
const current = computed(() => props.file?.rev || 'A')
const next = computed(() => nextRev(current.value))
const ext = computed(() => extOf(props.file?.file_name))
const takeoffs = computed(() => (props.file?.drawings || []).reduce((n, d) => n + (Number(d.takeoffs) || 0), 0))
const wrongType = computed(() => !!chosen.value && !sameType(chosen.value.name, props.file?.file_name))
const ready = computed(() => (props.mode === 'restore' || (chosen.value && !wrongType.value)) && (!takeoffs.value || !!choice.value))
const title = computed(() => (props.mode === 'upload' ? 'Upload new version' : `Restore Rev ${props.restoring?.rev || ''}`))
const description = computed(() => (props.mode === 'upload'
  ? `Rev ${next.value} of ${props.file?.file_name || 'this file'}. It keeps its name and link; Rev ${current.value} stays in the history.`
  : `Rev ${props.restoring?.rev || ''} comes back as Rev ${next.value}. Rev ${current.value} stays in the history; nothing is deleted.`))

function pick(event) {
  chosen.value = event.target.files?.[0] || null
}
function submit() {
  if (!ready.value) return
  emit('submit', { file: chosen.value, note: note.value.trim(), takeoffs: takeoffs.value ? choice.value : '' })
}
watch(() => props.open, (on) => {
  if (!on) return
  chosen.value = props.preset
  note.value = ''
  choice.value = ''
  if (input.value) input.value.value = ''
})
</script>
