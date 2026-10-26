<template>
  <!-- P3-57 (W9): rows of name, email, role and job title, sent at once through people.invite_staff_many (at most 50). Each
       row gets its own answer, so one wrong address does not stop the others. The first project can be ticked (D-235 allows one). -->
  <section class="cw-card flex flex-col gap-3 px-4 py-3.5" aria-labelledby="sec-team" data-testid="team-step">
    <h2 id="sec-team" class="cw-card-title">Your team</h2>
    <label v-if="project" class="flex min-h-12 items-center gap-2.5 text-sm text-ink-gray-9">
      <input v-model="addToProject" type="checkbox" class="form-checkbox" data-testid="team-project" /> Add them to {{ project.project_name }}
    </label>
    <form class="flex flex-col gap-3" novalidate @submit.prevent="send">
      <fieldset v-for="(r, i) in rows" :key="r.key" class="m-0 flex flex-col gap-2 rounded-5 border border-outline-gray-1 p-3" :data-testid="`team-row-${i}`">
        <legend class="px-1 text-xs text-ink-gray-7">Person {{ i + 1 }}</legend>
        <div class="grid gap-2 sm:grid-cols-2">
          <input v-model="r.full_name" maxlength="140" aria-label="Name" placeholder="Name" class="form-input h-12 w-full md:h-8" :data-testid="`team-name-${i}`" />
          <input v-model="r.email" type="email" aria-label="Email" placeholder="Email" class="form-input h-12 w-full md:h-8" :data-testid="`team-email-${i}`" />
          <select v-model="r.role" aria-label="Role" class="form-select h-12 w-full md:h-8" :data-testid="`team-role-${i}`">
            <option v-for="role in ROLES" :key="role" :value="role">{{ role }}</option>
          </select>
          <input v-model="r.job_title" maxlength="140" aria-label="Job title" placeholder="Job title (optional)" class="form-input h-12 w-full md:h-8" :data-testid="`team-title-${i}`" />
        </div>
        <p v-if="r.result" :class="r.result.ok ? 'text-ink-green-7' : 'text-ink-red-7'" class="m-0 text-sm" :role="r.result.ok ? undefined : 'alert'" :data-testid="`team-result-${i}`">
          {{ r.result.ok ? 'Invitation sent.' : r.result.error }}
        </p>
      </fieldset>
      <div class="flex flex-wrap gap-2">
        <Button label="Add a person" class="max-md:!h-12" :disabled="busy || rows.length >= 50" data-testid="team-add" @click="add" />
        <Button type="submit" variant="solid" theme="blue" label="Send the invitations" class="max-md:!h-12" :loading="busy" :disabled="busy || !filled.length" data-testid="team-send" />
      </div>
    </form>
    <p v-if="error" role="alert" class="m-0 text-ink-red-7" data-testid="team-error">{{ error }}</p>
    <p v-if="done" class="m-0 text-ink-green-7" data-testid="team-done">{{ done }}</p>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Button } from 'frappe-ui'
import { post, projects, useRun } from './setup.js'

const emit = defineEmits(['saved'])
const ROLES = ['Construction Staff', 'Construction Manager']
let n = 0
const blank = () => reactive({ key: ++n, full_name: '', email: '', role: 'Construction Staff', job_title: '', result: null })
const rows = ref([blank(), blank(), blank()])
const project = ref(null)
const addToProject = ref(true)
const { busy, error, done, run } = useRun()
const filled = computed(() => rows.value.filter((r) => r.email.trim() && !r.result?.ok)) // a row that went is not sent twice

onMounted(async () => {
  try {
    project.value = (await projects())[0] || null
  } catch {
    project.value = null // invitations then carry no project
  }
})

const add = () => rows.value.push(blank())

async function send() {
  const sending = filled.value
  const body = sending.map((r) => ({ full_name: r.full_name.trim(), email: r.email.trim(), role: r.role, job_title: r.job_title.trim(), project: project.value && addToProject.value ? project.value.name : null }))
  const got = await run(() => post('construction_core.accounts.people.invite_staff_many', { rows: body }))
  if (!got) return
  const results = got.out || []
  sending.forEach((r, i) => { r.result = results[i] || null })
  // A row that went stays on screen with its answer; a row that failed keeps its text so it can be fixed and sent again.
  const sent = results.filter((x) => x.ok).length
  done.value = sent ? `${sent} ${sent === 1 ? 'invitation' : 'invitations'} sent.` : ''
  if (sent) emit('saved')
  if (sent < sending.length) error.value = `${sending.length - sent} could not be sent. Read the line under each one.`
}
</script>
