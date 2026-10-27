import { computed, onMounted, onUnmounted, ref } from 'vue';
import { api, type GlancePower } from '../../api/client';
import { t } from '../../i18n';
import { useCharacterStore } from '../../stores/character';
import { useSettingsStore } from '../../stores/settings';

/** 舞台顶栏和桌宠共用这一枚视觉开关。 */
export function useGlancePower() {
  const characters = useCharacterStore();
  const settings = useSettingsStore();
  const glance = ref<GlancePower>({ along: false, eyes: 'down', message: '', character_id: 0 });
  const glanceBusy = ref(false);
  let timer = 0;

  const glanceTip = computed(() => {
    if (glance.value.eyes === 'starting' || glanceBusy.value) return t('top.glanceStarting');
    if (glance.value.message) return glance.value.message;
    return glance.value.along ? t('top.glanceOff') : t('top.glance');
  });

  async function refreshGlance() {
    try {
      const data = await api.glancePower();
      glance.value = data;
      if (data.along && !settings.modules.glance) settings.modules.glance = true;
    } catch {
      /* 后端还没起来时按钮保持上一次 */
    }
  }

  async function toggleGlance() {
    if (glanceBusy.value) return;
    const next = !glance.value.along;
    glanceBusy.value = true;
    try {
      if (next && !settings.modules.glance) {
        settings.modules.glance = true;
        await settings.save();
      }
      glance.value = await api.glancePowerSet(next, characters.currentId || 0);
      if (glance.value.along) settings.modules.glance = true;
    } catch {
      await refreshGlance();
    } finally {
      glanceBusy.value = false;
    }
  }

  onMounted(() => {
    void refreshGlance();
    timer = window.setInterval(() => { void refreshGlance(); }, 3000);
  });
  onUnmounted(() => window.clearInterval(timer));

  return { glance, glanceBusy, glanceTip, toggleGlance };
}
