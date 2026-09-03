<script setup lang="ts">
import { tarotUi, askAbout, tarotGameLock, doCut, doHerDraw, doReveal, pickPlay } from './session';

function pick(i: number) {
  if (!(tarotUi.revealed || []).includes(i)) {
    void doReveal(i);
    return;
  }
  void askAbout(i);
}

function face(card: { index: number; name: string }) {
  return (tarotUi.revealed || []).includes(card.index);
}

function playLabel(p: { title: string; n: number }) {
  return p.n > 1 ? `${p.title} · ${p.n}张` : p.title;
}
</script>

<template>
  <div class="tarot-layer" aria-live="polite">
    <div class="top">
      <transition name="fade">
        <p v-if="tarotUi.disclaimer" class="note">仅供娱乐，不构成建议</p>
        <p v-else-if="tarotUi.hint" class="note">{{ tarotUi.hint }}</p>
        <p v-else-if="tarotGameLock() && tarotUi.phase === 'open'" class="note">
          看牌中 · 点背面翻开
        </p>
      </transition>
      <transition name="fade">
        <p v-if="tarotUi.caption && tarotUi.phase !== 'off' && tarotUi.phase !== 'leaving'" class="card-name">
          {{ tarotUi.caption }}
        </p>
      </transition>
    </div>
    <div v-if="tarotUi.phase === 'intent' && (tarotUi.plays || []).length" class="plays">
      <button
        v-for="(p, i) in tarotUi.plays"
        :key="p.id"
        type="button"
        class="chip play"
        @click="pickPlay(p.id)"
      >
        <span class="pos">{{ p.index || (i + 1) }}</span>
        <span class="nm">{{ playLabel(p) }}</span>
      </button>
    </div>
    <div class="hud">
      <button v-if="tarotUi.canCut || tarotUi.phase === 'shuffle'" type="button" @click="doCut()">切牌</button>
      <button v-if="tarotUi.canHerDraw" type="button" @click="doHerDraw()">你来抽</button>
    </div>
    <div v-if="tarotUi.cards.length && (tarotUi.phase === 'placed' || tarotUi.phase === 'open' || tarotUi.phase === 'linger' || tarotUi.phase === 'synth')" class="chips">
      <button
        v-for="(card, i) in tarotUi.cards"
        :key="`${card.index}-${i}`"
        type="button"
        class="chip"
        :class="{ on: tarotUi.inspect === (card.index ?? i), back: !face(card) }"
        @click="pick(card.index ?? i)"
      >
        <span class="pos">第{{ (card.index ?? i) + 1 }} · {{ card.position }}</span>
        <span class="nm">{{ face(card) ? card.name : '背面' }}</span>
        <span v-if="face(card) && card.reversed" class="rev">逆</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.tarot-layer {
  position: absolute;
  inset: 0;
  z-index: 8;
  pointer-events: none;
}

.top {
  position: absolute;
  left: 0;
  right: 0;
  top: calc(72px + var(--desk-chrome, 0px));
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.note,
.card-name {
  margin: 0;
  padding: 6px 16px;
  border-radius: 999px;
  letter-spacing: 0.08em;
  text-align: center;
}

.note {
  font-size: 12px;
  color: rgba(245, 228, 186, 0.78);
  background: rgba(10, 8, 16, 0.42);
  border: 1px solid rgba(212, 176, 106, 0.28);
}

.card-name {
  font-size: 14px;
  font-weight: 600;
  color: #f5e4ba;
  background: rgba(10, 8, 16, 0.48);
  border: 1px solid rgba(212, 176, 106, 0.4);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28);
}

.plays {
  pointer-events: auto;
  position: absolute;
  left: 50%;
  bottom: 108px;
  transform: translateX(-50%);
  width: min(560px, calc(100vw - 48px));
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}
.chip.play { max-width: 46%; }

.hud {
  pointer-events: auto;
  position: absolute;
  left: 50%;
  bottom: 88px;
  transform: translateX(-50%);
  display: flex;
  gap: 8px;
}
.hud button {
  appearance: none;
  pointer-events: auto;
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid rgba(212, 176, 106, 0.45);
  background: rgba(10, 8, 16, 0.62);
  color: #f5e4ba;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
}

.chips {
  pointer-events: auto;
  position: absolute;
  left: calc(20px + min(372px, 100vw - 40px) + 12px);
  right: 24px;
  bottom: 22px;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}

.chip {
  appearance: none;
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid rgba(212, 176, 106, 0.32);
  background: rgba(10, 8, 16, 0.52);
  color: #f3e6c6;
  cursor: pointer;
  font: inherit;
}

.chip:hover,
.chip.on {
  border-color: rgba(212, 176, 106, 0.7);
  background: rgba(212, 176, 106, 0.18);
}
.chip.back { opacity: 0.78; }

.pos {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: rgba(212, 176, 106, 0.9);
}

.nm {
  font-size: 13px;
  font-weight: 600;
}

.rev {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 999px;
  background: rgba(212, 176, 106, 0.16);
  color: rgba(245, 228, 186, 0.8);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.35s ease, transform 0.35s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
