<template>
  <div class="flex max-w-5xl flex-col gap-3.5 px-6 py-5" data-testid="section-page">
    <PageHead crumb="Workspace / Settings" title="Workspace settings" :meta="frame.project.name">
      <template v-if="clientEntry">
        <Dropdown v-if="clientEntry.options" :options="clientEntry.options" align="end">
          <Button variant="outline" size="md" icon-left="lucide-monitor" label="View portal as client" data-testid="view-as-client" />
        </Dropdown>
        <Button v-else variant="outline" size="md" icon-left="lucide-monitor" label="View portal as client" :route="clientEntry.route" data-testid="view-as-client" />
      </template>
      <Button v-if="canEdit && config" variant="solid" theme="blue" size="md" label="Save" :disabled="busy" data-testid="save-settings" @click="save" />
    </PageHead>
    <p v-if="closed.closed" class="rounded-4 bg-surface-amber-1 px-3 py-2 text-sm text-ink-gray-9" data-testid="closed-note">{{ closedLine }}</p>
    <p v-else-if="!canEdit" class="rounded-4 bg-surface-gray-2 px-3 py-2 text-sm text-ink-gray-8" data-testid="read-only-note">Only the project's managers can change these settings.</p>
    <p v-if="error" class="text-ink-red-7" role="alert" data-testid="error">{{ error }}</p>
    <p v-if="saved" class="text-ink-green-7" data-testid="saved">Saved</p>

    <template v-if="config">
      <section class="cw-card overflow-hidden" aria-labelledby="sec-portal">
        <div class="border-b border-outline-gray-1 px-4 py-3.5">
          <h2 id="sec-portal" class="cw-card-title">Client portal</h2>
          <p class="mt-1 text-sm text-ink-gray-7">Whether this project's clients can sign in, and what their portal shows.</p>
        </div>
        <div class="px-2 py-2">
          <Switch :model-value="Boolean(config.client_portal_enabled)" :disabled="!canEdit" padded
            label="The project's clients can sign in to its portal" data-testid="portal-enabled"
            @update:model-value="(v) => (config.client_portal_enabled = v ? 1 : 0)" />
        </div>
        <div class="overflow-x-auto">
          <div class="min-w-[520px]" role="table" aria-label="Workspace sections">
            <div role="row" class="cw-list-head grid grid-cols-[minmax(140px,1fr)_150px_minmax(220px,1.4fr)] text-[11px] font-semibold uppercase tracking-[0.06em]">
              <span role="columnheader">Section</span><span role="columnheader">On for the team</span><span role="columnheader">Shown in the client portal</span>
            </div>
            <div v-for="row in config.sidebar_sections" :key="row.name" role="row" class="cw-list-row grid grid-cols-[minmax(140px,1fr)_150px_minmax(220px,1.4fr)] py-0.5"
              data-testid="section-row" :data-section="row.section">
              <span role="cell" class="text-base text-ink-gray-9">{{ sectionLabel(row.section, mode) }}</span>
              <span role="cell">
                <Switch :model-value="Boolean(row.visible)" :disabled="!canEdit" :aria-label="`${sectionLabel(row.section, mode)} on for the team`"
                  @update:model-value="(v) => (row.visible = v ? 1 : 0)" />
              </span>
              <span role="cell">
                <Switch v-if="CLIENT_SECTIONS.has(row.section)" :model-value="Boolean(row.client_visible)" :disabled="!canEdit"
                  :aria-label="`${sectionLabel(row.section, mode)} shown in the client portal`" data-testid="client-visible"
                  @update:model-value="(v) => (row.client_visible = v ? 1 : 0)" />
                <Badge v-else label="Never shown to clients" />
              </span>
            </div>
          </div>
        </div>
        <p class="border-t border-outline-gray-1 px-4 py-2.5 text-sm text-ink-gray-7">Switching the portal or a section off also removes what was shared with the clients there.</p>
      </section>

      <section class="cw-card flex flex-col gap-3 px-4 py-3.5" aria-labelledby="sec-conv">
        <h2 id="sec-conv" class="cw-card-title">Client conversations</h2>
        <Switch :model-value="Boolean(config.seen_receipts)" :disabled="!canEdit" padded class="-mx-2"
          label="Show “Seen by” avatars to staff" description="Staff see which client contacts have read a message. Clients never see this."
          data-testid="seen-receipts" @update:model-value="(v) => (config.seen_receipts = v ? 1 : 0)" />
        <div class="flex gap-2.5 rounded-4 border border-outline-amber-2 bg-surface-amber-1 px-3 py-2.5 text-sm text-ink-gray-9">
          <span class="lucide-lock mt-0.5 size-4 flex-none text-ink-amber-7" aria-hidden="true" />
          <span>Always staff-only, whatever the settings: the typing indicator, pinned notes and staff-only notes inside a client conversation.</span>
        </div>
      </section>
    </template>

    <section class="cw-card overflow-hidden" aria-labelledby="sec-contacts">
      <div class="flex flex-wrap items-center gap-2.5 px-4 py-3.5">
        <div class="min-w-0 flex-[1_1_240px]">
          <h2 id="sec-contacts" class="cw-card-title">Client contacts</h2>
          <p class="mt-1 text-sm text-ink-gray-7">People at the client who can sign in to this project's portal.</p>
        </div>
        <Button v-if="canClients" variant="solid" theme="blue" size="md" label="Invite contact" :disabled="!mailReady" data-testid="open-invite" @click="openInvite" />
      </div>
      <p v-if="canClients && !mailReady" class="mx-4 mb-3 rounded-4 bg-surface-amber-1 px-3 py-2 text-sm text-ink-gray-9" data-testid="mail-paused">
        Email isn't set up yet, so invitations are paused. A System Manager sets up outgoing email first.
      </p>

      <template v-if="waiting.length">
        <div class="cw-list-head border-t border-outline-gray-1 text-[11px] font-semibold uppercase tracking-[0.06em]">Waiting for you</div>
        <div v-for="r in waiting" :key="r.name" class="cw-list-row flex-wrap" data-testid="waiting-row">
          <Avatar :label="r.full_name || r.email" size="xl" />
          <div class="min-w-0 flex-[1_1_220px]">
            <div class="truncate text-base text-ink-gray-9">{{ r.email }} <Badge label="Email checked" theme="green" /></div>
            <div class="truncate text-sm text-ink-gray-7">As they typed it: {{ [r.full_name, r.mobile_no, r.company_name].filter(Boolean).join(' · ') }}</div>
          </div>
          <template v-if="canClients">
            <Button variant="solid" theme="blue" label="Approve" :disabled="busy" data-testid="approve" @click="decide(r, 1)" />
            <Button variant="outline" theme="red" label="Decline" :disabled="busy" data-testid="decline" @click="decide(r, 0)" />
          </template>
        </div>
      </template>

      <div v-for="c in clients" :key="c.name" class="cw-list-row flex-wrap" data-testid="client-contact">
        <Avatar :label="detailOf(c).full_name || c.full_name || c.user" :image="c.image || undefined" size="xl" :theme="themeOf(c.user)" />
        <div class="min-w-0 flex-[1_1_200px]">
          <div class="truncate text-base text-ink-gray-9">{{ detailOf(c).full_name || c.full_name || c.user }}</div>
          <div class="truncate text-sm text-ink-gray-7" data-testid="contact-line">{{ c.email || c.user }}<template v-if="c.job_title"> · {{ c.job_title }}</template><template v-if="detailOf(c).mobile_no"> · {{ detailOf(c).mobile_no }}</template><template v-if="detailOf(c).company_name"> · {{ detailOf(c).company_name }}</template></div>
        </div>
        <Button v-if="canClients" variant="outline" label="Edit" :disabled="busy" data-testid="edit-contact" @click="startEdit(c)" />
        <Button v-if="canClients" variant="outline" theme="red" label="Remove" :disabled="busy" @click="removeClient(c)" />
      </div>

      <div v-for="i in invited" :key="i.name" class="cw-list-row flex-wrap" data-testid="invited-row">
        <Avatar :label="whoOf(i).title" size="xl" />
        <div class="min-w-0 flex-[1_1_200px]">
          <div class="truncate text-base text-ink-gray-9">{{ whoOf(i).title }}</div>
          <div class="truncate text-sm text-ink-gray-7">{{ [whoOf(i).line, untilOf(i), mailLine(i)].filter(Boolean).join(' · ') }}</div>
        </div>
        <Badge :label="badgeOf(i).label" :theme="badgeOf(i).theme" />
        <template v-if="canClients">
          <Button variant="outline" label="New link" :disabled="busy || !mailReady" data-testid="renew" @click="renew(i)" />
          <Button variant="outline" theme="red" label="Cancel" :disabled="busy" data-testid="revoke" @click="revoke(i)" />
        </template>
      </div>
      <p v-if="!clients.length && !invited.length && !waiting.length" class="border-t border-outline-gray-1 px-4 py-3 text-sm text-ink-gray-7">No client contact yet.</p>
    </section>

    <section class="cw-card overflow-hidden" aria-labelledby="sec-team" data-testid="team-section">
      <div class="flex flex-wrap items-center gap-2.5 px-4 py-3.5">
        <div class="min-w-0 flex-[1_1_240px]">
          <h2 id="sec-team" class="cw-card-title">Team</h2>
          <p class="mt-1 text-sm text-ink-gray-7">The team accounts on this project. A client joins through an invitation above, not here.</p>
        </div>
      </div>
      <p v-if="teamError" role="alert" class="mx-4 mb-3 text-sm text-ink-red-7" data-testid="team-error">{{ teamError }}</p>
      <div v-for="m in team" :key="m.user" class="cw-list-row flex-wrap" data-testid="team-member" :data-user="m.user">
        <Avatar :label="m.full_name || m.user" size="xl" />
        <div class="min-w-0 flex-[1_1_200px]">
          <div class="truncate text-base text-ink-gray-9">{{ m.full_name || m.user }}</div>
          <div class="truncate text-sm text-ink-gray-7">{{ [m.job_title, m.role].filter(Boolean).join(' · ') }}</div>
        </div>
        <Button v-if="canTeam && m.role !== 'System Manager'" variant="outline" theme="red" label="Remove" class="max-md:!h-12" :disabled="busy" data-testid="team-remove" @click="removeMember(m)" />
      </div>
      <p v-if="!team.length" class="border-t border-outline-gray-1 px-4 py-3 text-sm text-ink-gray-7">No team member yet.</p>
      <form v-if="canTeam" class="flex flex-wrap items-end gap-2.5 border-t border-outline-gray-1 px-4 py-3" @submit.prevent="addMember">
        <label class="flex min-w-0 flex-[1_1_240px] flex-col gap-1.5 text-xs text-ink-gray-7">Email of a team member
          <input v-model="teamEmail" type="email" required class="form-input h-12 w-full md:h-8" data-testid="team-email" />
        </label>
        <Button type="submit" variant="solid" theme="blue" label="Add to the team" class="max-md:!h-12" :disabled="busy" data-testid="team-add" />
      </form>
    </section>

    <ApprovalSettings :project="project" />

    <ApprovalSteps />

    <SigninPictures v-if="canClients" :project="project" />

    <section v-if="frame.can_manage_portal && !closed.closed" class="cw-card flex flex-wrap items-center gap-2.5 px-4 py-3.5" aria-labelledby="sec-close" data-testid="close-section">
      <div class="min-w-0 flex-[1_1_300px]">
        <h2 id="sec-close" class="cw-card-title">Close project</h2>
        <p class="mt-1 text-sm text-ink-gray-7">When the work is handed over. After you close it, the chat is closed for everyone, clients can only read for 90 days, and the team can still edit documents.</p>
      </div>
      <Button variant="outline" theme="red" label="Close project" class="max-md:!h-12" :disabled="busy" data-testid="close-project" @click="closeProject" />
    </section>

    <Dialog v-model:open="inviting" title="Invite a client contact" description="With an email, the link is emailed to them and works for 7 days. Without one, you get a link for a chat or a QR code that works for 3 days, and you approve each person who uses it.">
      <form id="invite-form" class="flex flex-col gap-3" @submit.prevent="invite">
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Name
          <input v-model="newName" maxlength="140" class="form-input w-full" data-testid="invite-name" />
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Email <span class="text-ink-gray-6">Optional. Example: maria.santos@example.com</span>
          <input v-model="newEmail" type="email" class="form-input w-full" data-testid="invite-email" />
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Job title <span class="text-ink-gray-6">Seen by the project team only</span>
          <input v-model="newTitle" maxlength="140" class="form-input w-full" data-testid="invite-title" />
        </label>
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button label="Cancel" @click="close" />
          <Button type="submit" form="invite-form" variant="solid" theme="blue" :label="newEmail.trim() ? 'Invite and email' : 'Make a link'" :disabled="busy" data-testid="invite" />
        </div>
      </template>
    </Dialog>

    <Dialog v-model:open="sharing" title="Share the invitation">
      <SharePanel v-if="shared" :share="shared" :email="sharedEmail" :company="company" />
      <template #actions="{ close }">
        <div class="flex justify-end"><Button label="Done" data-testid="share-done" @click="close" /></div>
      </template>
    </Dialog>

    <Dialog v-model:open="editing" :title="`Edit ${editingName}`" description="The job title is seen by the project team only.">
      <form id="edit-contact-form" class="flex flex-col gap-3" @submit.prevent="saveContact">
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Name the team sees
          <input v-model="editName" maxlength="140" class="form-input w-full" data-testid="contact-name" />
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Mobile number
          <input v-model="editMobile" type="tel" maxlength="40" class="form-input w-full" data-testid="contact-mobile" />
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Company
          <input v-model="editCompany" maxlength="140" class="form-input w-full" data-testid="contact-company" />
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Job title
          <input v-model="editTitle" maxlength="140" class="form-input w-full" data-testid="contact-title" />
        </label>
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button label="Cancel" @click="close" />
          <Button type="submit" form="edit-contact-form" variant="solid" theme="blue" label="Save" :disabled="busy" data-testid="save-contact" />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Avatar, Badge, Button, Dialog, Dropdown, Switch } from 'frappe-ui'
import PageHead from '../components/PageHead.vue'
import SharePanel from '../components/SharePanel.vue'
import SigninPictures from '../components/SigninPictures.vue'
import ApprovalSettings from '../approvals/staff/ApprovalSettings.vue'
import ApprovalSteps from '../approvals/staff/ApprovalSteps.vue'
import { call, updateDoc } from '../api.js'
import { themeOf } from '../frame.js'
import { useMode } from '../mode.js'
import { sectionLabel } from '../words.js'
import { clientViewEntry } from '../portal/tabs.js'
import { badgeOf, call as invitesCall, invitedOf, mailLine, untilOf, waitingOf, whoOf } from '../invites.js'

// The staff side of client control (P2-06, D-122), on existing server rules only: Workspace Config through its own
// save (rows sent with their names, D-119), client contacts on invitations (P3-19: onboarding.invites, D-198) and
// the project's members.
// Drawn as the live design's Settings (D-124, version 1791648865-5845): switch rows, Save in the header, contacts with
// avatars, Invite in a dialog; "View portal as client" opens the staff preview (P3-05).
const CLIENT_SECTIONS = new Set(['home', 'files', 'documents', 'rfi', 'submittals', 'variations', 'discuss', 'whiteboards'])
const props = defineProps({ frame: Object, project: String, section: String })
const mode = useMode()
const config = ref(null)
const members = ref([])
const error = ref('')
const saved = ref(false)
const busy = ref(false)
const newEmail = ref('')
const newName = ref('')
// The staff preview of a client's portal (P3-05, D-136), labelled and placed as the live design draws it (D-172): one
// contact opens it, several give a list, none draw nothing (D-058). The server lists the contacts and checks each call.
const clientContacts = ref([])
const clientEntry = computed(() => clientViewEntry(props.project, clientContacts.value))
async function loadContacts() {
  try {
    clientContacts.value = await call('construction_core.portal_preview.contacts', { project: props.project })
  } catch {
    clientContacts.value = []
  }
}
watch(() => props.project, loadContacts, { immediate: true })
const inviting = ref(false)
const newTitle = ref('')
const editing = ref(false)
const editingRow = ref(null)
const editTitle = ref('')
const editingName = computed(() => editingRow.value?.full_name || editingRow.value?.user || '')
// P3-59 (QG): a closed project reads only. The server refuses every write after the close; the screen only stops offering
// them. P3-56 (QE): the project's managers add and remove team accounts; the server refuses a client or a partner.
const closed = ref({ closed: false })
const canEdit = computed(() => props.frame.can_manage_portal && !closed.value.closed)
const canClients = computed(() => props.frame.can_manage_clients && !closed.value.closed)
const canTeam = computed(() => props.frame.can_manage_portal && !closed.value.closed)
const closedLine = computed(() => `This project was closed${closed.value.closed_on ? ` on ${closed.value.closed_on.slice(0, 10)}` : ''}. The chat is closed and these settings are read only.${closed.value.clients_until ? ` Clients can read until ${closed.value.clients_until.slice(0, 10)}.` : ''}`)
const team = ref([])
const teamEmail = ref('')
const teamError = ref('')
async function loadTeam() {
  try {
    closed.value = await call('construction_core.projects_close.state', { project: props.project })
  } catch { /* not closed as far as we can tell; the server refuses writes anyway */ }
  try {
    team.value = await call('construction_core.projects_team.list', { project: props.project })
  } catch (e) {
    teamError.value = e.message || ''
  }
}
// A refused add or remove shows its reason beside the list, not as "Saved".
async function teamRun(job) {
  busy.value = true
  teamError.value = ''
  try { await job() } catch (e) { teamError.value = e.message || 'That did not work.' } finally { busy.value = false }
  await loadTeam()
}
function addMember() {
  const user = teamEmail.value.trim()
  teamRun(async () => {
    await call('construction_core.projects_team.add', { project: props.project, person: user }, { post: true })
    teamEmail.value = ''
  })
}
function removeMember(m) {
  if (window.confirm(`Remove ${m.full_name || m.user} from this project?`)) teamRun(() => call('construction_core.projects_team.remove', { project: props.project, person: m.user }, { post: true }))
}
function closeProject() {
  if (!window.confirm('Close this project? The chat is closed for everyone, clients can only read for 90 days, and the team can still edit documents.')) return
  run(async () => {
    await call('construction_core.projects_close.close', { project: props.project }, { post: true })
    await loadTeam()
  })
}
const clients = computed(() => members.value.filter((m) => m.cc_workspace_role === 'Client'))
// Invitations, the people waiting on open links and the contacts' own details (P3-19): the server sends no secret.
const invites = ref([])
const details = ref([])
const mailReady = ref(true)
const invited = computed(() => invitedOf(invites.value))
const waiting = computed(() => waitingOf(invites.value))
const sharing = ref(false)
const shared = ref(null)
const sharedEmail = ref('')
const company = ref('') // the company's name as the mails give it (D-225), never the product's
const editName = ref('')
const editMobile = ref('')
const editCompany = ref('')
const detailOf = (c) => details.value.find((d) => d.member === c.name) || {}
async function loadInvites() {
  try {
    const out = await call(invitesCall('project_invites'), { project: props.project })
    invites.value = out.invites
    mailReady.value = !!out.mail_ready
    company.value = out.company || ''
    details.value = await call(invitesCall('client_details'), { project: props.project })
  } catch {
    invites.value = []
    details.value = []
  }
}

// The members come with the project, read with Frappe's field rules: the team gets the permlevel-1 fields (a contact's
// job title, P3-04), and a list of the member rows would leave them out even for the team.
async function load() {
  try {
    config.value = await call('frappe.client.get', { doctype: 'Workspace Config', name: props.project })
    members.value = (await call('frappe.client.get', { doctype: 'Construction Project', name: props.project })).users || []
  } catch (e) {
    error.value = e.message
  }
}

async function run(job) {
  busy.value = true
  error.value = ''
  saved.value = false
  try {
    await job()
    saved.value = true
  } catch (e) {
    error.value = e.message || 'That did not work.'
  } finally {
    busy.value = false
    await load()
    await loadInvites()
    await loadContacts() // an invited or removed contact changes the client view's entry
  }
}

function save() {
  run(() => updateDoc('Workspace Config', props.project, {
    modified: config.value.modified,
    client_portal_enabled: config.value.client_portal_enabled,
    seen_receipts: config.value.seen_receipts,
    sidebar_sections: config.value.sidebar_sections.map(({ name, section, visible, client_visible }) => ({ name, section, visible, client_visible })),
  }))
}

function openInvite() {
  newEmail.value = ''
  newName.value = ''
  newTitle.value = ''
  inviting.value = true
}

function showShare(out, email) {
  shared.value = out
  sharedEmail.value = email || ''
  sharing.value = true
}

function invite() {
  run(async () => {
    const email = newEmail.value.trim()
    const out = await call(invitesCall('create_invite'), {
      project: props.project, email: email || null, full_name: newName.value || null, job_title: newTitle.value || null,
      mail_it: 1,
    }, { post: true })
    inviting.value = false
    showShare(out, email)
  })
}

function renew(i) {
  run(async () => showShare(await call(invitesCall('renew'), { invite: i.name, mail_it: 1 }, { post: true }), i.email))
}

function revoke(i) {
  if (!window.confirm(`Cancel the invitation for ${whoOf(i).title}? Its link stops working.`)) return
  run(() => call(invitesCall('revoke'), { invite: i.name }, { post: true }))
}

function decide(r, approve) {
  if (!approve && !window.confirm(`Decline ${r.email}? Nothing is made for them.`)) return
  run(() => call(invitesCall('decide'), { invite: r.invite, request_id: r.name, approve }, { post: true }))
}

// Removing a contact is a save of the project's members (permlevel 1: the project managers); the core revokes what
// that contact held.
function removeClient(c) {
  if (!window.confirm(`Remove ${c.full_name || c.user} from this project's portal?`)) return
  run(async () => {
    const doc = await call('frappe.client.get', { doctype: 'Construction Project', name: props.project })
    await updateDoc('Construction Project', props.project, {
      modified: doc.modified,
      users: doc.users.filter((u) => u.name !== c.name),
    })
  })
}

function startEdit(c) {
  const d = detailOf(c)
  editingRow.value = c
  editName.value = d.full_name || c.full_name || ''
  editMobile.value = d.mobile_no || ''
  editCompany.value = d.company_name || ''
  editTitle.value = c.job_title || ''
  editing.value = true
}

// The client record and the job title through update_client (manage_clients, D-209); the title is still saved on the
// project's own member row there (D-119).
function saveContact() {
  const row = editingRow.value
  run(async () => {
    const was = detailOf(row)
    const changed = (value, before) => (value.trim() === (before || '').trim() ? undefined : value) // D-225
    await call(invitesCall('update_client'), {
      project: props.project, member: row.name, full_name: changed(editName.value, was.full_name || row.full_name),
      mobile_no: changed(editMobile.value, was.mobile_no), company_name: changed(editCompany.value, was.company_name),
      job_title: changed(editTitle.value, row.job_title),
    }, { post: true })
    editing.value = false
  })
}

watch(() => props.project, () => {
  load()
  loadInvites()
  loadTeam()
}, { immediate: true })
</script>
