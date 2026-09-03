<script setup lang="ts">
import { computed, ref } from 'vue';
import { NButton, NPopover } from 'naive-ui';
import { useCharacterStore } from '../../stores/character';
import { tarotLive } from './gate';
import { tarotUi } from './session';

const PLAYS = [
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

const characters = useCharacterStore();
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
                title="看牌">
        牌
      </n-button>
    </template>
    <div class="pop">
      <p class="lead">{{ live ? (tarotUi.title || '牌还摊着') : '选一种玩法' }}</p>
      <p class="hint">{{ live ? (tarotUi.hint || '仅供娱乐，不构成建议') : '仅供娱乐，不构成建议' }}</p>
      <label v-if="!live" class="ask">
        <span>想问的事（可空）</span>
        <input v-model="question" maxlength="80" placeholder="没有就按眼下讲" />
      </label>
      <div v-if="live" class="ops ritual">
        <button v-if="tarotUi.canCut || tarotUi.phase === 'shuffle'" type="button" :disabled="busy" @click="cut">切牌</button>
        <button v-if="tarotUi.canHerDraw" type="button" :disabled="busy" @click="herDraw">你来抽</button>
        <button v-if="tarotUi.canClarifier" type="button" :disabled="busy" @click="clarifier">再翻一张补</button>
        <button type="button" :disabled="busy" @click="redeal">再抽 / 换牌</button>
        <button type="button" class="ghost" :disabled="busy" @click="pack">收起来</button>
      </div>
      <div v-for="g in PLAYS" :key="g.group" class="group">
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
