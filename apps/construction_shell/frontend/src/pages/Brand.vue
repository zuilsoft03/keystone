<template>
  <!-- P3-45 (D-300, D-445; docs/design/brand.md): the owner's Brand page, for System Managers. The canvas has no frame for it, so it
       is built from the design system's tokens and its closest frames, Settings (the cards) and the sign-in pages (the
       preview), as D-196 allows. The server checks System Manager on every call and refuses a colour white text cannot be read
       on. The "Powered by" credit shows in the preview and has no switch (D-404). -->
  <component :is="embedded ? 'div' : 'main'" class="flex max-w-5xl flex-1 flex-col gap-3.5" :class="{ 'px-4 py-5 sm:px-6': !embedded }" data-testid="brand-page">
    <PageHead v-if="!embedded" crumb="Workspace / Brand" title="Your brand" />
    <p v-if="!boot.system_manager" role="alert" class="text-ink-red-7" data-testid="brand-denied">You are not allowed to change the brand. Ask a System Manager.</p>
    <template v-else>
      <p class="m-0 text-sm text-ink-gray-7">Your firm's name, logo and colours lead on every page your team and clients see.</p>
      <p v-if="error" role="alert" class="m-0 text-ink-red-7" data-testid="brand-error">{{ error }}</p>
      <p v-if="done" class="m-0 text-ink-green-7" data-testid="brand-done">{{ done }}</p>

      <div class="grid gap-3.5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div class="flex min-w-0 flex-col gap-3.5">
          <section class="cw-card flex flex-col gap-3 px-4 py-3.5" aria-labelledby="sec-name">
            <h2 id="sec-name" class="cw-card-title">Name and logo</h2>
            <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Company name
              <input v-model="form.company_name" maxlength="140" class="form-input h-12 w-full md:h-8" data-testid="brand-company" />
            </label>
            <div class="flex flex-col gap-1.5 text-xs text-ink-gray-7">
              <span>Logo <span class="text-ink-gray-6">PNG, JPEG or WebP</span></span>
              <div class="flex flex-wrap items-center gap-2">
                <img v-if="look.logo" :src="look.logo" :alt="`${brand.company} logo`" class="h-12 max-w-[160px] rounded-4 border border-outline-gray-2 object-contain" data-testid="brand-logo-now" />
                <Button label="Upload a logo" icon-left="lucide-upload" class="max-md:!h-12" :disabled="busy" data-testid="brand-logo-pick" @click="logoInput.click()" />
                <Button v-if="look.logo" label="Remove" class="max-md:!h-12" :disabled="busy" data-testid="brand-logo-clear" @click="clear('logo')" />
                <input ref="logoInput" type="file" accept="image/png,image/jpeg,image/webp" class="hidden" data-testid="brand-logo-file" @change="pick('logo', $event)" />
              </div>
            </div>
          </section>

          <section class="cw-card flex flex-col gap-3 px-4 py-3.5" aria-labelledby="sec-colour">
            <h2 id="sec-colour" class="cw-card-title">Colours</h2>
            <div v-for="c in COLOURS" :key="c.key" class="flex flex-col gap-1.5 text-xs text-ink-gray-7">
              <label :for="`brand-${c.key}`">{{ c.label }} <span class="text-ink-gray-6">{{ c.hint }}</span></label>
              <div class="flex items-center gap-2">
                <input type="color" :value="hexOf(form[c.key])" class="size-12 flex-none cursor-pointer rounded-4 border border-outline-gray-2 bg-transparent p-1 md:size-8" :aria-label="`${c.label}, pick`" :data-testid="`brand-${c.key}-pick`" @input="form[c.key] = $event.target.value" />
                <input :id="`brand-${c.key}`" v-model="form[c.key]" maxlength="7" spellcheck="false" autocomplete="off" placeholder="Default" class="form-input h-12 w-32 md:h-8" :aria-invalid="form[c.key] !== '' && !hexOf(form[c.key])" :data-testid="`brand-${c.key}`" />
              </div>
            </div>
            <p class="m-0 text-xs text-ink-gray-7">A colour must be dark enough for white text to be read on it.</p>
          </section>

          <section class="cw-card flex flex-col gap-3 px-4 py-3.5" aria-labelledby="sec-font">
            <h2 id="sec-font" class="cw-card-title">Heading font</h2>
            <p class="m-0 text-xs text-ink-gray-7">Used for the name and the headings on the sign-in and client pages. Screens stay Inter.</p>
            <div role="radiogroup" aria-label="Heading font" class="flex flex-col gap-1">
              <label v-for="(f, key) in FONTS" :key="key" class="flex min-h-12 items-center gap-2.5 rounded-4 px-2 text-ink-gray-9 hover:bg-surface-gray-2 md:min-h-9">
                <input v-model="form.heading_font" type="radio" :value="key" class="form-radio" :data-testid="`brand-font-${key}`" />
                <span class="text-[18px]" :style="{ fontFamily: f.family, fontWeight: key === 'ibm-plex-sans' ? 700 : 800 }">{{ f.name }}</span>
              </label>
            </div>
          </section>

          <section class="cw-card flex flex-col gap-3 px-4 py-3.5" aria-labelledby="sec-picture">
            <h2 id="sec-picture" class="cw-card-title">Sign-in picture</h2>
            <p class="m-0 text-xs text-ink-gray-7">Shown on the client sign-in page when no project render is marked. PNG, JPEG or WebP.</p>
            <div class="flex flex-wrap items-center gap-2">
              <img v-if="look.picture" :src="look.picture" alt="Default sign-in picture" class="h-12 w-20 rounded-4 border border-outline-gray-2 object-cover" data-testid="brand-picture-now" />
              <Button label="Upload a picture" icon-left="lucide-upload" class="max-md:!h-12" :disabled="busy" data-testid="brand-picture-pick" @click="pictureInput.click()" />
              <Button v-if="look.picture" label="Remove" class="max-md:!h-12" :disabled="busy" data-testid="brand-picture-clear" @click="clear('signin')" />
              <input ref="pictureInput" type="file" accept="image/png,image/jpeg,image/webp" class="hidden" data-testid="brand-picture-file" @change="pick('signin', $event)" />
            </div>
          </section>
        </div>

        <section class="cw-card flex min-w-0 flex-col gap-3 self-start px-4 py-3.5" aria-labelledby="sec-preview" data-testid="brand-preview">
          <h2 id="sec-preview" class="cw-card-title">Preview</h2>
          <div class="cw-brand-scope flex flex-col gap-3" :data-brand-main="draftLook.main ? '' : undefined" :style="vars">
            <div class="flex min-h-[52px] items-center gap-3 rounded-5 border border-outline-gray-2 bg-surface-base px-3" data-testid="preview-topbar">
              <BrandMark preview :company-name="draft.company" :logo-url="draftLogo" />
              <Button variant="solid" theme="blue" label="New project" class="ml-auto" tabindex="-1" aria-hidden="true" />
            </div>
            <div class="relative flex min-h-[220px] flex-col gap-4 overflow-hidden rounded-5 p-5 text-white" style="background: var(--brand-panel, oklch(0.205 0 0))" data-testid="preview-panel">
              <BrandMark preview on-dark :size="40" :company-name="draft.company" :logo-url="draftLogo" />
              <p class="cw-brand-font mb-0 mt-auto text-[22px] font-semibold leading-[1.25]">The project workspace for your team and its clients.</p>
              <Button variant="solid" theme="blue" label="Sign in" class="self-start" tabindex="-1" aria-hidden="true" />
              <!-- the credit follows the firm's name, as on the real pages, and nothing here turns it off -->
              <span v-if="draft.company" class="inline-flex items-center gap-1.5 text-[11px] leading-none text-white/70" data-testid="preview-credit">Powered by <span class="font-semibold">{{ product }}</span></span>
            </div>
          </div>
        </section>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <Button variant="solid" theme="blue" label="Save" class="max-md:!h-12" :disabled="busy || !hasChanges" :loading="busy" data-testid="brand-save" @click="save" />
        <Button :label="`Reset to ${product}`" class="max-md:!h-12" :disabled="busy" data-testid="brand-reset" @click="resetting = true" />
      </div>

      <Dialog v-model:open="resetting" title="Reset the brand?" :description="`The name, logo, colours, font and sign-in picture go back to ${product}'s.`">
        <template #actions="{ close }">
          <div class="flex justify-end gap-2">
            <Button label="Cancel" class="max-md:!h-12" data-testid="brand-reset-cancel" @click="close" />
            <Button variant="solid" theme="blue" :label="`Reset to ${product}`" class="max-md:!h-12" data-testid="brand-reset-confirm" @click="reset(close)" />
          </div>
        </template>
      </Dialog>
    </template>
  </component>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { Button, Dialog } from 'frappe-ui'
import PageHead from '../components/PageHead.vue'
import BrandMark, { FALLBACK_PRODUCT } from '../components/BrandMark.vue'
import { ApiError, call, upload } from '../api.js'
import { boot } from '../boot.js'
import { FONTS, applyLook, changedFields, draftOf, formOf, hexOf, looksOf, varsOf } from '../brand.js'

// embedded: the set-up wizard's Brand step (W2) shows this form without the page frame and hears every save.
defineProps({ embedded: Boolean })
const emit = defineEmits(['saved'])
const COLOURS = [
  { key: 'main_colour', label: 'Main colour', hint: 'Buttons and links' },
  { key: 'panel_colour', label: 'Panel colour', hint: 'The sign-in panel and the client header' },
]
const A = 'construction_core.brand.'
const product = FALLBACK_PRODUCT
// What the server holds; the form is the draft. The boot's brand is the first copy.
const brand = ref({ ...(boot.brand || {}) })
const form = reactive(formOf(brand.value))
const look = computed(() => looksOf(brand.value))
const draft = computed(() => draftOf(form, brand.value))
const draftLook = computed(() => looksOf(draft.value))
const vars = computed(() => varsOf(draftLook.value))
const draftLogo = computed(() => draftLook.value.logo)
const hasChanges = computed(() => Object.keys(changedFields(form, brand.value)).length > 0)
const busy = ref(false)
const error = ref('')
const done = ref('')
const resetting = ref(false)
const logoInput = ref(null)
const pictureInput = ref(null)

// One place for every call: the server's own message on a refusal (a colour too light, a file that is not a picture).
async function run(job, message) {
  busy.value = true
  error.value = ''
  done.value = ''
  try {
    const saved = await job()
    brand.value = { ...saved }
    Object.assign(form, formOf(brand.value))
    applyLook(looksOf(brand.value)) // colours and font now; the bar's name and logo on the next load
    done.value = message
    emit('saved')
    return true
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'The brand could not be saved. Try again.'
    return false
  } finally {
    busy.value = false
  }
}

const save = () => run(() => call(`${A}update`, changedFields(form, brand.value), { post: true }), 'Saved. The top bar shows the new name and logo the next time a page loads.')
const clear = (kind) => run(() => call(`${A}clear_image`, { kind }, { post: true }), 'Removed.')
async function reset(close) {
  if (await run(() => call(`${A}update`, { reset: 1 }, { post: true }), `Back to ${product}. The top bar changes the next time a page loads.`)) close()
}
async function pick(kind, event) {
  const file = event.target.files[0]
  event.target.value = '' // the same file may be chosen again after a refusal
  if (file) await run(() => upload(`${A}set_image`, { kind }, file), 'Saved.')
}
</script>
