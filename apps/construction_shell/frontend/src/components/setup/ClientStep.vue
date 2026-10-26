<template>
  <!-- P3-57 (W10): the first client contact, with the fields and the call of Settings → Client contacts (P3-19,
       onboarding.invites.create_invite) and the same one-time link panel. That dialog lives inside the project Settings
       page, so the form is repeated here, small, rather than pulled out of a file this step does not own. -->
  <section class="cw-card flex flex-col gap-3 px-4 py-3.5" aria-labelledby="sec-client" data-testid="client-step">
    <h2 id="sec-client" class="cw-card-title">Your client</h2>
    <p v-if="loaded && !list.length" class="m-0 text-sm text-ink-gray-8" data-testid="client-no-project">Make a project first (the step before), then invite a client to it. You can also do this later in the project's Settings.</p>
    <template v-else-if="shared">
      <p class="m-0 text-ink-green-7" data-testid="client-done">{{ shared.email ? `The invitation is sent to ${shared.email}.` : 'The link is ready.' }}</p>
      <SharePanel :share="shared.out" :email="shared.email" :company="company" />
      <Button label="Invite another contact" class="self-start max-md:!h-12" data-testid="client-another" @click="shared = null" />
    </template>
    <form v-else-if="list.length" class="flex flex-col gap-3" @submit.prevent="send">
      <p class="m-0 text-sm text-ink-gray-7">With an email, the link is emailed to them and works for 7 days. Without one, you get a link for a chat or a QR code that works for 3 days, and you approve each person who uses it.</p>
      <label v-if="list.length > 1" class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Project
        <select v-model="project" class="form-select h-12 w-full md:h-8" data-testid="client-project">
          <option v-for="p in list" :key="p.name" :value="p.name">{{ p.project_name }}</option>
        </select>
      </label>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Name
        <input v-model="form.name" maxlength="140" class="form-input h-12 w-full md:h-8" data-testid="client-name" />
      </label>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Email <span class="text-ink-gray-6">Optional. Example: maria.santos@example.com</span>
        <input v-model="form.email" type="email" class="form-input h-12 w-full md:h-8" data-testid="client-email" />
      </label>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Job title <span class="text-ink-gray-6">Seen by the project team only</span>
        <input v-model="form.title" maxlength="140" class="form-input h-12 w-full md:h-8" data-testid="client-title" />
      </label>
      <p v-if="error" role="alert" class="m-0 text-ink-red-7" data-testid="client-error">{{ error }}</p>
      <Button type="submit" variant="solid" theme="blue" :label="form.email.trim() ? 'Invite and email' : 'Make a link'" class="self-start max-md:!h-12" :loading="busy" :disabled="busy" data-testid="client-send" />
    </form>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Button } from 'frappe-ui'
import SharePanel from '../SharePanel.vue'
import { call as invitesCall } from '../../invites.js'
import { boot } from '../../boot.js'
import { post, projects, useRun } from './setup.js'

const emit = defineEmits(['saved'])
const company = boot.brand?.company || ''
const list = ref([])
const loaded = ref(false)
const project = ref('')
const form = reactive({ name: '', email: '', title: '' })
const shared = ref(null)
const { busy, error, run } = useRun()

onMounted(async () => {
  try {
    list.value = await projects()
    project.value = list.value[0]?.name || ''
  } catch (e) {
    error.value = e.message || 'The projects could not be read.'
  }
  loaded.value = true
})

async function send() {
  const email = form.email.trim()
  const got = await run(() => post(invitesCall('create_invite'), { project: project.value, email: email || null, full_name: form.name || null, job_title: form.title || null, mail_it: 1 }))
  if (!got) return
  shared.value = { out: got.out, email }
  Object.assign(form, { name: '', email: '', title: '' })
  emit('saved')
}
</script>
