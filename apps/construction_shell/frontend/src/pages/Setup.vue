<template>
  <!-- P3-52…P3-57 (docs/design/phase-3.3-firm-setup.md §4, Stage B): the set-up wizard, W1…W12, for System Managers. The canvas
       has no set-up screens (QI), so it is built from the design system's tokens and its nearest frames, Settings (cards,
       fields) and the dialogs (D-196). The server redirects here until set-up is finished, keeps each step's state and
       checks every call; this page only shows the steps. W10 "Your client" sits on the join page's invitation; W11 (partner
       companies) is hidden by the server until partners ship (D-444). -->
  <main class="flex max-w-5xl flex-1 flex-col gap-3.5 px-4 py-5 sm:px-6" data-testid="setup-page">
    <PageHead crumb="Workspace / Set-up" title="Set up your firm" />
    <p v-if="!boot.system_manager" role="alert" class="text-ink-red-7" data-testid="setup-denied">Only a System Manager can set up the firm. Ask one.</p>
    <p v-else-if="error && !state" role="alert" class="text-ink-red-7" data-testid="setup-error">{{ error }}</p>
    <template v-else-if="state">
      <div class="flex flex-wrap items-center gap-3">
        <p class="m-0 text-sm text-ink-gray-8" data-testid="setup-progress">Step {{ position(state, current) }} of {{ steps.length }} · {{ settledCount }} done or skipped</p>
        <div class="h-2 min-w-24 flex-1 overflow-hidden rounded-full bg-surface-gray-3" aria-hidden="true"><div class="h-full bg-surface-blue-6" :style="{ width: `${(settledCount / (steps.length - 1)) * 100}%` }" /></div>
        <Button label="All steps" class="lg:hidden max-md:!h-12" :aria-expanded="listOpen" data-testid="setup-steps-toggle" @click="listOpen = !listOpen" />
        <Button label="Finish later" class="max-md:!h-12" data-testid="setup-later" @click="later" />
      </div>

      <div class="grid gap-3.5 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav :class="listOpen ? '' : 'max-lg:hidden'" class="cw-card flex flex-col self-start p-1" aria-label="Set-up steps" data-testid="setup-steps">
          <button v-for="s in steps" :key="s.id" type="button" class="flex min-h-12 items-center gap-2 rounded-4 px-2 text-left text-base lg:min-h-9"
            :class="s.id === current ? 'bg-surface-blue-1 text-ink-blue-8' : 'text-ink-gray-8 hover:bg-surface-gray-2'" :aria-current="s.id === current ? 'step' : undefined"
            :data-testid="`setup-go-${s.id}`" @click="go(s.id)">
            <span class="min-w-0 flex-1">{{ s.title }}</span>
            <span class="text-xs" :class="stateOf(state, s.id) === 'done' ? 'text-ink-green-7' : 'text-ink-gray-7'" :data-testid="`setup-state-${s.id}`">{{ s.id === 'W12' ? '' : stateWord(state, s.id) }}</span>
          </button>
        </nav>

        <div class="flex min-w-0 flex-col gap-3.5">
          <div>
            <h2 class="m-0 text-xl-semibold text-ink-gray-9" data-testid="setup-title" :id="`step-${current}`">{{ step.title }}</h2>
            <p class="m-0 mt-1 text-sm text-ink-gray-7">{{ step.lead }}</p>
          </div>
          <p v-if="error" role="alert" class="m-0 text-ink-red-7" data-testid="setup-error">{{ error }}</p>
          <component :is="PANELS[current]" :key="current" @saved="saved(current)" @goto="go" @finished="finished" />
          <div v-if="current !== 'W12'" class="flex flex-wrap items-center gap-2" data-testid="setup-footer">
            <Button v-if="index > 0" label="Back" class="max-md:!h-12" data-testid="setup-back" @click="go(steps[index - 1].id)" />
            <Button variant="solid" theme="blue" label="Next" class="max-md:!h-12" :disabled="busy || !settled(current)" data-testid="setup-next" @click="go(steps[index + 1].id)" />
            <Button v-if="current !== 'W1'" :label="current === 'W2' ? `Keep ${product}` : 'Skip this step'" class="ml-auto max-md:!h-12" :disabled="busy" data-testid="setup-skip" @click="skip" />
          </div>
        </div>
      </div>
    </template>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import PageHead from '../components/PageHead.vue'
import { FALLBACK_PRODUCT as product } from '../components/BrandMark.vue'
import FirmPanel from '../components/setup/FirmPanel.vue'
import BrandStep from '../components/setup/BrandStep.vue'
import MailPanel from '../components/setup/MailPanel.vue'
import OwnerPanel from '../components/setup/OwnerPanel.vue'
import SecurityPanel from '../components/setup/SecurityPanel.vue'
import BackupPanel from '../components/setup/BackupPanel.vue'
import DefaultsPanel from '../components/setup/DefaultsPanel.vue'
import ProjectStep from '../components/setup/ProjectStep.vue'
import TeamStep from '../components/setup/TeamStep.vue'
import ClientStep from '../components/setup/ClientStep.vue'
import SummaryStep from '../components/setup/SummaryStep.vue'
import { call } from '../api.js'
import { boot } from '../boot.js'
import { CLIENT_DONE, SETUP, firstOpen, position, post, stateOf, stateWord, visibleSteps } from '../components/setup/setup.js'

const PANELS = { W1: FirmPanel, W2: BrandStep, W3: MailPanel, W4: OwnerPanel, W5: SecurityPanel, W6: BackupPanel, W7: DefaultsPanel, W8: ProjectStep, W9: TeamStep, W10: ClientStep, W12: SummaryStep }
const router = useRouter()
const state = ref(null)
const current = ref('W1')
const error = ref('')
const busy = ref(false)
const listOpen = ref(false)
const steps = computed(() => visibleSteps(state.value))
const index = computed(() => steps.value.findIndex((s) => s.id === current.value))
const step = computed(() => steps.value[index.value] || steps.value[0])
const settled = (id) => ['done', 'skipped'].includes(stateOf(state.value, id))
const settledCount = computed(() => steps.value.filter((s) => s.id !== 'W12' && settled(s.id)).length)

onMounted(async () => {
  if (!boot.system_manager) return
  try {
    state.value = await call(`${SETUP}state`)
    current.value = firstOpen(state.value)
  } catch (e) {
    error.value = e.message || 'Set-up could not be read.'
  }
})

function go(id) {
  current.value = id
  listOpen.value = false
}

async function mark(id, to) {
  busy.value = true
  error.value = ''
  try {
    state.value = await post(`${SETUP}mark_step`, { step: id, state: to })
    return true
  } catch (e) {
    error.value = e.message || 'That did not work. Try again.'
    return false
  } finally {
    busy.value = false
  }
}

// The server proves W1, W3, W4, W6, W7 and W9 itself and refuses a screen's "done" for them; the others are marked here.
async function saved(id) {
  if (!CLIENT_DONE.includes(id)) {
    try {
      state.value = await call(`${SETUP}state`)
    } catch (e) {
      error.value = e.message || 'Set-up could not be read.'
    }
  } else if (stateOf(state.value, id) !== 'done') await mark(id, 'done')
}

// The server remembers it for this person, so the dashboard opens instead of the wizard (T8).
async function later() {
  busy.value = true
  try {
    await post(`${SETUP}finish_later`)
    router.push('/')
  } catch (e) {
    error.value = e.message || 'That did not work. Try again.'
  } finally {
    busy.value = false
  }
}

async function skip() {
  if (await mark(current.value, current.value === 'W2' ? 'done' : 'skipped')) go(steps.value[index.value + 1].id)
}

const finished = () => router.push('/')
</script>
