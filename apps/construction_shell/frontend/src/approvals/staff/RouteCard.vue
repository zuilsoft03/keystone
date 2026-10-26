<template>
  <div class="flex flex-col gap-3 border-t border-outline-gray-1 px-4 py-3.5" :data-testid="`route-${card.kind}`">
    <div class="flex flex-wrap items-center gap-2">
      <h3 class="m-0 min-w-0 flex-[1_1_200px] text-base font-semibold text-ink-gray-9">{{ kindWord(card.kind, mode) }}</h3>
      <span class="text-xs text-ink-gray-7" data-testid="route-version">{{ card.version ? w('rt_version', { name: card.version.by, when: whenText(card.version.at) }) : w('rt_not_saved') }}</span>
    </div>
    <p v-if="!steps.length" class="m-0 text-sm text-ink-gray-7" data-testid="route-empty">{{ w('rt_no_steps') }}</p>

    <fieldset v-for="(s, i) in steps" :key="i" class="m-0 flex min-w-0 flex-col gap-2.5 rounded-4 border border-outline-gray-2 p-3" :disabled="!canEdit" data-testid="route-step">
      <legend class="px-1 text-sm font-medium text-ink-gray-8">{{ w('rt_step', { no: i + 1 }) }}</legend>
      <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('rt_name') }}
        <input v-model="s.step_name" maxlength="140" class="form-input w-full max-md:h-12" data-testid="step-name" />
      </label>
      <div class="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('rt_position') }}
          <select v-model="s.position" class="form-select w-full py-0 max-md:h-12" data-testid="step-position">
            <option v-for="o in POSITIONS" :key="o" :value="o">{{ w(OPTION_WORD[o]) }}</option>
          </select>
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('rt_who') }}
          <select v-model="s.who" class="form-select w-full py-0 max-md:h-12" data-testid="step-who">
            <option v-for="o in WHO" :key="o" :value="o">{{ w(OPTION_WORD[o]) }}</option>
          </select>
        </label>
        <label v-if="s.who === 'Project role'" class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('rt_project_role') }}
          <select v-model="s.project_role" class="form-select w-full py-0 max-md:h-12" data-testid="step-project-role"><option v-for="o in PROJECT_ROLES" :key="o">{{ o }}</option></select>
        </label>
        <label v-else-if="s.who === 'Staff role'" class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('rt_staff_role') }}
          <select v-model="s.staff_role" class="form-select w-full py-0 max-md:h-12" data-testid="step-staff-role"><option v-for="o in STAFF_ROLES" :key="o">{{ o }}</option></select>
        </label>
        <label v-else class="col-span-2 flex flex-col gap-1.5 text-xs text-ink-gray-7 max-sm:col-span-1">{{ w('rt_people') }}
          <textarea v-model="s.people" rows="3" class="form-textarea h-auto w-full" data-testid="step-people" />
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('rt_rule') }}
          <select v-model="s.rule" class="form-select w-full py-0 max-md:h-12" data-testid="step-rule">
            <option v-for="o in RULES" :key="o" :value="o">{{ w(OPTION_WORD[o]) }}</option>
          </select>
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('rt_condition') }}
          <select v-model="s.condition" class="form-select w-full py-0 max-md:h-12" data-testid="step-condition">
            <option v-for="o in CONDITIONS" :key="o" :value="o">{{ w(OPTION_WORD[o]) }}</option>
          </select>
        </label>
        <label v-if="s.condition === 'Cost above'" class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('rt_amount') }}
          <input v-model.number="s.amount" type="number" min="0" class="form-input w-full max-md:h-12" data-testid="step-amount" />
        </label>
        <label v-if="s.condition === 'Days above'" class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('rt_days') }}
          <input v-model.number="s.days" type="number" min="0" class="form-input w-full max-md:h-12" data-testid="step-days" />
        </label>
        <label class="flex flex-col gap-1.5 text-xs text-ink-gray-7">{{ w('rt_due') }}
          <input v-model.number="s.due_days" type="number" min="1" max="30" class="form-input w-full max-md:h-12" data-testid="step-due" />
        </label>
      </div>
      <div v-if="canEdit" class="flex flex-wrap gap-2">
        <Button variant="outline" class="max-md:!h-12" icon-left="lucide-arrow-up" :label="w('rt_up')" :disabled="i === 0" data-testid="step-up" @click="steps = moveStep(steps, i, -1)" />
        <Button variant="outline" class="max-md:!h-12" icon-left="lucide-arrow-down" :label="w('rt_down')" :disabled="i === steps.length - 1" data-testid="step-down" @click="steps = moveStep(steps, i, 1)" />
        <Button variant="outline" class="max-md:!h-12" icon-left="lucide-trash-2" :label="w('rt_remove')" data-testid="step-remove" @click="steps.splice(i, 1)" />
      </div>
    </fieldset>

    <div v-if="canEdit" class="flex flex-wrap items-center gap-2">
      <Button variant="outline" class="max-md:!h-12" icon-left="lucide-plus" :label="w('rt_add')" :disabled="steps.length >= LIMIT" data-testid="step-add" @click="steps.push(blankStep())" />
      <Button variant="solid" theme="blue" class="max-md:!h-12" :label="w('rt_save')" :disabled="busy" data-testid="route-save" @click="save" />
      <span v-if="saved" class="text-sm text-ink-green-7" role="status" data-testid="route-saved">{{ w('rt_saved') }}</span>
    </div>
    <div v-if="problems.length" class="rounded-4 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-8" role="alert" data-testid="route-errors">
      <div v-for="l in problems" :key="l">{{ l }}</div>
    </div>

    <!-- the preview line, from the saved steps -->
    <div class="flex flex-col gap-1.5 rounded-4 bg-surface-gray-2 px-3 py-2.5" data-testid="route-preview">
      <span class="text-xs text-ink-gray-7">{{ w('rt_preview') }}</span>
      <span class="break-words text-sm text-ink-gray-9" data-testid="preview-text">{{ line }}</span>
      <div class="flex flex-wrap items-center gap-2">
        <input v-model="sample" class="form-input min-w-0 flex-[1_1_160px] max-md:h-12" :aria-label="w('rt_try')" :placeholder="w('rt_try')" data-testid="preview-sample" />
        <Button variant="outline" class="max-md:!h-12" :label="w('rt_try_go')" :disabled="!sample.trim()" data-testid="preview-go" @click="preview" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Button } from 'frappe-ui'
import { call } from '../../api.js'
import { useMode } from '../../mode.js'
import { kindWord, whenText } from '../terms.js'
import { staffWords } from '../words.js'
import { refusalLines } from './ask.js'
import { CONDITIONS, LIMIT, OPTION_WORD, POSITIONS, PROJECT_ROLES, RULES, STAFF_ROLES, WHO, blankStep, moveStep, previewBody, routeBody, routeErrors, stepsOf } from './routes.js'

// One record kind's card in Settings, Approval steps (P3-82; design 14.6): the ordered steps with their fields, add, remove
// and reorder, Save through routes.save_route (the server's refusals shown as sentences) and the preview line.
const props = defineProps({ card: { type: Object, required: true }, canEdit: Boolean })
const emit = defineEmits(['saved'])
const mode = useMode()
const w = staffWords(mode)
const API = 'construction_core.approvals.routes.'
const steps = ref(stepsOf(props.card.steps))
const busy = ref(false)
const saved = ref(false)
const refused = ref([])
const tried = ref(false)
const line = ref('')
const sample = ref('')

const problems = computed(() => [...(tried.value ? routeErrors(steps.value).map(([no, key]) => (no ? w('rt_step_err', { no, error: w(key) }) : w(key))) : []), ...refused.value])

async function preview() {
  try {
    line.value = (await call(API + 'preview', previewBody(props.card.kind, sample.value))).text
  } catch (e) {
    refused.value = refusalLines(e.message)
  }
}

async function save() {
  tried.value = true
  saved.value = false
  refused.value = []
  if (routeErrors(steps.value).length) return
  busy.value = true
  try {
    emit('saved', (await call(API + 'save_route', routeBody(props.card.kind, steps.value), { post: true })).routes[0])
    saved.value = true
    tried.value = false
  } catch (e) {
    refused.value = refusalLines(e.message)
  } finally {
    busy.value = false
  }
}

// A new card (after a save or a reload) resets the form and reads the preview again.
watch(() => props.card, (c) => { steps.value = stepsOf(c.steps); sample.value = ''; preview() }, { immediate: true })
</script>
