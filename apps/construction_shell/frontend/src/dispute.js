// A receipt's "This was not me" page (P3-78, approvals design §3.7). construction_core's /approval-dispute page serves
// no data; the app posts the link's token to construction_core.approvals.dispute.
import { createApp } from 'vue'
import { wipeCadWhenIdle } from './cadstore.js'
import { FrappeUI, useColorScheme } from 'frappe-ui'
import 'frappe-ui/style.css'
import './style.css'
import DisputeApp from './dispute/App.vue'

useColorScheme() // the viewer's saved Light/Dark choice, as on the join page (D-126)

createApp(DisputeApp).use(FrappeUI).mount('#app')
wipeCadWhenIdle() // P3-48: drawing copies a CAD viewer left in this browser (cadstore.js)
