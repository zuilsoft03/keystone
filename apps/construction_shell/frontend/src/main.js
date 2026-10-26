import { createApp } from 'vue'
import { wipeCadWhenIdle } from './cadstore.js'
import { FrappeUI, useColorScheme } from 'frappe-ui'
// frappe-ui 1.x keeps its stylesheet behind a subpath export; it defines the variables its Tailwind preset reads.
import 'frappe-ui/style.css'
import './style.css'
import App from './App.vue'
import router from './router.js'

// The saved Light/Dark choice (D-126) is applied before the app mounts; the account menu changes it.
useColorScheme()

const app = createApp(App)
app.use(router)
app.use(FrappeUI)
app.mount('#app')
wipeCadWhenIdle() // P3-48: drawing copies a CAD viewer left in this browser (cadstore.js)
