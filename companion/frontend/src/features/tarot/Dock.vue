<script setup lang="ts">
import { computed, ref } from 'vue';
import { NButton, NPopover } from 'naive-ui';
import { useCharacterStore } from '../../stores/character';
import { useSettingsStore } from '../../stores/settings';
import { t } from '../../i18n';
import XkIcon from '../icons/XkIcon.vue';
import { tarotLive } from './gate';
import { tarotUi } from './session';

const ZH_PLAYS = [
  { group: '普通', items: [
    { id: 'daily', title: '日抽一张', sub: '今日主题' },
    { id: 'yesno', title: '是否一张', sub: '这件事的倾向' },
    { id: 'three', title: '时间线三张', sub: '过去 / 现在 / 未来' },
    { id: 'advice', title: '行动三张', sub: '现状 / 阻碍 / 建议' },
    { id: 'body', title: '身心三张', sub: '心 / 身 / 气' },
  ]},
  { group: '进阶', items: [
    { id: 'choice', title: '二选一', sub: 'A / B 各三张 + 总建议' },
    { id: 'bond', title: '关系五张', sub: '我、对方、连接、卡住、潜力' },
    { id: 'work', title: '事业五张', sub: '现状、优势、挑战、机会、行动' },
    { id: 'celtic', title: '凯尔特十字', sub: '十字 + 右侧一列' },
  ]},
];

const EN_PLAYS = [
  { group: 'Quick', items: [
    { id: 'daily', title: 'Daily card', sub: 'Today' },
    { id: 'yesno', title: 'Yes or no', sub: 'Which way it leans' },
    { id: 'three', title: 'Three cards', sub: 'Past / present / future' },
    { id: 'advice', title: 'Advice', sub: 'Now / block / next' },
    { id: 'body', title: 'Heart and body', sub: 'Heart / body / breath' },
  ]},
  { group: 'Further', items: [
    { id: 'choice', title: 'Two paths', sub: 'A and B, then advice' },
    { id: 'bond', title: 'The bond', sub: 'Five cards' },
    { id: 'work', title: 'Work', sub: 'Five cards' },
    { id: 'celtic', title: 'Celtic cross', sub: 'Ten cards' },
  ]},
];

const JA_PLAYS = [
  { group: 'ふつう', items: [
    { id: 'daily', title: '今日の一枚', sub: '今日' },
    { id: 'yesno', title: 'はい・いいえ', sub: '傾き' },
    { id: 'three', title: '三枚', sub: '過去 / 現在 / 未来' },
    { id: 'advice', title: '助言', sub: '現状 / 妨げ / 次' },
    { id: 'body', title: '心と体', sub: '心 / 体 / 息' },
  ]},
  { group: 'さらに', items: [
    { id: 'choice', title: '二つに一つ', sub: 'A と B' },
    { id: 'bond', title: '関係', sub: '五枚' },
    { id: 'work', title: '仕事', sub: '五枚' },
    { id: 'celtic', title: 'ケルト十字', sub: '十枚' },
  ]},
];

const KO_PLAYS = [
  { group: '보통', items: [
    { id: 'daily', title: '오늘의 한 장', sub: '오늘' },
    { id: 'yesno', title: '예 또는 아니오', sub: '기울기' },
    { id: 'three', title: '세 장', sub: '과거 / 현재 / 미래' },
    { id: 'advice', title: '조언', sub: '지금 / 막힘 / 다음' },
    { id: 'body', title: '마음과 몸', sub: '마음 / 몸 / 숨' },
  ]},
  { group: '더', items: [
    { id: 'choice', title: '둘 중 하나', sub: 'A 와 B' },
    { id: 'bond', title: '관계', sub: '다섯 장' },
    { id: 'work', title: '일', sub: '다섯 장' },
    { id: 'celtic', title: '켈틱 크로스', sub: '열 장' },
  ]},
];

const characters = useCharacterStore();
const settings = useSettingsStore();
const plays = computed(() => {
  const ui = settings.locale.ui;
  if (ui === 'ja') return JA_PLAYS;
  if (ui === 'ko') return KO_PLAYS;
  if (ui === 'en') return EN_PLAYS;
  return ZH_PLAYS;
});
const open = ref(false);
const busy = ref(false);
const question = ref('');
const live = computed(() => tarotLive.value);

async function go(spread: string) {
  if (!characters.currentId || busy.value) return;
  open.value = false;
  busy.value = true;
  try {
    const { beginPlay } = await import('./session');
    await beginPlay(characters.currentId, spread, question.value.trim());
  } finally {
    busy.value = false;
  }
}

async function pack() {
  if (!characters.currentId || busy.value) return;
  open.value = false;
  busy.value = true;
  try {
    const { dismissAndSpeak } = await import('./session');
    await dismissAndSpeak(characters.currentId);
  } finally {
    busy.value = false;
  }
}

async function cut() {
  if (busy.value) return;
  busy.value = true;
  try {
    const { doCut } = await import('./session');
    await doCut(`dock-${Date.now()}`);
  } finally {
    busy.value = false;
  }
}

async function herDraw() {
  if (busy.value) return;
  busy.value = true;
  try {
    const { doHerDraw } = await import('./session');
    await doHerDraw();
  } finally {
    busy.value = false;
  }
}

async function clarifier() {
  if (busy.value) return;
  busy.value = true;
  try {
    const { doClarifier } = await import('./session');
    await doClarifier();
  } finally {
    busy.value = false;
  }
}

async function redeal() {
  if (!characters.currentId || busy.value) return;
  open.value = false;
  busy.value = true;
  try {
    const { redealAndSpeak } = await import('./session');
    await redealAndSpeak(characters.currentId);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <n-popover trigger="click" placement="top" :show="open" @update:show="(v: boolean) => { open = v; }">
    <template #trigger>
      <n-button quaternary circle size="small"
                :type="live ? 'primary' : 'default'"
                :disabled="busy"
                :title="t('tarot.mark')">
        <XkIcon name="tarot" :size="18" />
      </n-button>
    </template>
    <div class="pop">
      <p class="lead">{{ live ? (tarotUi.title || t('tarot.still')) : t('tarot.pick') }}</p>
      <p class="hint">{{ live ? (tarotUi.hint || t('tarot.note')) : t('tarot.note') }}</p>
      <label v-if="!live" class="ask">
        <span>{{ t('tarot.ask') }}</span>
        <input v-model="question" maxlength="80" :placeholder="t('tarot.askPh')" />
      </label>
      <div v-if="live" class="ops ritual">
        <button v-if="tarotUi.canCut || tarotUi.phase === 'shuffle'" type="button" :disabled="busy" @click="cut">{{ t('tarot.cut') }}</button>
        <button v-if="tarotUi.canHerDraw" type="button" :disabled="busy" @click="herDraw">{{ t('tarot.her') }}</button>
        <button v-if="tarotUi.canClarifier" type="button" :disabled="busy" @click="clarifier">{{ t('tarot.extra') }}</button>
        <button type="button" :disabled="busy" @click="redeal">{{ t('tarot.redeal') }}</button>
        <button type="button" class="ghost" :disabled="busy" @click="pack">{{ t('tarot.pack') }}</button>
      </div>
      <div v-for="g in plays" :key="g.group" class="group">
        <p class="g">{{ g.group }}</p>
        <div class="ops">
          <button
            v-for="p in g.items"
            :key="p.id"
            type="button"
            :disabled="busy"
            @click="go(p.id)"
          >
            <strong>{{ p.title }}</strong>
            <span>{{ p.sub }}</span>
          </button>
        </div>
      </div>
    </div>
  </n-popover>
</template>

<style scoped>
.pop {
  width: 268px;
  max-height: min(72vh, 560px);
  overflow: auto;
  padding: 2px 2px 4px;
}
.lead {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 600;
  color: #f5e4ba;
}
.hint {
  margin: 0 0 10px;
  font-size: 11px;
  letter-spacing: 0.04em;
  color: rgba(255, 255, 255, 0.48);
}
.ask {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
  font-size: 11px;
  color: rgba(245, 228, 186, 0.7);
}
.ask input {
  appearance: none;
  border: 1px solid rgba(212, 176, 106, 0.28);
  background: rgba(0, 0, 0, 0.28);
  color: #f3e6c6;
  border-radius: 8px;
  padding: 6px 8px;
  font: inherit;
}
.group { margin-bottom: 8px; }
.g {
  margin: 0 0 4px;
  font-size: 10px;
  letter-spacing: 0.12em;
  color: rgba(212, 176, 106, 0.7);
}
.ops {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ops.ritual { margin-bottom: 10px; }
.ops button {
  appearance: none;
  border: 1px solid rgba(212, 176, 106, 0.35);
  background: rgba(212, 176, 106, 0.12);
  color: #f3e6c6;
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ops button span {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.48);
  font-weight: 400;
}
.ops button:hover:not(:disabled) {
  background: rgba(212, 176, 106, 0.22);
}
.ops button.ghost {
  border-color: rgba(255, 255, 255, 0.14);
  background: transparent;
  color: rgba(255, 255, 255, 0.72);
  text-align: center;
  display: block;
}
.ops button:disabled {
  opacity: 0.45;
  cursor: default;
}
</style>
