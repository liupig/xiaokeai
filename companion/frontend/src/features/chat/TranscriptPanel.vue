<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue';
import { NDrawer, NDrawerContent, NTabPane, NTabs } from 'naive-ui';
import { api, type TalkLogLine } from '../../api/client';
import { useChatStore } from '../../stores/chat';
import { friendlyWhen } from './when';

const props = defineProps<{ show: boolean }>();
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>();

const chat = useChatStore();
const tab = ref<'talk' | 'log'>('talk');
const lines = ref<TalkLogLine[]>([]);
const logWhen = ref('');
let timer = 0;

const turns = computed(() => chat.messages.filter((m) => m.kind !== 'aside'));

function sameText(a?: string, b?: string) {
  return (a || '').replace(/\s+/g, '') === (b || '').replace(/\s+/g, '');
}

async function refreshLog() {
  try {
    const r = await api.getTalkLog(500);
    lines.value = r.lines || [];
    logWhen.value = r.when || '';
  } catch {
    lines.value = [];
  }
}

watch(() => props.show, (on) => {
  if (on) {
    void refreshLog();
    timer = window.setInterval(() => { void refreshLog(); }, 2500);
  } else if (timer) {
    window.clearInterval(timer);
    timer = 0;
  }
});

onUnmounted(() => {
  if (timer) window.clearInterval(timer);
});
</script>

<template>
  <n-drawer :show="show" @update:show="(v: boolean) => emit('update:show', v)"
            :width="460" placement="right" show-mask="transparent" to="body">
    <n-drawer-content title="会话记录" closable :native-scrollbar="false">
      <n-tabs v-model:value="tab" type="line" size="small">
        <n-tab-pane name="talk" tab="对话对照">
          <p class="hint">气泡里是实际播出的。这里还能看到模型完整回复；插话没念完的会标成未播出。</p>
          <div v-if="!turns.length" class="empty">还没有对话。</div>
          <div v-for="(m, i) in turns" :key="m.id ?? i" class="turn" :class="m.role">
            <div class="meta">
              <span class="who">{{ m.role === 'user' ? '对方' : '她' }}</span>
              <span class="time">{{ friendlyWhen(m.when, m.created_at) }}</span>
            </div>
            <p v-if="m.role === 'user'" class="body">{{ m.content }}</p>
            <template v-else>
              <div class="block">
                <span class="tag">完整回复</span>
                <p class="body">{{ m.fullContent || m.content || '…' }}</p>
              </div>
              <div v-if="m.content && !sameText(m.content, m.fullContent || m.content)" class="block spoken">
                <span class="tag">实际播出</span>
                <p class="body">{{ m.content }}</p>
              </div>
              <div v-else-if="m.content" class="ok">实际播出与完整回复相同</div>
              <div v-else class="wait">还没开口</div>
            </template>
          </div>
        </n-tab-pane>
        <n-tab-pane name="log" tab="后台日志">
          <p class="hint">今天的流水账，时间是本机本地时间{{ logWhen ? `（刷新于 ${friendlyWhen(logWhen)}）` : '' }}。</p>
          <div v-if="!lines.length" class="empty">还没有日志。说一句之后会写到这里。</div>
          <div v-for="(row, i) in lines" :key="i" class="log" :class="row.kind">
            <span class="time">{{ friendlyWhen(row.t) }}</span>
            <span class="kind">{{ row.kind_cn || row.kind }}</span>
            <span class="txt">{{ row.text }}</span>
          </div>
        </n-tab-pane>
      </n-tabs>
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
.hint {
  font-size: 12px;
  opacity: 0.55;
  margin: 0 0 12px;
  line-height: 1.5;
}
.empty { font-size: 13px; opacity: 0.45; padding: 24px 0; }
.turn {
  padding: 10px 0 12px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
}
.who { font-weight: 600; }
.turn.user .who { color: #93c5fd; }
.turn.assistant .who { color: #c4b5fd; }
.time { opacity: 0.45; font-variant-numeric: tabular-nums; }
.body { font-size: 13px; line-height: 1.55; white-space: pre-wrap; word-break: break-word; }
.block { margin-top: 6px; }
.tag {
  display: inline-block;
  font-size: 11px;
  opacity: 0.55;
  margin-bottom: 4px;
}
.block.spoken .tag { color: #86efac; opacity: 0.9; }
.ok { margin-top: 6px; font-size: 12px; color: #86efac; opacity: 0.8; }
.wait { margin-top: 6px; font-size: 12px; opacity: 0.4; }
.log {
  display: grid;
  grid-template-columns: 76px 64px 1fr;
  gap: 8px;
  align-items: start;
  padding: 6px 0;
  font-size: 12px;
  line-height: 1.45;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}
.log .time { opacity: 0.45; font-variant-numeric: tabular-nums; }
.log .kind { opacity: 0.75; }
.log .txt { word-break: break-word; }
.log.user .kind { color: #93c5fd; }
.log.full .kind { color: #c4b5fd; }
.log.spoken .kind { color: #86efac; }
.log.unsaid .kind { color: #fbbf24; }
.log.tts .kind { color: #67e8f9; }
.log.asr .kind { color: #fdba74; }
</style>
