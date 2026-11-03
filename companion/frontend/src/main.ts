import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import { i18n } from './i18n';
import './styles/global.css';
import { getLogoUrl } from './branding';

const favicon = document.createElement('link');
favicon.rel = 'icon';
favicon.type = 'image/png';
favicon.href = getLogoUrl();
document.head.appendChild(favicon);

if (window.companionDesktop?.isShell) {
  document.documentElement.classList.add('is-desktop');
  if (new URLSearchParams(location.search).get('shell') === 'pet') {
    document.documentElement.classList.add('is-pet');
  }
}

const app = createApp(App);
app.use(createPinia());
app.use(i18n);
app.mount('#app');
