<template>
  <!-- P3-21 (D-189, D-235): the People page, for System Managers. Built from the design's Settings card, list rows and
       tokens (D-196). The server checks System Manager on every call and refuses Administrator and System Managers. -->
  <main class="flex max-w-5xl flex-1 flex-col gap-3.5 px-6 py-5" data-testid="people-page">
    <PageHead crumb="Workspace / People" title="People" :meta="data ? `${data.people.length} accounts` : ''">
      <Button variant="outline" size="md" icon-left="lucide-users" label="Invite several" :disabled="!data || !data.mail_ready" data-testid="open-many" @click="openMany" />
      <Button variant="solid" theme="blue" size="md" icon-left="lucide-user-plus" label="Invite a team member" :disabled="!data || !data.mail_ready" data-testid="open-staff-invite" @click="openInvite" />
    </PageHead>
    <p v-if="error" role="alert" class="text-ink-red-7" data-testid="people-error">{{ error }}</p>
    <p v-if="done" class="text-ink-green-7" data-testid="people-done">{{ done }}</p>
    <p v-if="!data && !error" class="text-ink-gray-7">Loading…</p>

    <template v-if="data">
      <p v-if="!data.mail_ready" class="rounded-4 bg-surface-amber-1 px-3 py-2 text-sm text-ink-gray-9" data-testid="people-mail">Email isn't set up yet: team invitations and reset emails are paused.</p>

      <section class="cw-card flex flex-col gap-2.5 px-4 py-3.5" aria-labelledby="sec-2step" data-testid="two-step-requirement">
        <h2 id="sec-2step" class="cw-card-title">Two-step sign-in</h2>
        <p class="m-0 text-sm text-ink-gray-7">Each person may turn it on from their account menu. You can require it.</p>
        <div class="cw-tabbuttons self-start" role="group" aria-label="Who must use two-step sign-in">
          <button v-for="[id, label] in SCOPES" :key="id" type="button" class="cw-tabbutton" :aria-pressed="data.two_step.requirement === id"
            :disabled="busy" :data-testid="`require-${id}`" @click="setRequirement(id)">{{ label }}</button>
        </div>
        <p v-if="data.two_step.requirement !== 'nobody' && data.two_step.not_set_up.length" class="m-0 text-sm text-ink-gray-8" data-testid="not-set-up">
          Not set up yet ({{ data.two_step.not_set_up.length }}): their next sign-in emails them a setup link.
        </p>
      </section>

      <section class="cw-card overflow-hidden" aria-labelledby="sec-people">
        <div class="flex flex-wrap items-center gap-2.5 px-4 py-3">
          <h2 id="sec-people" class="cw-card-title flex-1">Accounts</h2>
          <div class="cw-tabbuttons" role="group" aria-label="Show">
            <button v-for="[id, label] in FILTERS" :key="id" type="button" class="cw-tabbutton" :aria-pressed="filter === id" :data-testid="`filter-${id}`" @click="filter = id">
              {{ label }} <span class="text-ink-gray-7">{{ countOf(id) }}</span>
            </button>
          </div>
        </div>
        <template v-if="filter !== 'invites'">
          <div v-for="p in shown" :key="p.person" class="cw-list-row flex-wrap" data-testid="person-row" :data-person="p.person">
            <Avatar :label="p.full_name" size="xl" />
            <div class="min-w-0 flex-[1_1_220px]">
              <div class="truncate text-base text-ink-gray-9">{{ p.full_name }}<template v-if="p.is_me"> (you)</template></div>
              <div class="truncate text-sm text-ink-gray-7">{{ [p.email, p.role || (p.kind === 'client' ? 'Client' : ''), p.job_title, projectsLine(p)].filter(Boolean).join(' · ') }}</div>
            </div>
            <Badge v-if="!p.enabled" label="Turned off" theme="red" />
            <Badge v-if="p.two_step" label="Two-step on" theme="green" />
            <Badge v-if="p.kind === 'protected'" label="Managed in Desk" theme="gray" data-testid="protected" />
            <Dropdown v-else :options="actionsOf(p)" align="end">
              <Button variant="outline" label="Manage" :disabled="busy" data-testid="manage" />
            </Dropdown>
          </div>
          <p v-if="!shown.length" class="border-t border-outline-gray-1 px-4 py-3 text-sm text-ink-gray-7">Nobody here.</p>
        </template>
        <template v-else>
          <div v-for="i in data.invites" :key="i.name" class="cw-list-row flex-wrap" data-testid="invite-row">
            <Avatar :label="i.full_name || i.email || 'Open link'" size="xl" />
            <div class="min-w-0 flex-[1_1_220px]">
              <div class="truncate text-base text-ink-gray-9">{{ i.full_name || i.email || 'Open link' }}</div>
              <div class="truncate text-sm text-ink-gray-7">{{ [i.kind === 'Staff' ? i.role : 'Client', i.email, projectName(i.project), i.waiting ? `${i.waiting} waiting` : ''].filter(Boolean).join(' · ') }}</div>
            </div>
            <template v-if="i.kind === 'Staff'">
              <Button variant="outline" label="New link" :disabled="busy || !data.mail_ready" data-testid="staff-renew" @click="renew(i)" />
              <Button variant="outline" theme="red" label="Cancel" :disabled="busy" data-testid="staff-revoke" @click="revoke(i)" />
            </template>
            <Badge v-else label="In the project's Settings" theme="gray" />
          </div>
          <p v-if="!data.invites.length" class="border-t border-outline-gray-1 px-4 py-3 text-sm text-ink-gray-7">No pending invitation.</p>
        </template>
      </section>
    </template>

    <Dialog v-model:open="inviting" title="Invite a team member" description="They get an email with a link to set up their account. It works for 7 days.">
      <form id="staff-invite-form" class="flex flex-col gap-3" @submit.prevent="invite">
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Name
          <input v-model="form.full_name" maxlength="140" class="form-input w-full" data-testid="staff-name" />
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Email
          <input v-model="form.email" type="email" required class="form-input w-full" data-testid="staff-email" />
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Role
          <select v-model="form.role" class="form-select w-full" data-testid="staff-role">
            <option v-for="r in data?.roles || []" :key="r" :value="r">{{ r }}</option>
          </select>
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Job title <span class="text-ink-gray-6">Optional; the team sees it</span>
          <input v-model="form.job_title" maxlength="140" class="form-input w-full" data-testid="staff-title" />
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Project <span class="text-ink-gray-6">Optional; more can be added later</span>
          <select v-model="form.project" class="form-select w-full" data-testid="staff-project">
            <option value="">No project yet</option>
            <option v-for="pr in data?.projects || []" :key="pr.name" :value="pr.name">{{ pr.project_name }}</option>
          </select>
        </label>
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button label="Cancel" @click="close" />
          <Button type="submit" form="staff-invite-form" variant="solid" theme="blue" label="Invite and email" :disabled="busy" data-testid="staff-invite" />
        </div>
      </template>
    </Dialog>

    <Dialog v-model:open="many" title="Invite several" description="One person on each row, up to 50. Each row is checked on its own, and each gets an email with a link that works for 7 days.">
      <form id="many-form" class="flex max-h-[60vh] flex-col gap-3 overflow-y-auto" @submit.prevent="inviteMany">
        <fieldset v-for="(r, i) in rows" :key="i" class="m-0 flex flex-col gap-2 rounded-4 border border-outline-gray-2 p-2.5" data-testid="many-row">
          <div class="grid gap-2 sm:grid-cols-2">
            <input v-model="r.full_name" maxlength="140" placeholder="Name" aria-label="Name" class="form-input h-12 w-full md:h-8" data-testid="many-name" />
            <input v-model="r.email" type="email" placeholder="Email" aria-label="Email" class="form-input h-12 w-full md:h-8" data-testid="many-email" />
            <select v-model="r.role" aria-label="Role" class="form-select h-12 w-full md:h-8" data-testid="many-role">
              <option v-for="x in data?.roles || []" :key="x" :value="x">{{ x }}</option>
            </select>
            <input v-model="r.job_title" maxlength="140" placeholder="Job title" aria-label="Job title" class="form-input h-12 w-full md:h-8" data-testid="many-title" />
            <select v-model="r.project" aria-label="First project" class="form-select h-12 w-full md:h-8 sm:col-span-2" data-testid="many-project">
              <option value="">No project yet</option>
              <option v-for="pr in data?.projects || []" :key="pr.name" :value="pr.name">{{ pr.project_name }}</option>
            </select>
          </div>
          <p v-if="results[i]" class="m-0 text-sm text-ink-red-7" role="alert" data-testid="many-result">{{ results[i] }}</p>
          <Button v-if="rows.length > 1" label="Remove row" class="self-start max-md:!h-12" @click="removeRow(i)" />
        </fieldset>
        <Button v-if="rows.length < 50" label="Add a row" icon-left="lucide-plus" class="self-start max-md:!h-12" data-testid="many-add" @click="rows.push(blankRow())" />
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button label="Close" @click="close" />
          <Button type="submit" form="many-form" variant="solid" theme="blue" label="Invite and email" :disabled="busy || !rows.some((r) => r.email.trim())" data-testid="many-send" />
        </div>
      </template>
    </Dialog>

    <Dialog v-model:open="titleOpen" :title="`Job title of ${target?.full_name || ''}`" description="The team sees it on People and on a project's Team.">
      <form id="title-form" @submit.prevent="saveTitle">
        <input v-model="titleChoice" maxlength="140" aria-label="Job title" class="form-input h-12 w-full md:h-8" data-testid="job-title" />
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button label="Cancel" @click="close" />
          <Button type="submit" form="title-form" variant="solid" theme="blue" label="Save" :disabled="busy" data-testid="save-title" />
        </div>
      </template>
    </Dialog>

    <Dialog v-model:open="sharing" title="Share the invitation">
      <SharePanel v-if="shared" :share="shared" :email="shared.email" :company="''" />
      <template #actions="{ close }">
        <div class="flex justify-end"><Button label="Done" data-testid="share-done" @click="close" /></div>
      </template>
    </Dialog>

    <Dialog v-model:open="roleOpen" :title="`Role of ${target?.full_name || ''}`">
      <div class="flex flex-col gap-2">
        <label v-for="r in data?.roles || []" :key="r" class="flex items-center gap-2 text-base text-ink-gray-9">
          <input v-model="roleChoice" type="radio" :value="r" class="form-radio" :data-testid="`role-${r}`" /> {{ r }}
        </label>
      </div>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button label="Cancel" @click="close" />
          <Button variant="solid" theme="blue" label="Save" :disabled="busy || !roleChoice" data-testid="save-role" @click="saveRole" />
        </div>
      </template>
    </Dialog>

    <Dialog v-model:open="projectsOpen" :title="`Projects of ${target?.full_name || ''}`">
      <div class="flex max-h-[50vh] flex-col gap-1.5 overflow-y-auto">
        <label v-for="pr in data?.projects || []" :key="pr.name" class="flex items-center gap-2 text-base text-ink-gray-9">
          <input type="checkbox" class="form-checkbox" :checked="target?.projects.includes(pr.name)" :disabled="busy || target?.kind === 'client'"
            :data-testid="`project-${pr.name}`" @change="toggleProject(pr.name, $event.target.checked)" /> {{ pr.project_name }}
        </label>
      </div>
      <p v-if="target?.kind === 'client'" class="mt-2 text-sm text-ink-gray-7">A client joins a project through an invitation in its Settings.</p>
      <template #actions="{ close }">
        <div class="flex justify-end"><Button label="Done" @click="close" /></div>
      </template>
    </Dialog>
  </main>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Avatar, Badge, Button, Dialog, Dropdown } from 'frappe-ui'
import PageHead from '../components/PageHead.vue'
import SharePanel from '../components/SharePanel.vue'
import { call } from '../api.js'
import { countOf as count, filterPeople, projectsLine as line } from '../people.js'

const M = 'construction_core.accounts.people.'
const SCOPES = [['nobody', 'Each person chooses'], ['team', 'Required for the team'], ['everyone', 'Required for everyone']]
const FILTERS = [['team', 'Team'], ['clients', 'Clients'], ['off', 'Turned off'], ['invites', 'Invitations']]
const data = ref(null)
const error = ref('')
const done = ref('')
const busy = ref(false)
const filter = ref('team')
const inviting = ref(false)
const form = reactive({ full_name: '', email: '', role: 'Construction Staff', job_title: '', project: '' })
const sharing = ref(false)
const shared = ref(null)
const target = ref(null)
const roleOpen = ref(false)
const roleChoice = ref('')
const projectsOpen = ref(false)
const titleOpen = ref(false)
const titleChoice = ref('')
const many = ref(false)
const blankRow = () => ({ full_name: '', email: '', role: 'Construction Staff', job_title: '', project: '' })
const rows = ref([blankRow()])
const results = ref([]) // the reason a row failed, by row

const shown = computed(() => filterPeople(data.value?.people || [], filter.value))
const countOf = (id) => (id === 'invites' ? data.value?.invites.length || 0 : count(data.value?.people || [], id))
const projectName = (name) => data.value?.projects.find((p) => p.name === name)?.project_name || ''
const projectsLine = (p) => line(p, data.value?.projects || [])

async function load() {
  try {
    data.value = await call(`${M}people`)
    if (target.value) target.value = data.value.people.find((p) => p.person === target.value.person) || null
  } catch (e) {
    error.value = e.message || 'That did not work.'
  }
}

async function run(job, message) {
  busy.value = true
  error.value = ''
  done.value = ''
  try {
    const out = await job()
    done.value = message || ''
    return out
  } catch (e) {
    error.value = e.message || 'That did not work.'
  } finally {
    busy.value = false
    await load()
  }
}

function post(name, args) {
  return call(`${M}${name}`, args, { post: true })
}

function actionsOf(p) {
  const out = []
  if (p.kind === 'team') out.push({ label: 'Change role', icon: 'lucide-badge-check', onClick: () => openRole(p) })
  if (p.kind === 'team') out.push({ label: 'Job title', icon: 'lucide-briefcase', onClick: () => openTitle(p) })
  out.push({ label: 'Projects', icon: 'lucide-folder', onClick: () => openProjects(p) })
  if (p.enabled && data.value.mail_ready) out.push({ label: 'Send password reset email', icon: 'lucide-mail', onClick: () => reset(p) })
  if (p.two_step) out.push({ label: 'Switch off two-step sign-in (lost phone)', icon: 'lucide-shield-off', onClick: () => twoStepOff(p) })
  out.push(p.enabled
    ? { label: 'Turn access off', icon: 'lucide-user-x', onClick: () => access(p, 0) }
    : { label: 'Turn access back on', icon: 'lucide-user-check', onClick: () => access(p, 1) })
  return out
}

function openInvite() {
  Object.assign(form, { full_name: '', email: '', role: 'Construction Staff', job_title: '', project: '' })
  inviting.value = true
}

async function invite() {
  const email = form.email.trim()
  const out = await run(() => post('invite_staff', { ...form, email, job_title: form.job_title.trim() || null, project: form.project || null, mail_it: 1 }), `Invitation sent to ${email}.`)
  if (out) {
    inviting.value = false
    shared.value = { ...out, email }
    sharing.value = true
  }
}

async function renew(i) {
  const out = await run(() => post('renew_staff_invite', { invite: i.name, mail_it: 1 }), `A new link went to ${i.email}.`)
  if (out) {
    shared.value = { ...out, email: i.email }
    sharing.value = true
  }
}

function revoke(i) {
  if (window.confirm(`Cancel the invitation for ${i.email}? Its link stops working.`)) run(() => post('revoke_staff_invite', { invite: i.name }), 'Invitation cancelled.')
}

function openMany() {
  rows.value = [blankRow()]
  results.value = []
  many.value = true
}

function removeRow(i) {
  rows.value.splice(i, 1)
  results.value.splice(i, 1)
}

// Rows with no email are skipped. The server answers each row alone, so one bad row never stops the others: rows that
// went through are dropped, the failed ones stay with their reason, to fix and send again.
async function inviteMany() {
  const sent = rows.value.filter((r) => r.email.trim())
  const out = await run(() => post('invite_staff_many', { rows: sent.map((r) => ({ ...r, email: r.email.trim(), job_title: r.job_title.trim() || null, project: r.project || null })) }))
  if (!out) return
  const res = out.results || out
  const kept = sent.filter((_, i) => !res[i]?.ok)
  done.value = `${sent.length - kept.length} of ${sent.length} invitations sent.`
  results.value = res.filter((x) => !x.ok).map((x) => x.error || 'That did not work.')
  rows.value = kept.length ? kept : [blankRow()]
  if (!kept.length) many.value = false
}

function openTitle(p) {
  target.value = p
  titleChoice.value = p.job_title || ''
  titleOpen.value = true
}

async function saveTitle() {
  if (await run(() => post('set_job_title', { person: target.value.person, job_title: titleChoice.value.trim() }), 'Job title saved.')) titleOpen.value = false
}

function openRole(p) {
  target.value = p
  roleChoice.value = p.role || ''
  roleOpen.value = true
}

async function saveRole() {
  if (await run(() => post('set_role', { person: target.value.person, role: roleChoice.value }), 'Role saved.')) roleOpen.value = false
}

function openProjects(p) {
  target.value = p
  projectsOpen.value = true
}

function toggleProject(project, on) {
  run(() => post('project_access', { person: target.value.person, project, on: on ? 1 : 0 }), on ? 'Added to the project.' : 'Removed from the project.')
}

function access(p, on) {
  const ask = on ? `Turn ${p.full_name}'s access back on?` : `Turn ${p.full_name}'s access off? They are signed out everywhere at once, and their invitations stop.`
  if (window.confirm(ask)) run(() => post('set_access', { person: p.person, on }), on ? 'Access turned on.' : 'Access turned off.')
}

function reset(p) {
  if (window.confirm(`Email ${p.email} a link to choose a new password?`)) run(() => post('send_reset', { person: p.person }), 'Reset email sent.')
}

function twoStepOff(p) {
  if (window.confirm(`Switch off two-step sign-in for ${p.full_name}? Do this only when they lost their phone.`)) run(() => post('two_step_off', { person: p.person }), 'Two-step sign-in switched off.')
}

function setRequirement(scope) {
  if (scope === data.value.two_step.requirement) return
  const ask = scope === 'nobody' ? 'Let each person choose two-step sign-in?' : `Require two-step sign-in ${scope === 'team' ? 'for the team' : 'for everyone'}? Whoever has not set it up gets a setup email at their next sign-in.`
  if (window.confirm(ask)) run(() => call('construction_core.accounts.two_step.set_requirement', { scope }, { post: true }), 'Saved.')
}

onMounted(load)
</script>
