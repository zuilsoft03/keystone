<template>
  <!-- P3-53 (W3): the default outgoing email account. Saving does not prove it works: a test email carries a 6-digit code
       and the typed code proves the mail left the server and arrived (T2). The saved password is never shown (T4). -->
  <section class="cw-card flex flex-col gap-3 px-4 py-3.5" aria-labelledby="sec-mail" data-testid="mail-panel">
    <h2 id="sec-mail" class="cw-card-title">Outgoing email</h2>
    <p v-if="mail?.confirmed" class="m-0 text-ink-green-7" data-testid="mail-confirmed">Working: a test email reached you. Change the settings below and test again if you move to another mail service.</p>
    <p v-if="mail?.last_error" role="alert" class="m-0 text-ink-red-7" data-testid="mail-last-error">Last problem: {{ mail.last_error }}</p>
    <form class="flex flex-col gap-3" @submit.prevent="save">
      <div class="grid grid-cols-[minmax(0,1fr)_7rem] gap-3">
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Mail server <span class="text-ink-gray-6">Example: smtp.gmail.com</span>
          <input v-model="form.server" maxlength="140" required autocomplete="off" class="form-input h-12 w-full md:h-8" data-testid="mail-server" />
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Port
          <input v-model.number="form.port" type="number" min="1" max="65535" required class="form-input h-12 w-full md:h-8" data-testid="mail-port" />
        </label>
      </div>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Security
        <select v-model="form.security" class="form-select h-12 w-full md:h-8" data-testid="mail-security">
          <option value="ssl">SSL (usually port 465)</option>
          <option value="starttls">STARTTLS (usually port 587)</option>
          <option value="none">None (not safe; only for a mail server in your own office)</option>
        </select>
      </label>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">User name
        <input v-model="form.login" maxlength="140" autocomplete="off" class="form-input h-12 w-full md:h-8" data-testid="mail-login" />
      </label>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Password <span class="text-ink-gray-6">{{ mail?.has_password ? 'A password is saved. Leave this empty to keep it.' : 'Some services need an app password' }}</span>
        <input v-model="form.password" type="password" maxlength="200" autocomplete="new-password" class="form-input h-12 w-full md:h-8" data-testid="mail-password" />
      </label>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Send from <span class="text-ink-gray-6">Example: projects@example.com</span>
        <input v-model="form.from_address" type="email" maxlength="140" required class="form-input h-12 w-full md:h-8" data-testid="mail-from" />
      </label>
      <Button type="submit" variant="solid" theme="blue" label="Save" class="self-start max-md:!h-12" :loading="busy" :disabled="busy" data-testid="mail-save" />
    </form>

    <div class="flex flex-col gap-2 border-t border-outline-gray-1 pt-3">
      <h3 class="m-0 text-sm font-semibold text-ink-gray-9">Check that it works</h3>
      <p class="m-0 text-sm text-ink-gray-7">We send a 6-digit code to the address below. Type it here.</p>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">Send the code to
        <input v-model="address" type="email" required class="form-input h-12 w-full md:h-8" data-testid="mail-to" />
      </label>
      <Button label="Send me a test email" class="self-start max-md:!h-12" :disabled="busy || !mail?.server || !address.trim()" data-testid="mail-test" @click="test" />
      <template v-if="sent">
        <p class="m-0 text-sm text-ink-gray-8" data-testid="mail-sent">A code is on its way to {{ address }}. It runs out in a few minutes.</p>
        <CodeBoxes v-model="code" testid="mail-code" label="Code from the test email" :disabled="busy" @complete="confirm" />
        <Button variant="solid" theme="blue" label="Check the code" class="self-start max-md:!h-12" :disabled="busy || code.length !== 6" data-testid="mail-confirm" @click="confirm" />
      </template>
    </div>
    <p v-if="error" role="alert" class="m-0 text-ink-red-7" data-testid="mail-error">{{ error }}</p>
    <p v-if="done" class="m-0 text-ink-green-7" data-testid="mail-done">{{ done }}</p>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Button } from 'frappe-ui'
import CodeBoxes from '../CodeBoxes.vue'
import { call } from '../../api.js'
import { boot } from '../../boot.js'
import { post, useRun } from './setup.js'

const emit = defineEmits(['saved'])
const M = 'construction_core.accounts.mail_setup.'
const mail = ref(null)
const form = reactive({ server: '', port: 465, security: 'ssl', login: '', password: '', from_address: '' })
const sent = ref(false)
const code = ref('')
// Administrator has only Frappe's placeholder address before W4, so the address is asked for.
const address = ref(/@/.test(boot.email || '') && boot.email !== 'admin@example.com' ? boot.email : '')
const { busy, error, done, run } = useRun()

async function load() {
  try {
    mail.value = await call(`${M}get`)
  } catch (e) {
    error.value = e.message || 'The email settings could not be read.' // not through run(): it would wipe the message of the save that called this
    return
  }
  for (const k of ['server', 'port', 'security', 'login', 'from_address']) if (mail.value[k]) form[k] = mail.value[k]
}
onMounted(load)

async function save() {
  const secret = form.password
  const out = await run(() => post(`${M}save`, { ...form, password: secret || null }), 'Saved. Now send yourself a test email.', secret)
  if (out) {
    form.password = '' // the page keeps no password once it is sent
    sent.value = false
    await load()
  }
}

async function test() {
  code.value = ''
  sent.value = false
  const got = await run(() => post(`${M}test`, { to: address.value.trim() }), '')
  if (!got) return
  if (got.out.sent) sent.value = true
  else error.value = got.out.error || 'The test email was not sent.'
}

const WHY = { wrong: (r) => `That code is not right. ${r.left} ${r.left === 1 ? 'try' : 'tries'} left.`, locked: () => 'Too many wrong codes. Send a new test email.', expired: () => 'That code ran out. Send a new test email.' }

async function confirm() {
  if (busy.value || code.value.length !== 6) return
  const got = await run(() => post(`${M}confirm`, { code: code.value }))
  if (!got) return
  if (got.out.state === 'confirmed') {
    done.value = 'The code is right: email works.'
    sent.value = false
    await load()
    emit('saved')
    return
  }
  error.value = (WHY[got.out.state] || WHY.expired)(got.out)
  code.value = ''
  if (got.out.state !== 'wrong') sent.value = false
}
</script>
