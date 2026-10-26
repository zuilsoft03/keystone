// The sign-in-free join page (P3-17, D-214). construction_core's /join page serves no data; every step is a POST to
// construction_core.onboarding.join, which checks the invitation on each call.
import { createApp } from 'vue'
import { wipeCadWhenIdle } from './cadstore.js'
import { FrappeUI, useColorScheme } from 'frappe-ui'
import 'frappe-ui/style.css'
import './style.css'
import JoinApp from './join/App.vue'

useColorScheme()  // the viewer's saved Light/Dark choice, as on the portal (D-126)

createApp(JoinApp).use(FrappeUI).mount('#app')
wipeCadWhenIdle() // P3-48: drawing copies a CAD viewer left in this browser (cadstore.js)
