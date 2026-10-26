<template>
  <!-- P3-58 (QI, docs/design/phase-3.3-firm-setup.md §4 Stage F): the Company page, for System Managers. The canvas has no frame
       for it, so it is built from the tokens and the Settings cards (D-196). Each editable section is the wizard's own panel;
       Clients and Health are read only. Partner companies wait for go-live (D-444). The server checks System Manager on every call. -->
  <main class="flex max-w-5xl flex-1 flex-col gap-3.5 px-4 py-5 sm:px-6" data-testid="company-page">
    <PageHead crumb="Workspace / Company" title="Your company" />
    <p v-if="!boot.system_manager" role="alert" class="text-ink-red-7" data-testid="company-denied">You are not allowed to see this page. Ask a System Manager.</p>
    <template v-else>
      <p v-if="error" role="alert" class="m-0 text-ink-red-7" data-testid="company-error">{{ error }}</p>
      <p v-if="!data && !error" class="text-ink-gray-7">Loading…</p>

      <template v-if="data">
        <div id="firm" data-testid="company-firm"><FirmPanel /></div>

        <section id="brand" class="cw-card flex flex-wrap items-center gap-2.5 px-4 py-3.5" aria-labelledby="sec-brand" data-testid="company-brand">
          <div class="min-w-0 flex-[1_1_240px]">
            <h2 id="sec-brand" class="cw-card-title">Brand</h2>
            <p class="mt-1 text-sm text-ink-gray-7">{{ data.brand?.company || data.firm?.company_name || 'Your name, logo and colours.' }}</p>
          </div>
          <Button label="Open the Brand page" icon-left="lucide-palette" class="max-md:!h-12" :route="{ name: 'brand' }" data-testid="company-brand-link" />
        </section>

        <div id="mail" data-testid="company-mail"><MailPanel /></div>

        <div id="backups" data-testid="company-backups"><BackupPanel /></div>

        <div id="security" data-testid="company-security"><SecurityPanel /></div>

        <section id="people" class="cw-card flex flex-wrap items-center gap-2.5 px-4 py-3.5" aria-labelledby="sec-people" data-testid="company-people">
          <div class="min-w-0 flex-[1_1_240px]">
            <h2 id="sec-people" class="cw-card-title">People</h2>
            <p class="mt-1 text-sm text-ink-gray-7">Invite the team, set roles and job titles, turn access off.</p>
          </div>
          <Button label="Open People" icon-left="lucide-users" class="max-md:!h-12" :route="{ name: 'people' }" data-testid="company-people-link" />
        </section>

        <section id="clients" class="cw-card overflow-hidden" aria-labelledby="sec-clients" data-testid="company-clients">
          <div class="px-4 py-3.5">
            <h2 id="sec-clients" class="cw-card-title">Clients</h2>
            <p class="mt-1 text-sm text-ink-gray-7">The people at your clients, with their projects. Read only; each project's Settings invites them.</p>
          </div>
          <div v-for="c in data.clients" :key="c.email" class="cw-list-row flex-wrap" data-testid="company-client">
            <Avatar :label="c.full_name || c.email" size="xl" />
            <div class="min-w-0 flex-[1_1_220px]">
              <div class="truncate text-base text-ink-gray-9">{{ c.full_name || c.email }}</div>
              <div class="truncate text-sm text-ink-gray-7">{{ [c.email, c.company, projectsOf(c)].filter(Boolean).join(' · ') }}</div>
            </div>
          </div>
          <p v-if="!data.clients.length" class="border-t border-outline-gray-1 px-4 py-3 text-sm text-ink-gray-7">No client yet.</p>
        </section>

        <div id="defaults" data-testid="company-defaults"><DefaultsPanel /></div>

        <section id="privacy" class="cw-card flex flex-col gap-1 px-4 py-3.5" aria-labelledby="sec-privacy" data-testid="company-privacy">
          <h2 id="sec-privacy" class="cw-card-title">Privacy</h2>
          <p class="m-0 text-sm text-ink-gray-8">Privacy contact: {{ data.privacy?.contact || 'not set' }}</p>
          <p class="m-0 text-sm text-ink-gray-7">Privacy notice version: {{ data.privacy?.notice_version || '—' }}</p>
        </section>

        <section id="health" class="cw-card overflow-hidden" aria-labelledby="sec-health" data-testid="company-health">
          <div class="px-4 py-3.5"><h2 id="sec-health" class="cw-card-title">Health</h2></div>
          <div v-for="[label, value] in healthRows" :key="label" class="cw-list-row flex-wrap justify-between" data-testid="health-row">
            <span class="text-base text-ink-gray-9">{{ label }}</span>
            <span class="text-sm text-ink-gray-7">{{ value }}</span>
          </div>
        </section>
      </template>
    </template>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Avatar, Button } from 'frappe-ui'
import PageHead from '../components/PageHead.vue'
import FirmPanel from '../components/setup/FirmPanel.vue'
import MailPanel from '../components/setup/MailPanel.vue'
import BackupPanel from '../components/setup/BackupPanel.vue'
import DefaultsPanel from '../components/setup/DefaultsPanel.vue'
import SecurityPanel from '../components/setup/SecurityPanel.vue'
import { boot } from '../boot.js'
import { call } from '../api.js'
import { healthRows as rowsOf } from '../company.js'

const data = ref(null)
const error = ref('')
const healthRows = computed(() => rowsOf(data.value?.health))
const projectsOf = (c) => (c.projects?.length ? c.projects.join(', ') : '')

onMounted(async () => {
  if (!boot.system_manager) return
  try {
    data.value = await call('construction_core.accounts.company.page')
  } catch (e) {
    error.value = e.message || 'That did not work.'
  }
})
</script>
