<template>
  <!-- P3-24, P3-26 (D-250, D-251, D-264, D-265): the sign-in page in the look of the group its address is for, read live
       from the design (LoginA 1791897348-4b53, LoginB 1791955581-f999): LoginA for the team at /login, LoginB for clients
       at /portal/login, and the password page in the look of the person whose reset key it is. Every action is one of
       Frappe's own calls (useSignIn); nothing here is rendered as HTML. -->
  <ClientFrame v-if="look === 'client'" :s="s" :company="company" :help="help" />
  <TeamFrame v-else :s="s" :company="company" :help="help" />
</template>

<script setup>
import ClientFrame from './ClientFrame.vue'
import TeamFrame from './TeamFrame.vue'
import { useSignIn } from './useSignIn.js'

const boot = window.cc_boot || {}
const look = boot.look === 'client' ? 'client' : 'team'
const company = boot.company || ''
const help = boot.help_email || ''
const s = useSignIn({ ...boot, look })
</script>

<style>
.lg-link { display: inline; padding: 0; border: 0; background: none; font: inherit; letter-spacing: inherit; color: var(--ink-blue-8, var(--ink-blue-link)); cursor: pointer; }
.lg-link:hover { text-decoration: underline; text-underline-offset: 2px; }
.lg-inline { color: var(--ink-blue-8, var(--ink-blue-link)); text-decoration: underline; text-underline-offset: 2px; }
.lg-back { display: inline-flex; align-items: center; gap: 6px; padding: 0; border: 0; background: none; font: inherit; font-size: 13px; color: var(--ink-gray-8); cursor: pointer; }
.lg-back:hover { color: var(--ink-gray-9); text-decoration: underline; text-underline-offset: 2px; }
@keyframes lg-tile-in { from { opacity: 0; transform: scale(.55) } to { opacity: 1; transform: scale(1) } }
.lg-tile { transform-box: fill-box; transform-origin: center; animation: lg-tile-in .9s cubic-bezier(.2,.7,.2,1) both }
@media (prefers-reduced-motion: reduce) { .lg-tile { animation: none } }
</style>
