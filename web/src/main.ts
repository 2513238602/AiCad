import { createApp } from 'vue'
import { createPinia } from 'pinia'
import i18n from './i18n'
import App from './App.vue'

import './styles/variables.css'
import './styles/global.css'

const app = createApp(App)
app.use(createPinia())
app.use(i18n)
app.mount('#app')
