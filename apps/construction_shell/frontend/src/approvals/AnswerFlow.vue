<template>
  <section ref="root" tabindex="-1" class="flex flex-col gap-3.5 border-t border-outline-gray-1 pt-3.5 outline-none" :aria-label="title || undefined" data-testid="approval-flow" :data-stage="stage">
    <!-- B1: one polite live region, always here: the step's title and the refusal in view are spoken when they change. Focus
         goes to the heading (tabindex -1) on every step; the sentences below carry no alert role, so nothing is said twice. -->
    <p class="sr-only" aria-live="polite" aria-atomic="true" data-testid="approval-live">{{ said }}</p>
    <h3 v-if="title" data-focus tabindex="-1" class="m-0 text-lg font-semibold text-ink-gray-9 outline-none" data-testid="approval-step-title">{{ title }}</h3>

    <!-- The portal agreement (§3.5 item 2): the server's text and version, accepted with the password once -->
    <template v-if="stage === 'agreement'">
      <p class="m-0 text-base leading-relaxed text-ink-gray-9" data-testid="approval-agreement">{{ sheet.agreement.text }}</p>
      <div>
        <label :for="ids" class="mb-1 block text-sm text-ink-gray-8">{{ w('answer.password') }}</label>
        <input :id="ids" v-model="a.password" type="password" autocomplete="current-password" class="form-input w-full max-md:h-12" :placeholder="w('answer.password_placeholder')"
          data-testid="approval-password" @keydown.enter.prevent="agreeNow">
        <p class="m-0 mt-1 text-xs text-ink-gray-7">{{ w('answer.agree_once') }}</p>
      </div>
      <p class="m-0 text-xs text-ink-gray-7">{{ w('answer.agreement_version', { version: versionText(sheet.agreement.version) }) }}</p>
    </template>

    <template v-else-if="stage === 'accepted'">
      <p role="status" class="m-0 flex items-start gap-2 rounded-4 bg-surface-green-1 px-3 py-2.5 text-base text-ink-green-8" data-testid="approval-agreed">
        <span class="lucide-mail-check mt-0.5 size-4 flex-none" aria-hidden="true" />{{ w('answer.agreement_mailed') }}
      </p>
      <p class="m-0 text-base leading-relaxed text-ink-gray-8">{{ a.agreed.text }}</p>
      <p class="m-0 text-xs text-ink-gray-7">{{ w('answer.accepted_at', { when: whenText(a.agreed.at), version: versionText(a.agreed.version) }) }}</p>
    </template>

    <!-- The password step (§3.5 item 3, N5), before any signing -->
    <template v-else-if="stage === 'password'">
      <p class="m-0 text-base text-ink-gray-9">{{ w('answer.password_ask') }}</p>
      <div>
        <label :for="ids" class="mb-1 block text-sm text-ink-gray-8">{{ w('answer.password') }}</label>
        <input :id="ids" v-model="a.password" type="password" autocomplete="current-password" class="form-input w-full max-md:h-12" :placeholder="w('answer.password_placeholder')"
          data-testid="approval-password" @keydown.enter.prevent="passwordNow">
      </div>
      <div><button type="button" :class="LINK" data-testid="approval-forgot" @click="forgot">{{ w('answer.forgot') }}</button></div>
      <p class="m-0 text-xs text-ink-gray-7">{{ w('answer.password_why') }}</p>
    </template>

    <template v-else-if="stage === 'locked'">
      <p class="m-0 flex items-start gap-2 rounded-4 bg-surface-red-1 px-3 py-2.5 text-base text-ink-red-8" data-testid="approval-locked">
        <span class="lucide-circle-alert mt-0.5 size-4 flex-none" aria-hidden="true" />{{ w('answer.too_many') }}
      </p>
      <div v-if="canMessage"><button type="button" :class="LINK" @click="$emit('message')">{{ w('message_team') }}</button></div>
    </template>

    <!-- Signing (§3.5 items 4-6; N4, N6, N12): the locked line directly above the box, then the location choice -->
    <template v-else-if="stage === 'sign'">
      <div class="grid grid-cols-2 gap-0.5 rounded-4 bg-surface-gray-2 p-0.5" role="group" :aria-label="w('answer.how')" data-testid="approval-how">
        <button v-for="h in HOWS" :key="h" type="button" class="h-8 rounded-3 text-base font-medium max-md:h-12" :aria-pressed="String(a.how === h)" :data-how="h"
          :class="a.how === h ? 'bg-surface-base text-ink-gray-9 shadow-sm' : 'text-ink-gray-7 hover:text-ink-gray-9'" @click="choose(h)">{{ w(`answer.how_${h}`) }}</button>
      </div>
      <p class="m-0 text-base leading-normal text-ink-gray-9" data-testid="approval-locked-line">{{ line }}</p>
      <div class="overflow-hidden rounded-5 border border-dashed border-outline-gray-4 bg-surface-base" data-testid="approval-sign-box">
        <template v-if="a.how === 'type'">
          <div class="px-2.5 pt-2.5">
            <input v-model="a.typed" class="form-input w-full max-md:h-12" autocomplete="name" maxlength="140" :aria-label="w('answer.full_name')" :placeholder="w('answer.full_name')" data-testid="approval-typed">
          </div>
          <div class="flex min-h-[72px] items-center justify-center px-3.5 py-1" aria-hidden="true">
            <span v-if="typed.name" class="break-all text-[34px] leading-tight text-ink-gray-9" :style="SCRIPT">{{ typed.name }}</span>
            <span v-else class="text-sm text-ink-gray-6">{{ w('answer.name_here') }}</span>
          </div>
          <p v-if="typed.differs" class="m-0 px-3 pb-1.5 text-xs text-ink-amber-8" data-testid="approval-name-differs">{{ w('answer.name_differs', { name: account }) }}</p>
        </template>
        <SignPad v-else :strokes="a.strokes" :label="w('answer.draw_here')" @ratio="(r) => (a.ratio = r)" />
        <div class="flex items-center gap-2 border-t border-outline-gray-1 px-2 py-1">
          <span class="min-w-0 flex-1 truncate text-xs text-ink-gray-7">{{ account }}</span>
          <Button variant="ghost" size="sm" class="max-md:!h-12" :label="w('answer.clear')" data-testid="approval-clear" @click="clear" />
        </div>
      </div>
      <p class="m-0 text-sm text-ink-gray-8">{{ w('answer.saved') }} <button type="button" :class="LINK" :aria-expanded="String(why)" @click="why = !why">{{ w('answer.why') }}</button></p>
      <p v-if="why" class="m-0 rounded-4 bg-surface-gray-2 px-3 py-2.5 text-sm leading-normal text-ink-gray-9" data-testid="approval-why">{{ w('answer.why_text', { firm: boot.brand_name || '' }) }}</p>
      <div v-if="sheet.location?.on" class="flex flex-col gap-1.5 rounded-4 border border-outline-gray-2 px-3 py-2.5" data-testid="approval-location">
        <label class="flex items-start gap-2 text-base text-ink-gray-9 max-md:min-h-12">
          <input type="checkbox" class="form-checkbox mt-0.5 flex-none" :checked="a.where.ticked" data-testid="approval-location-tick" @change="tickLocation(a, $event.target.checked)">
          <span>{{ sheet.location.notice }}</span>
        </label>
        <p v-if="a.where.ticked" role="status" class="m-0 ml-6 text-sm font-medium text-ink-gray-9" data-testid="approval-location-state">
          {{ w(`answer.location_${a.where.state}`) }}
          <button v-if="a.where.state === 'waiting'" type="button" :class="LINK" @click="a.where.skip?.()">{{ w('answer.skip') }}</button>
        </p>
      </div>
    </template>

    <!-- Return with a reason (§3.5 item 3): the reason only, no signature -->
    <template v-else-if="stage === 'return'">
      <div>
        <label :for="ids" class="mb-1 block text-sm text-ink-gray-8">{{ w('answer.reason') }}</label>
        <textarea :id="ids" v-model="a.reason" rows="4" maxlength="1000" class="form-textarea h-auto w-full text-base" :placeholder="w('answer.reason_placeholder')" data-testid="approval-reason" />
      </div>
      <p class="m-0 text-sm text-ink-gray-8">{{ w('answer.reason_note') }}</p>
    </template>

    <!-- The result (§3.5 item 8) -->
    <template v-else-if="stage === 'done'">
      <div class="flex items-center gap-3">
        <span class="grid size-11 flex-none place-items-center rounded-full bg-surface-green-2 text-ink-green-8" aria-hidden="true"><span class="lucide-check size-5" /></span>
        <p role="status" class="m-0 text-base text-ink-gray-9" data-testid="approval-result">{{ w(`answer.${a.result.state}_result`, { to: a.result.to }) }}</p>
      </div>
      <dl class="m-0 grid grid-cols-[110px_1fr] gap-x-3 gap-y-2 sm:grid-cols-[132px_1fr]">
        <dt class="text-sm text-ink-gray-7">{{ w('answer.item') }}</dt><dd class="m-0 break-words text-base text-ink-gray-9">“{{ sheet.title }}” ({{ refOf(sheet) }})</dd>
        <dt class="text-sm text-ink-gray-7">{{ w('answer.answered') }}</dt><dd class="m-0 text-base text-ink-gray-9">{{ whenText(a.result.at) }}</dd>
        <dt class="text-sm text-ink-gray-7">{{ w('answer.by') }}</dt><dd class="m-0 text-base text-ink-gray-9">{{ a.result.by }}</dd>
      </dl>
      <p v-if="a.result.state === 'approved'" class="m-0 text-sm text-ink-gray-8">{{ w('answer.tab_reads', { line: w('you_approved', { date: dateText(a.result.at) }) }) }}</p>
    </template>

    <!-- A refusal that ends the flow (N7; frame "Refusal messages on the sheet"): in place of the buttons -->
    <p v-else-if="stage === 'stopped'" data-focus tabindex="-1" class="m-0 flex items-start gap-2 rounded-4 bg-surface-gray-2 px-3 py-2.5 text-base text-ink-gray-9 outline-none" data-testid="approval-refusal">
      <span class="lucide-info mt-0.5 size-4 flex-none text-ink-gray-7" aria-hidden="true" />{{ a.stop || sheet.must_reset }}
    </p>
    <div v-if="stage === 'stopped' && canMessage"><button type="button" :class="LINK" data-testid="approval-stopped-message" @click="$emit('message')">{{ w('message_team') }}</button></div>

    <!-- the lockout says its own sentence on its step, so a banner repeating the server's would show it twice -->
    <p v-if="a.banner && stage !== 'locked'" class="m-0 flex items-start gap-2 rounded-4 bg-surface-red-1 px-3 py-2.5 text-base text-ink-red-8" data-testid="approval-banner">
      <span class="lucide-circle-alert mt-0.5 size-4 flex-none" aria-hidden="true" />{{ a.banner }}
    </p>

    <footer v-if="stage !== 'closed'" class="flex flex-wrap items-center justify-end gap-2 border-t border-outline-gray-1 pt-3" data-testid="approval-flow-actions">
      <Button v-if="['agreement', 'password', 'sign', 'return'].includes(stage)" variant="ghost" size="md" class="max-md:!h-12" :label="w('answer.cancel')" data-testid="approval-cancel" @click="back" />
      <Button v-if="stage === 'agreement'" variant="solid" theme="blue" size="md" class="max-md:!h-12" :label="w('answer.agree')" :loading="a.busy" data-testid="approval-agree" @click="agreeNow" />
      <Button v-else-if="stage === 'accepted'" variant="solid" theme="blue" size="md" class="max-md:!h-12" :label="w('answer.continue')" data-testid="approval-continue" @click="a.agreed.fresh = false" />
      <Button v-else-if="stage === 'password'" variant="solid" theme="blue" size="md" class="max-md:!h-12" :label="w('answer.continue')" :loading="a.busy" data-testid="approval-password-continue" @click="passwordNow" />
      <Button v-else-if="stage === 'sign'" variant="solid" theme="blue" size="md" class="max-md:!h-12" icon-left="lucide-pen-line" :label="w('sign_approve')" :loading="a.busy" data-testid="approval-sign" @click="answerNow('approve')" />
      <Button v-else-if="stage === 'return'" variant="solid" theme="blue" size="md" class="max-md:!h-12" :label="w('answer.return')" :loading="a.busy" data-testid="approval-send-return" @click="answerNow('return')" />
      <Button v-else-if="stage === 'done'" variant="solid" theme="blue" size="md" class="max-md:!h-12" :label="w('close')" data-testid="approval-done" @click="$emit('close')" />
      <Button v-else variant="subtle" size="md" class="max-md:!h-12" :label="w('close')" data-testid="approval-flow-close" @click="$emit('close')" />
    </footer>
  </section>
</template>

<script setup>
import { computed, nextTick, ref, useId, watch } from 'vue'
import { Button } from 'frappe-ui'
import { call } from '../api.js'
import { boot } from '../boot.js'
import SignPad from './SignPad.vue'
import { dateText, refOf, whenText } from './terms.js'
import { RESET, agree, announce, attempt, confirmPassword, focusStep, press, remember, settle, stageOf, tickLocation, typedName } from './flow.js'

// The answering flow (design §3.5 items 2-8; ApprovalDecide boards 3-6, 8, 9 and the agreement and password boards), drawn
// in the sheet's #flow place below the terms, which stay in view as the summary. Its state (`state`, flow.newAnswer) is
// the sheet's, so a live reload of the sheet keeps the typed name, the drawing and the reason. Every sentence the server
// owns (the agreement, the locked lines, the location notice, the refusals) is shown as the server sends it.
const props = defineProps({
  sheet: { type: Object, required: true },
  option: { type: String, default: '' },
  step: { type: String, default: '' },
  state: { type: Object, required: true },
  w: { type: Function, required: true },
  canMessage: Boolean,
})
const emit = defineEmits(['step', 'close', 'message', 'reload'])
const a = props.state
const ids = useId()
const root = ref(null)
const why = ref(false)
const HOWS = ['type', 'draw'] // typing first, for keyboard and screen-reader users (§3.5 item 4)
const SCRIPT = { fontFamily: "'Segoe Script', 'Brush Script MT', 'Lucida Handwriting', cursive" }
const LINK = 'text-ink-blue-link underline-offset-2 hover:underline max-md:inline-flex max-md:min-h-12 max-md:items-center'
const account = boot.full_name || boot.user || ''

const stage = computed(() => stageOf(props.sheet, a, props.step))
const line = computed(() => props.sheet.lines?.[props.sheet.options?.length ? props.option : 'record'] || '')
const typed = computed(() => typedName(a.typed, account))
const title = computed(() => ({
  agreement: props.w('answer.agreement_title'), accepted: props.w('answer.accepted_title'), password: props.w('answer.password_title'),
  locked: props.w('answer.password_title'), sign: props.w('sign_approve'), return: props.w('return'),
  done: props.w(`answer.${a.result?.state}_title`),
})[stage.value] || '')
const said = computed(() => announce(stage.value, title.value, a, props.sheet, props.w))
const versionText = (v) => String(v || '').replace(/^\D+/, '') // "agreement-1" reads "1"

// A sheet this person cannot answer (another approver answered meanwhile, or an address opened it on a step) shows the
// terms and their own buttons again.
watch(stage, (s) => (s === 'closed' ? emit('step', '') : nextTick(() => {
  root.value?.scrollIntoView?.({ block: 'nearest' })
  focusStep(root.value)
})), { immediate: true })

function choose(how) {
  a.how = how
  remember(how)
}
const clear = () => (a.how === 'draw' ? a.strokes.splice(0) : (a.typed = ''))
function back() {
  a.banner = ''
  emit('step', '')
}

// A refusal that ends the flow also reads the sheet again (B7), so the terms stop saying the request is open.
const run = async (job) => (await attempt(a, job, props.w)) && emit('reload')
const agreeNow = () => (a.password ? run(() => agree(a, props.sheet)) : (a.banner = props.w('answer.password_empty')))
const passwordNow = () => (a.password ? run(() => confirmPassword(a)) : (a.banner = props.w('answer.password_empty')))
const answerNow = (kind) => !a.busy && run(async () => {
  const out = await press(kind, { sheet: props.sheet, a, option: props.option, w: props.w })
  if (out) settle(a, out, account)
})
// "Forgot password" (N5): Frappe's reset email to this account, then back to the sheet with a note above the terms.
const forgot = () => run(async () => {
  const email = boot.email || boot.user
  try {
    await call(RESET, { user: email }, { post: true })
  } catch (e) {
    if (e.status !== 429) throw e
    a.banner = props.w('answer.reset_wait')
    return
  }
  a.notice = props.w('answer.reset_sent', { email })
  emit('step', '')
})
</script>
