// The sign-in page (P3-24, D-251, D-252): /login and /update-password drawn as the design's LoginA. Every call is one
// of Frappe's own (sign-in, its two-step check, the reset email, update_password); this only presents.
import { createApp } from 'vue'
import { wipeCadWhenIdle } from './cadstore.js'
import { clearAllDrafts, draftStorage } from './sections/drafts.js'
import { FrappeUI, useColorScheme } from 'frappe-ui'
import 'frappe-ui/style.css'
import './style.css'
import LoginApp from './login/App.vue'

useColorScheme() // the viewer's saved Light/Dark choice (D-126)
clearAllDrafts(draftStorage()) // P3-61: unsent chat drafts never survive a sign-out, a Desk logout or an expired session

createApp(LoginApp).use(FrappeUI).mount('#app')
wipeCadWhenIdle() // P3-48: drawing copies a CAD viewer left in this browser (cadstore.js)
