import { createApp } from 'vue';
import { createPinia } from 'pinia';
import { i18n } from '../../../i18n';
import LiveLab from './LiveLab.vue';

createApp(LiveLab).use(createPinia()).use(i18n).mount('#app');
