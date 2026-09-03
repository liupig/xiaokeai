import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import './styles/global.css';

if (window.companionDesktop?.isShell) {
  document.documentElement.classList.add('is-desktop');
}

const app = createApp(App);
app.use(createPinia());
app.mount('#app');
