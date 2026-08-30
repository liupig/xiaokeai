<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { NButton, NInput, NInputNumber, NPopconfirm, NPopover, useMessage } from 'naive-ui';
import { micAvailable, speechInput } from '../voice/stt';
import { stage } from '../../engine/stage';
import { useChatStore } from '../../stores/chat';
import { useCharacterStore } from '../../stores/character';
import { useSettingsStore } from '../../stores/settings';
import MemoryPanel from '../memory/MemoryPanel.vue';
import { memorySession, refreshMemory } from '../memory/session';
import ScenePicker from '../scenes/ScenePicker.vue';
import { captureClip, captureStill } from '../keepsake/capture';
import { keepsakeSession, refreshKeepsakes, setClipSec } from '../keepsake/session';
import { api } from '../../api/client';

const chat = useChatStore();
const characters = useCharacterStore();
const settings = useSettingsStore();
const message = useMessage();
const input = ref('');
const listening = ref(false);
let voiceDispatched = false;
let markSeq = 0;
let liveMark = -1;
type VoiceStatus = 'hearing' | 'recognizing' | 'sending' | 'sent' | 'hold' | 'drop' | 'echo' | 'fail';
type VoiceMark = { id: number; text: string; status: VoiceStatus };
const voiceMarks = ref<VoiceMark[]>([]);
const statusLabel: Record<VoiceStatus, string> = {
  hearing: '正在听',
  recognizing: '识别中',
  sending: '识别到 · 发送中',
  sent: '已发送',
  hold: '记下了 · 等她说完',
  drop: '附和 · 没打断',
  echo: '像回声 · 没发送',
  fail: '没发出去',
};

function upsertLive(text: string, status: VoiceStatus) {
  const shown = (text || '').trim() || '…';
  if (liveMark >= 0) {
    const row = voiceMarks.value.find((m) => m.id === liveMark);
    if (row) {
      row.text = shown;
      row.status = status;
      return;
    }
  }
  liveMark = ++markSeq;
  voiceMarks.value = [...voiceMarks.value, { id: liveMark, text: shown, status }].slice(-8);
}

function finishLive(status: VoiceStatus) {
  upsertLive(voiceMarks.value.find((m) => m.id === liveMark)?.text || '', status);
  liveMark = -1;
}
const messagesEl = ref<HTMLDivElement | null>(null);
const recastOpen = ref(false);

const partnerName = computed(() => characters.current?.name ?? '她');
const mods = computed(() => settings.modules);
const canRewrite = computed(() =>
  mods.value.rewrite && !!chat.lastQaAssistant()?.content && !chat.sending);

async function send(raw?: string) {
  const text = (raw ?? input.value);
  input.value = '';
  return chat.send(text);
}

function toggleMic() {
  const engine = settings.stt.engine === 'sensevoice' ? 'sensevoice' : 'browser';
  if (!micAvailable(engine)) {
    message.warning(engine === 'sensevoice'
      ? '浏览器不允许访问麦克风'
      : '当前浏览器不支持在线语音识别，请改用 Chrome/Edge，或在设置里切到离线 ASR');
    return;
  }
  if (listening.value) {
    if (engine === 'sensevoice') void speechInput.stopAndRecognize();
    else speechInput.stop();
    return;
  }
  speechInput.engine = engine;
  const ok = speechInput.start(
    (text, isFinal, meta) => {
      if (meta?.asrFail) {
        upsertLive((text || '').trim() || '（没听清）', 'fail');
        liveMark = -1;
        return;
      }
      if (meta?.echo) {
        upsertLive((text || '').trim() || '（像回声）', 'echo');
        liveMark = -1;
        return;
      }
      if (meta?.phase === 'recognizing') {
        const prev = voiceMarks.value.find((m) => m.id === liveMark)?.text;
        upsertLive((prev && prev !== '…' ? prev : text) || '…', 'recognizing');
        return;
      }
      if (text) input.value = text;
      const line = (text || '').trim();
      if (line) upsertLive(line, isFinal ? 'sending' : 'hearing');
      if (!line || voiceDispatched) return;
      if (!isFinal && !chat.peekIngressCut(line)) return;
      voiceDispatched = true;
      input.value = '';
      void (async () => {
        try {
          const act = await send(line);
          finishLive(!act || act === 'empty' ? 'fail' : act);
        } catch {
          finishLive('fail');
        } finally {
          voiceDispatched = false;
        }
      })();
    },
    () => { listening.value = false; },
    () => {
      voiceDispatched = false;
      upsertLive('…', 'hearing');
      chat.onMicStart();
    },
  );
  listening.value = ok;
  if (ok) upsertLive('…', 'hearing');
}

watch(listening, (on) => stage.director.setListening(on));

watch(
  () => [characters.currentId, mods.value.memory] as const,
  ([id, on]) => {
    if (on && id) void refreshMemory(id);
    else if (!on) memorySession.facts = [];
  },
  { immediate: true },
);

watch(
  () => chat.messages.map((m) => m.content).join(''),
  async () => {
    await nextTick();
    messagesEl.value?.scrollTo({ top: messagesEl.value.scrollHeight });
  }
);

function isQaAssistant(m: { role: string; kind?: string }) {
  return m.role === 'assistant' && (!m.kind || m.kind === 'qa');
}

function bubbleSpans(m: { role: string; content: string; spokenLen?: number; speakingFrom?: number; speakingTo?: number }) {
  if (m.role !== 'assistant' || !m.content) return null;
  const spoken = m.spokenLen ?? m.content.length;
  const a = Math.max(0, Math.min(m.content.length, m.speakingFrom ?? spoken));
  const b = Math.max(a, Math.min(m.content.length, m.speakingTo ?? a));
  return {
    read: m.content.slice(0, a),
    reading: m.content.slice(a, b),
    queued: m.content.slice(b),
  };
}

const lastQuote = computed(() => chat.lastQaAssistant()?.content?.slice(0, 40) || '');
const memCount = computed(() => memorySession.facts.length);
const thread = computed(() => chat.messages.map((m) => ({ m, spans: bubbleSpans(m) })));

async function afterKeepsake() {
  if (!characters.currentId) return;
  await refreshKeepsakes(characters.currentId);
  if (mods.value.memory) await refreshMemory(characters.currentId);
}

async function snap() {
  if (!characters.currentId || keepsakeSession.saving) return;
  keepsakeSession.saving = true;
  try {
    const blob = await captureStill();
    await api.uploadKeepsake(characters.currentId, blob, {
      kind: 'still', filename: 'still.jpg', quote: lastQuote.value,
    });
    await afterKeepsake();
    message.success('剧照已收下');
  } catch (e) {
    message.error(String(e));
  } finally {
    keepsakeSession.saving = false;
  }
}

async function record() {
  if (!characters.currentId || keepsakeSession.recording) return;
  const sec = keepsakeSession.clipSec;
  keepsakeSession.recording = true;
  keepsakeSession.recSec = 0;
  try {
    const blob = await captureClip(sec, (s) => { keepsakeSession.recSec = s; });
    keepsakeSession.saving = true;
    const ext = blob.type.includes('mp4') ? 'mp4' : 'webm';
    await api.uploadKeepsake(characters.currentId, blob, {
      kind: 'clip', filename: `clip.${ext}`, quote: lastQuote.value,
    });
    await afterKeepsake();
    message.success(`${sec} 秒短片已收下`);
  } catch (e) {
    message.error(String(e));
  } finally {
    keepsakeSession.recording = false;
    keepsakeSession.saving = false;
    keepsakeSession.recSec = 0;
  }
}

const recLeft = computed(() =>
  Math.max(0, Math.ceil(keepsakeSession.clipSec - keepsakeSession.recSec)));
</script>

<template>
  <div class="chat-dock">
    <MemoryPanel v-if="mods.memory" />
    <div class="chat-head">
      <span class="dot" :class="{ busy: chat.sending }" />
      <span class="title">与 {{ partnerName }} 对话</span>
      <span class="status">{{ chat.sending ? '正在回复…' : `${chat.messages.length} 条` }}</span>
      <button v-if="mods.memory" class="head-btn" :class="{ on: memorySession.open }"
              @click="memorySession.open = !memorySession.open">记忆{{ memCount ? ` ${memCount}` : '' }}</button>
    </div>
    <ScenePicker v-if="mods.scenes" class="scene-slot" />
    <div ref="messagesEl" class="messages">
      <div v-if="!chat.messages.length" class="empty">
        {{ mods.scenes ? '选一场今晚的戏，或直接开口。' : '开始聊天吧，她在等你开口～' }}
      </div>
      <div v-for="(row, i) in thread" :key="row.m.id ?? i"
           class="bubble" :class="[row.m.role, row.m.kind && row.m.kind !== 'qa' ? row.m.kind : '']">
        <p v-if="row.spans" class="bubble-text"><span class="read">{{ row.spans.read }}</span><span
            v-if="row.spans.reading" class="reading">{{ row.spans.reading }}</span><span
            v-if="row.spans.queued" class="queued">{{ row.spans.queued }}</span></p>
        <p v-else>{{ row.m.content || '…' }}</p>
        <div v-if="mods.rewrite && !chat.sending && (row.m.id || (isQaAssistant(row.m) && row.m === chat.lastQaAssistant() && row.m.content))" class="rw">
          <button v-if="isQaAssistant(row.m) && row.m === chat.lastQaAssistant() && row.m.content"
                  @click="chat.rerollLast()">重说</button>
          <n-popconfirm v-if="row.m.id" positive-text="删掉之后的"
                        negative-text="取消"
                        @positive-click="() => { recastOpen = false; return chat.rewindTo(row.m.id!); }">
            <template #trigger>
              <button>回溯</button>
            </template>
            这句之后的对话会从记录里删掉，确定回到这里？
          </n-popconfirm>
          <button v-if="isQaAssistant(row.m) && row.m === chat.lastQaAssistant() && row.m.content"
                  @click="recastOpen = !recastOpen">再演</button>
          <button v-if="row.m.alts?.length" @click="chat.showAlt(row.m, -1)">上一版</button>
        </div>
      </div>
    </div>
    <div v-if="mods.rewrite && recastOpen && canRewrite" class="recast">
      <span>再演一遍</span>
      <button v-for="e in (['happy','angry','sad','relaxed','neutral'] as const)" :key="e"
              @click="chat.recastLast(e); recastOpen = false">
        {{ { happy: '开心', angry: '生气', sad: '伤心', relaxed: '放松', neutral: '自然' }[e] }}
      </button>
    </div>
    <div v-if="voiceMarks.length" class="voice-marks">
      <div v-for="m in voiceMarks" :key="m.id" class="vmark" :class="m.status">
        <span class="vtxt">{{ m.text }}</span>
        <span class="vst">{{ statusLabel[m.status] }}</span>
      </div>
    </div>
    <div class="input-row">
      <n-button v-if="micAvailable(settings.stt.engine === 'sensevoice' ? 'sensevoice' : 'browser')"
                quaternary circle size="small"
                :type="listening ? 'error' : 'default'"
                class="mic" @click="toggleMic">
        {{ listening ? '🔴' : '🎤' }}
      </n-button>
      <n-button v-if="mods.keepsake" quaternary circle size="small"
                :disabled="keepsakeSession.saving || keepsakeSession.recording"
                title="拍一张剧照" @click="snap">📷</n-button>
      <span v-if="mods.keepsake" class="rec-pair">
        <n-popover trigger="click" placement="top"
                   :disabled="keepsakeSession.recording || keepsakeSession.saving">
          <template #trigger>
            <button class="dur" type="button"
                    :disabled="keepsakeSession.recording || keepsakeSession.saving"
                    :title="`录制时长 ${keepsakeSession.clipSec} 秒，点这里改`">
              {{ keepsakeSession.clipSec }}s
            </button>
          </template>
          <div class="dur-pop">
            <p>录几秒</p>
            <div class="dur-chips">
              <button v-for="s in [3, 8, 15, 30]" :key="s" type="button"
                      :class="{ on: keepsakeSession.clipSec === s }"
                      @click="setClipSec(s)">{{ s }}</button>
            </div>
            <n-input-number :value="keepsakeSession.clipSec" size="tiny"
                            :min="1" :max="60" :show-button="true"
                            placeholder="自定义"
                            @update:value="(v: number | null) => v != null && setClipSec(v)" />
          </div>
        </n-popover>
        <n-button quaternary circle size="small"
                  :type="keepsakeSession.recording ? 'error' : 'default'"
                  :disabled="keepsakeSession.saving"
                  :title="keepsakeSession.recording
                    ? `录制中 ${keepsakeSession.recSec.toFixed(0)}s`
                    : `录 ${keepsakeSession.clipSec} 秒`"
                  @click="record">
          {{ keepsakeSession.recording ? recLeft : '⏺' }}
        </n-button>
      </span>
      <n-input
        v-model:value="input" size="small" round
        :placeholder="listening
          ? '持续在听，说完一句就发出；再点红点收麦'
          : '说点什么…（回车发送，点麦克风可持续对话）'"
        @keydown.enter.prevent="send"
      />
      <n-button type="primary" size="small" round
                :loading="chat.sending" :disabled="!input.trim()"
                @click="send">发送</n-button>
    </div>
  </div>
</template>

<style scoped>
/* 左下停靠的对话面板：不遮挡居中的人物 */
.chat-dock {
  position: absolute;
  left: 20px;
  bottom: 20px;
  width: min(372px, calc(100vw - 40px));
  z-index: 10;
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  background: rgba(15, 15, 26, 0.66);
  backdrop-filter: blur(18px);
  border: 1px solid rgba(255, 255, 255, 0.09);
  box-shadow: 0 14px 44px rgba(0, 0, 0, 0.4);
  overflow: visible;
}

.chat-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #4ade80;
  box-shadow: 0 0 6px rgba(74, 222, 128, 0.7);
  flex-shrink: 0;
}

.dot.busy {
  background: #fbbf24;
  box-shadow: 0 0 6px rgba(251, 191, 36, 0.7);
  animation: pulse 1s ease-in-out infinite;
}

@keyframes pulse {
  50% { opacity: 0.35; }
}

.chat-head .title {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.3px;
}

.chat-head .status {
  margin-left: auto;
  font-size: 11px;
  opacity: 0.45;
}

.head-btn {
  border: 1px solid rgba(255,255,255,0.12);
  background: transparent;
  color: rgba(255,255,255,0.7);
  font-size: 11px;
  border-radius: 999px;
  padding: 2px 8px;
  cursor: pointer;
}
.head-btn.on { background: #5b5bd6; border-color: #5b5bd6; color: #fff; }

.scene-slot {
  padding: 6px 12px 0;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}

.bubble p { margin: 0; }

.bubble.assistant .reading {
  color: #ede9fe;
  background: rgba(167, 139, 250, 0.32);
  border-radius: 3px;
  box-decoration-break: clone;
}
.bubble.assistant .queued {
  opacity: 0.4;
}

.rw {
  display: flex;
  gap: 8px;
  margin-top: 6px;
  align-items: center;
}
.rw :deep(.n-popconfirm) { display: inline-flex; }
.rw button, .recast button {
  border: none;
  background: transparent;
  color: rgba(255,255,255,0.45);
  font-size: 11px;
  cursor: pointer;
  padding: 0;
}
.rw button:hover, .recast button:hover { color: #fff; }

.recast {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px 0;
  font-size: 11px;
  opacity: 0.8;
}

/* 高度约等于 2 条消息，历史往上滚动查看 */
.messages {
  max-height: 210px;
  min-height: 66px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.18) transparent;
}

.messages::-webkit-scrollbar {
  width: 4px;
}

.messages::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.18);
  border-radius: 2px;
}

.empty {
  padding: 16px 4px;
  font-size: 12.5px;
  opacity: 0.45;
  text-align: center;
}

.bubble {
  max-width: 86%;
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.bubble.user {
  align-self: flex-end;
  background: #5b5bd6;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.bubble.assistant {
  align-self: flex-start;
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-bottom-left-radius: 4px;
}

.bubble.delayed {
  background: rgba(245, 158, 11, 0.12);
  border: 1px dashed rgba(251, 191, 36, 0.45);
  color: #fde68a;
}

.bubble.proactive {
  background: rgba(20, 184, 166, 0.12);
  border: 1px dashed rgba(45, 212, 191, 0.45);
  color: #99f6e4;
}

.bubble.goodbye {
  background: rgba(148, 163, 184, 0.12);
  border: 1px dashed rgba(148, 163, 184, 0.4);
  color: #cbd5e1;
}

.bubble.welcome {
  background: rgba(129, 140, 248, 0.12);
  border: 1px dashed rgba(165, 180, 252, 0.45);
  color: #c7d2fe;
}

.bubble.user.aside {
  background: rgba(91, 91, 214, 0.35);
  color: rgba(255, 255, 255, 0.72);
  font-size: 12px;
  padding: 5px 10px;
}

.input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.input-row :deep(.n-input) {
  flex: 1;
}

.mic {
  font-size: 14px;
  flex-shrink: 0;
}

.rec-pair {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.dur {
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.55);
  font-size: 11px;
  padding: 0 2px;
  cursor: pointer;
  min-width: 28px;
}

.dur:hover:not(:disabled) { color: #fff; }
.dur:disabled { opacity: 0.4; cursor: default; }

.dur-pop { width: 168px; }
.dur-pop p { margin: 0 0 8px; font-size: 12px; opacity: 0.7; }
.dur-chips { display: flex; gap: 6px; margin-bottom: 8px; }
.dur-chips button {
  flex: 1;
  border: 1px solid rgba(255,255,255,0.14);
  background: transparent;
  color: rgba(255,255,255,0.8);
  border-radius: 8px;
  padding: 4px 0;
  font-size: 12px;
  cursor: pointer;
}
.dur-chips button.on { background: #5b5bd6; border-color: #5b5bd6; color: #fff; }

.voice-marks {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 4px 6px;
  max-height: 120px;
  overflow-y: auto;
}
.vmark {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding: 4px 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  font-size: 12px;
  line-height: 1.4;
}
.vtxt { flex: 1; min-width: 0; word-break: break-word; }
.vst { flex-shrink: 0; font-size: 11px; opacity: 0.85; }
.vmark.hearing { background: rgba(148,163,184,0.12); color: #cbd5e1; border-color: rgba(148,163,184,0.28); }
.vmark.recognizing { background: rgba(56,189,248,0.14); color: #7dd3fc; border-color: rgba(56,189,248,0.4); }
.vmark.sending { background: rgba(245,158,11,0.14); color: #fbbf24; border-color: rgba(245,158,11,0.4); }
.vmark.sent { background: rgba(91,91,214,0.18); color: #c4b5fd; border-color: rgba(91,91,214,0.45); }
.vmark.hold { background: rgba(249,115,22,0.16); color: #fdba74; border-color: rgba(249,115,22,0.4); }
.vmark.drop { background: rgba(100,116,139,0.12); color: #94a3b8; border-color: rgba(100,116,139,0.28); }
.vmark.echo { background: rgba(148,163,184,0.1); color: #94a3b8; border-color: rgba(148,163,184,0.22); }
.vmark.fail { background: rgba(239,68,68,0.16); color: #fca5a5; border-color: rgba(239,68,68,0.4); }
</style>
