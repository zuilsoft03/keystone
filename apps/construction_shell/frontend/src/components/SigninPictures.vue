<template>
  <!-- P3-34 (D-272, D-274): Settings → Sign-in page picture, for the project's managers. A render reaches the public
       client sign-in only when a manager marks it here; unticking takes it off at once. Built from the design's
       Settings cards (D-196: the owner approves the screenshots). -->
  <section class="cw-card overflow-hidden" aria-labelledby="sec-signin" data-testid="signin-pictures">
    <div class="flex flex-wrap items-center gap-2.5 px-4 py-3.5">
      <div class="min-w-0 flex-[1_1_240px]">
        <h2 id="sec-signin" class="cw-card-title">Sign-in page picture</h2>
        <p class="mt-1 text-sm text-ink-gray-7">Renders shown behind the client sign-in. Everyone who opens the sign-in page sees them, also people who are not signed in.</p>
      </div>
      <Button variant="outline" icon-left="lucide-image-plus" label="Add a picture" :disabled="busy || full" data-testid="signin-add" @click="open" />
    </div>
    <p v-if="error" role="alert" class="mx-4 mb-3 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-gray-9">{{ error }}</p>
    <p v-if="full" class="mx-4 mb-3 text-sm text-ink-gray-7">This project shows the most pictures it can ({{ limit }}). Remove one to add another.</p>

    <div v-for="p in pictures" :key="p.name" class="cw-list-row flex-wrap" data-testid="signin-row">
      <img :src="p.url" alt="" class="h-12 w-20 flex-none rounded-3 border border-outline-gray-1 object-cover" />
      <div class="min-w-0 flex-[1_1_220px]">
        <div class="truncate text-base text-ink-gray-9">{{ p.file_name || 'A file no longer in the project' }}</div>
        <input :value="p.caption" maxlength="80" class="form-input mt-1 h-7 w-full max-w-[360px] text-sm" placeholder="Caption, optional. Everyone sees it."
          :aria-label="`Caption for ${p.file_name}`" data-testid="signin-caption" @change="(e) => save(p, { caption: e.target.value })" />
      </div>
      <Switch :model-value="!!p.enabled" :aria-label="`Show ${p.file_name} on the sign-in page`" :disabled="busy" data-testid="signin-show" @update:model-value="(v) => save(p, { enabled: v ? 1 : 0 })" />
      <Badge v-if="p.enabled && !p.live" label="Not showing: the file is in the bin" theme="amber" />
      <Button variant="outline" theme="red" label="Remove" :disabled="busy" data-testid="signin-remove" @click="remove(p)" />
    </div>
    <p v-if="!pictures.length" class="border-t border-outline-gray-1 px-4 py-3 text-sm text-ink-gray-7">No picture yet. Clients see the standard night-city picture.</p>

    <Dialog v-model:open="picking" title="Add a sign-in picture" description="Upload a render, or pick one from this project's files. A copy without the photo's hidden details (such as its location) is what visitors see.">
      <!-- P3-36 (D-281): upload a render here; it is kept in the project's 02_Design/Renders and selected below -->
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <label class="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-4 border border-outline-gray-2 bg-surface-base px-2.5 text-base text-ink-gray-8 hover:bg-surface-gray-2 has-[:disabled]:cursor-not-allowed has-[:disabled]:text-ink-gray-4"
          data-testid="signin-upload">
          <span class="lucide-upload size-4" aria-hidden="true" />{{ uploading ? 'Uploading…' : 'Upload a render' }}
          <input type="file" accept="image/jpeg,image/png,image/webp" class="sr-only" :disabled="busy || uploading" data-testid="signin-upload-input" @change="uploadRender" />
        </label>
        <span class="text-xs text-ink-gray-7">JPG, PNG or WebP, up to 15 MB. Kept in the project's files under 02_Design/Renders.</span>
      </div>
      <p v-if="error" role="alert" class="mb-3 mt-0 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-gray-9" data-testid="signin-dialog-error">{{ error }}</p>
      <div v-if="!candidates.length" class="text-sm text-ink-gray-7">This project has no JPG, PNG or WebP image yet. Upload a render above.</div>
      <div v-else class="grid max-h-[320px] grid-cols-3 gap-2 overflow-y-auto p-0.5 max-sm:grid-cols-2" role="radiogroup" aria-label="Project images">
        <button v-for="c in candidates" :key="c.name" type="button" role="radio" :aria-checked="chosen === c.name" :disabled="c.marked"
          class="flex flex-col gap-1 rounded-4 border p-1 text-left disabled:cursor-not-allowed disabled:opacity-50"
          :class="chosen === c.name ? 'border-outline-blue-6 ring-2 ring-outline-blue-3' : 'border-outline-gray-2'" data-testid="signin-candidate" @click="chosen = c.name">
          <img :src="c.url" alt="" class="aspect-[16/10] w-full rounded-3 object-cover" loading="lazy" />
          <span class="truncate text-xs text-ink-gray-8">{{ c.file_name }}</span>
        </button>
      </div>
      <p v-if="chosenFile && !chosenFile.client_visible" class="mb-0 mt-3 rounded-4 bg-surface-amber-1 px-3 py-2 text-sm text-ink-gray-9" data-testid="signin-not-shared">
        This image is not shared with the client yet. On the sign-in page, everyone will see it.
      </p>
      <label class="mt-3 flex flex-col gap-1.5 text-xs text-ink-gray-7">Caption <span class="text-ink-gray-6">Optional. Everyone sees it, so leave it empty to keep the project's name private.</span>
        <input v-model="newCaption" maxlength="80" class="form-input w-full" data-testid="signin-new-caption" />
      </label>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button label="Cancel" @click="close" />
          <Button variant="solid" theme="blue" label="Show on the sign-in page" :disabled="busy || !chosen" data-testid="signin-mark" @click="markIt" />
        </div>
      </template>
    </Dialog>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Badge, Button, Dialog, Switch } from 'frappe-ui'
import { call, upload } from '../api.js'

const props = defineProps({ project: { type: String, required: true } })
const API = 'construction_core.signin_pictures.'
const pictures = ref([])
const candidates = ref([])
const limit = ref(6)
const busy = ref(false)
const error = ref('')
const picking = ref(false)
const chosen = ref('')
const newCaption = ref('')
const uploading = ref(false)
const full = computed(() => pictures.value.length >= limit.value)
const chosenFile = computed(() => candidates.value.find((c) => c.name === chosen.value))

async function load() {
  try {
    const out = await call(API + 'project_pictures', { project: props.project })
    pictures.value = out.pictures || []
    candidates.value = out.candidates || []
    limit.value = out.limit || 6
  } catch (e) {
    error.value = e.message || 'The pictures could not be loaded.'
  }
}

async function run(job) {
  busy.value = true
  error.value = ''
  try {
    await job()
  } catch (e) {
    error.value = e.message || 'That did not work.'
  } finally {
    busy.value = false
    await load()
  }
}

function open() {
  chosen.value = ''
  newCaption.value = ''
  picking.value = true
}

async function uploadRender(event) {
  const file = event.target.files && event.target.files[0]
  event.target.value = ''
  if (!file) return
  uploading.value = true
  error.value = ''
  try {
    const out = await upload(API + 'upload_render', { project: props.project }, file)
    await load()
    chosen.value = out.name // the new render, ready for a caption and Show
  } catch (e) {
    error.value = e.message || 'The image could not be uploaded.'
  } finally {
    uploading.value = false
  }
}

const markIt = () => run(async () => {
  await call(API + 'mark', { project: props.project, file: chosen.value, caption: newCaption.value }, { post: true })
  picking.value = false
})
const save = (p, values) => run(() => call(API + 'update', { picture: p.name, ...values }, { post: true }))
const remove = (p) => run(() => call(API + 'remove', { picture: p.name }, { post: true }))

load()
</script>
