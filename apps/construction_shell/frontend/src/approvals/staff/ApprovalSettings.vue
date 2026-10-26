<template>
  <section class="cw-card overflow-hidden [&_[role=switch][aria-checked=true]:enabled]:!bg-surface-blue-6" aria-labelledby="sec-approvals" data-testid="approval-settings">
    <div class="flex flex-wrap items-center gap-2.5 px-4 py-3.5">
      <div class="min-w-0 flex-[1_1_240px]">
        <h2 id="sec-approvals" class="cw-card-title">{{ w('set_title') }}</h2>
        <p class="mt-1 text-sm text-ink-gray-7">{{ w('set_head_note') }}</p>
      </div>
      <template v-if="s">
        <Badge :label="w(list.ready ? 'set_ready' : 'set_not_ready')" :theme="list.ready ? 'green' : 'amber'" data-testid="ready-badge" />
        <span class="text-sm text-ink-gray-7" data-testid="ready-count">{{ w('set_done_of', { done: list.done, of: list.of }) }}</span>
      </template>
    </div>
    <p v-if="loading" class="px-4 pb-3 text-sm text-ink-gray-7" role="status">{{ w('set_loading') }}</p>
    <p v-if="error" class="mx-4 mb-3 rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" data-testid="approval-error">{{ error }}</p>

    <template v-if="s">
      <p v-if="!s.manager" class="mx-4 mb-3 rounded-4 bg-surface-gray-2 px-3 py-2 text-sm text-ink-gray-8" data-testid="approval-read-only">{{ w('set_read_only') }}</p>

      <!-- the Ready checklist: each item, and the reasons of the ones not done -->
      <ul class="m-0 flex list-none flex-col gap-1.5 border-t border-outline-gray-1 px-4 py-3" aria-label="Ready checklist">
        <li v-for="i in list.items" :key="i.key" class="flex flex-col gap-0.5" data-testid="ready-item" :data-done="i.done ? '1' : '0'">
          <span class="flex items-center gap-2 text-base" :class="i.done ? 'text-ink-gray-9' : 'text-ink-gray-8'">
            <span class="size-4 flex-none" :class="i.done ? 'lucide-circle-check text-ink-green-7' : 'lucide-circle text-ink-gray-5'" aria-hidden="true" />{{ i.label }}
          </span>
          <span v-for="r in i.reasons" :key="r.key" class="pl-6 text-sm text-ink-gray-7" data-testid="ready-reason">{{ r.reason }}</span>
        </li>
        <li v-for="r in list.others" :key="r.key" class="pl-6 text-sm text-ink-gray-7" data-testid="ready-other">{{ r.reason }}</li>
      </ul>

      <!-- Portal approvals, with the contract reference and the client party -->
      <div class="flex flex-col gap-3 border-t border-outline-gray-1 px-4 py-3.5">
        <Switch v-model="form.portal_approvals" padded class="max-md:min-h-12 max-md:justify-center" :disabled="!s.manager" :label="w('set_portal')" :description="w('set_portal_help')" data-testid="portal-approvals" />
        <p class="m-0 text-sm text-ink-gray-8" data-testid="confirmation">{{ s.confirmation ? s.confirmation.text : w('set_confirm_text') }}</p>
        <p v-if="s.confirmation" class="m-0 -mt-2 text-xs text-ink-gray-7">{{ w('set_confirmed_by', { name: s.confirmation.by, when: whenText(s.confirmation.at) }) }}</p>
        <div class="grid grid-cols-3 gap-3 max-sm:grid-cols-1">
          <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('set_document') }}
            <input v-model="form.contract_document" maxlength="140" :disabled="!s.manager" class="form-input w-full max-md:h-12" data-testid="contract-document" />
          </label>
          <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('set_date') }}
            <input v-model="form.contract_date" type="date" :disabled="!s.manager" class="form-input w-full max-md:h-12" data-testid="contract-date" />
          </label>
          <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('set_clause') }}
            <input v-model="form.contract_clause" maxlength="140" :disabled="!s.manager" class="form-input w-full max-md:h-12" data-testid="contract-clause" />
          </label>
        </div>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('set_file') }}
          <select v-model="form.contract_file" :disabled="!s.manager" class="form-select w-full py-0 max-md:h-12" data-testid="contract-file">
            <option value="">{{ w('set_no_file') }}</option>
            <option v-if="form.contract_file && !files.some((f) => f.name === form.contract_file)" :value="form.contract_file">{{ s.values.contract_file_name }}</option>
            <option v-for="f in files" :key="f.name" :value="f.name">{{ f.file_name }}</option>
          </select>
        </label>

        <h3 class="m-0 mt-1 text-base font-semibold text-ink-gray-9">{{ w('set_party') }}</h3>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('set_legal_name') }}
          <input v-model="form.client_legal_name" maxlength="140" :disabled="!s.manager" class="form-input w-full max-md:h-12" data-testid="party-name" />
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('set_address') }}
          <textarea v-model="form.client_address" rows="2" maxlength="500" :disabled="!s.manager" class="form-textarea h-auto w-full" data-testid="party-address" />
        </label>
        <p v-if="s.client_party.entered_by" class="m-0 text-xs text-ink-gray-7">{{ w('set_party_entered', { name: s.client_party.entered_by, when: whenText(s.client_party.entered_at) }) }}</p>
      </div>

      <!-- the site's evidence mailbox: System Managers set it -->
      <div class="flex flex-col gap-2 border-t border-outline-gray-1 px-4 py-3.5">
        <h3 class="m-0 text-base font-semibold text-ink-gray-9">{{ w('set_mailbox') }}</h3>
        <div class="flex flex-wrap items-center gap-2">
          <input v-model="mailbox" type="email" :disabled="!boot.system_manager" class="form-input min-w-0 flex-[1_1_240px] max-md:h-12" :aria-label="w('set_mailbox')" data-testid="mailbox-address" />
          <Button v-if="boot.system_manager" variant="outline" class="max-md:!h-12" :label="w('set_mailbox_send_test')" :disabled="busy || !mailbox.trim()" data-testid="mailbox-test" @click="sendTest" />
          <Badge v-if="s.mailbox.address" :label="w(s.mailbox.confirmed ? 'set_state_confirmed' : 'set_state_waiting')" :theme="s.mailbox.confirmed ? 'green' : 'amber'" data-testid="mailbox-state" />
        </div>
        <p class="m-0 text-xs text-ink-gray-7" data-testid="mailbox-note">{{ mailboxNote }}</p>
      </div>

      <!-- the client contacts as approvers -->
      <div class="border-t border-outline-gray-1">
        <div class="px-4 py-3.5">
          <h3 class="m-0 text-base font-semibold text-ink-gray-9">{{ w('set_approvers') }}</h3>
          <p class="m-0 mt-1 text-sm text-ink-gray-7">{{ w('set_approvers_help') }}</p>
          <p v-if="notice" class="m-0 mt-1 text-sm text-ink-green-8" role="status" data-testid="approval-notice">{{ notice }}</p>
        </div>
        <div v-for="c in s.contacts" :key="c.member" class="cw-list-row flex-wrap" data-testid="approver-row">
          <Avatar :label="c.name" size="xl" />
          <div class="min-w-0 flex-[1_1_200px]">
            <div class="truncate text-base text-ink-gray-9">{{ c.name }}</div>
            <div class="truncate text-sm text-ink-gray-7">{{ [c.authority_name && w('set_authority')].filter(Boolean).join(' · ') }}</div>
            <div v-if="c.approver && c.must_reset" class="text-sm text-ink-amber-8" data-testid="must-reset">{{ w('set_must_reset') }}</div>
          </div>
          <Badge v-if="c.approver" :label="w(c.confirmed ? 'set_state_confirmed' : 'set_state_waiting')" :theme="c.confirmed ? 'green' : 'amber'" data-testid="approver-state" />
          <template v-if="s.manager">
            <Button v-if="contactActions(c).reset" variant="outline" class="max-md:!h-12" :label="w('set_send_reset')" :disabled="busy" data-testid="send-reset" @click="sendReset(c)" />
            <Button v-if="contactActions(c).confirm" variant="solid" theme="blue" class="max-md:!h-12" :label="w('set_confirm')" :disabled="busy" data-testid="confirm-approver" @click="act(() => post('api.confirm_approver', { project, member: c.member }))" />
            <Button v-if="contactActions(c).make" variant="outline" class="max-md:!h-12" :label="w('set_make_approver')" :disabled="busy" data-testid="make-approver" @click="act(() => post('api.set_approver', { project, member: c.member, may_approve: 1 }))" />
            <Button v-if="contactActions(c).remove" variant="outline" class="max-md:!h-12" :label="w('set_remove_approver')" :disabled="busy" data-testid="remove-approver" @click="act(() => post('api.set_approver', { project, member: c.member, may_approve: 0 }))" />
          </template>
        </div>
        <p v-if="!s.contacts.length" class="border-t border-outline-gray-1 px-4 py-3 text-sm text-ink-gray-7">{{ w('set_no_contacts') }}</p>
      </div>

      <div class="flex flex-col gap-3 border-t border-outline-gray-1 px-4 py-3.5">
        <Switch v-model="form.device_location" padded class="max-md:min-h-12 max-md:justify-center" :disabled="!s.manager" :label="w('set_device')" :description="w('set_device_help')" data-testid="device-location" />
        <div v-if="s.manager" class="flex items-center gap-3">
          <Button variant="solid" theme="blue" class="max-md:!h-12" :label="w('set_save')" :disabled="busy" data-testid="approval-save" @click="save" />
          <span v-if="saved" class="text-sm text-ink-green-7" role="status" data-testid="approval-saved">{{ w('set_saved') }}</span>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { Avatar, Badge, Button, Switch } from 'frappe-ui'
import { boot } from '../../boot.js'
import { call } from '../../api.js'
import { useMode } from '../../mode.js'
import { whenText } from '../terms.js'
import { staffWords } from '../words.js'
import { refusalLines } from './ask.js'
import { checklist, contactActions, formOf, switchesBody } from './settings.js'

// The project's approval settings (P3-80; design §3.2; canvas ApprovalSettings): the Ready checklist, Portal approvals with
// the contract reference and the client party, the site's evidence mailbox, the client contacts as approvers (Make approver,
// Confirm, Send reset link) and Device location. Managers write; other staff read. Every write is the server's own endpoint,
// and its refusals (the second-staff rule among them) are shown as the sentences they come in.
const props = defineProps({ project: { type: String, required: true } })
const mode = useMode()
const w = staffWords(mode)
const API = 'construction_core.approvals.'
const s = ref(null)
const form = reactive(formOf({}))
const files = ref([])
const mailbox = ref('')
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const saved = ref(false)

const list = computed(() => checklist(s.value?.ready))
const mailboxNote = computed(() => {
  if (!s.value.mailbox.address) return w(boot.system_manager ? 'set_mailbox_none' : 'set_mailbox_sysman')
  return w(s.value.mailbox.confirmed ? 'set_mailbox_confirmed' : 'set_mailbox_waiting')
})

const post = (name, args) => call(API + name, args, { post: true })

async function load() {
  loading.value = true
  try {
    s.value = await call(API + 'staff.settings', { project: props.project })
    Object.assign(form, formOf(s.value.values))
    mailbox.value = s.value.mailbox.address
    if (s.value.manager) files.value = (await call('construction_shell.api.record_options', { project: props.project })).files.filter((f) => /\.pdf$/i.test(f.file_name))
  } catch (e) {
    error.value = e.message || ''
  } finally {
    loading.value = false
  }
}

// One write, then the screen reads again; a refusal shows as its sentences.
async function act(job, then = '') {
  busy.value = true
  error.value = ''
  notice.value = ''
  saved.value = false
  try {
    await job()
    notice.value = then
    await load()
    return true
  } catch (e) {
    error.value = refusalLines(e.message).join(' ')
    return false
  } finally {
    busy.value = false
  }
}

async function save() {
  const ok = await act(() => post('api.set_switches', switchesBody(props.project, form, s.value.values)))
  saved.value = ok
}

const sendTest = () => act(() => post('api.set_evidence_mailbox', { address: mailbox.value.trim() }), w('set_mailbox_sent'))

async function sendReset(c) {
  busy.value = true
  error.value = ''
  try {
    notice.value = w('set_reset_sent', { to: (await post('credentials.send_reset_link', { project: props.project, member: c.member })).sent_to })
  } catch (e) {
    error.value = refusalLines(e.message).join(' ')
  } finally {
    busy.value = false
  }
}

watch(() => props.project, load, { immediate: true })
</script>
