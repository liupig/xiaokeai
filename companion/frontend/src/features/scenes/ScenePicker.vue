<script setup lang="ts">
import { NButton } from 'naive-ui';
import { useCharacterStore } from '../../stores/character';
import { useChatStore } from '../../stores/chat';
import { LOCAL_SCENES } from './catalog';
import {
  generateTonight, pickScene, randomScene, sceneExtra, sceneSession,
} from './session';

const characters = useCharacterStore();
const chat = useChatStore();

async function applyAndPlay(card: typeof sceneSession.current) {
  if (!card) return;
  pickScene(card);
  await chat.replayOpening(sceneExtra(card));
}

async function choose(id: string) {
  const card = sceneSession.cards.find((c) => c.id === id)
    || LOCAL_SCENES.find((c) => c.id === id);
  if (card) await applyAndPlay(card);
}

async function randomOne() {
  const card = randomScene();
  await applyAndPlay(card);
}

async function tonight() {
  if (!characters.currentId) return;
  const card = await generateTonight(characters.currentId);
  await applyAndPlay(card);
}
</script>

<template>
  <div class="scenes">
    <div class="row">
      <span class="label">今晚</span>
      <strong>{{ sceneSession.current?.title || '还没定' }}</strong>
      <span class="grow" />
      <n-button size="tiny" quaternary @click="randomOne">随机</n-button>
      <n-button size="tiny" quaternary :loading="sceneSession.generating" @click="tonight">现编</n-button>
    </div>
    <p v-if="sceneSession.current" class="desc">{{ sceneSession.current.setting }}</p>
    <div class="chips">
      <button v-for="c in (sceneSession.cards.length ? sceneSession.cards : LOCAL_SCENES)"
              :key="c.id"
              class="chip" :class="{ on: sceneSession.current?.id === c.id }"
              @click="choose(c.id)">{{ c.title }}</button>
    </div>
  </div>
</template>

<style scoped>
.scenes { padding: 4px 0 8px; }
.row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.label { opacity: 0.45; }
.grow { flex: 1; }
.desc { margin: 6px 0 8px; font-size: 11px; opacity: 0.55; line-height: 1.5; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; max-height: 88px; overflow-y: auto; }
.chip {
  border: 1px solid rgba(255,255,255,0.12);
  background: transparent;
  color: rgba(255,255,255,0.75);
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 11px;
  cursor: pointer;
}
.chip.on { background: #5b5bd6; border-color: #5b5bd6; color: #fff; }
</style>
