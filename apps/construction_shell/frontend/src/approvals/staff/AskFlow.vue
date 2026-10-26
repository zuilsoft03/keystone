<template>
  <span>
    <AskPicker v-model:open="picking" :project="project" @picked="chosen" />
    <AskSheet v-model:open="asking" :project="project" :doctype="target.doctype" :name="target.name" />
    <DecisionForm v-model:open="deciding" :project="project" :name="target.doctype === DECISION ? target.name : ''" @ask="chosen" />
  </span>
</template>

<script setup>
import { ref, watch } from 'vue'
import AskPicker from './AskPicker.vue'
import AskSheet from './AskSheet.vue'
import DecisionForm from './DecisionForm.vue'
import { DECISION } from './ask.js'

// The two staff items of the Client room's attach menu: "Ask the client to approve…" (pick a record, then the Ask sheet)
// and "New Decision…" (the Decision form, whose "Ask the client to choose" opens the Ask sheet). `want` is which one the menu chose.
const props = defineProps({ project: { type: String, default: '' }, want: { type: String, default: '' } })
const emit = defineEmits(['done'])
const picking = ref(false)
const asking = ref(false)
const deciding = ref(false)
const target = ref({ doctype: '', name: '' })

function chosen(t) {
  target.value = t
  deciding.value = false
  asking.value = true
}

watch(() => props.want, (v) => {
  if (v === 'ask') picking.value = true
  else if (v === 'decision') {
    target.value = { doctype: '', name: '' }
    deciding.value = true
  }
}, { immediate: true })
watch([picking, asking, deciding], ([a, b, c]) => !a && !b && !c && emit('done'))
</script>
