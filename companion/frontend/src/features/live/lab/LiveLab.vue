<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { playLiveTurn, type LiveTurn, type PlaybackOutcome } from '../playback';
import { speechPlayer } from '../../voice/tts';
import { useSettingsStore } from '../../../stores/settings';
import { useCharacterStore } from '../../../stores/character';
import { useAssetsStore } from '../../../stores/assets';
import { caster } from '../../performance/caster';
import { shots } from '../../performance/shotConductor';
import StageView from '../../stage/StageView.vue';

type Trace = { seq: number; at: number; kind: string; data: Record<string, any> };
type Scenario = { id: string; name: string; description: string; duration: number; events: number };
type Snapshot = { run_id: string; state: string; mode: string; scenario: string; elapsed: number; duration: number; emitted: number; total: number;
  disconnected: boolean; trace: Trace[]; host: { turn: LiveTurn | null; queue: number; health: { last_error: string };
    processing: { intake: { accepted?: number; duplicate?: number }; expired: number; overflow: number; playback_failures: number; generating: boolean } } | null };
const scenarios = ref<Scenario[]>([]);
const scenario = ref('mixed');
const mode = ref('scripted');
const voice = ref('browser');
const speed = ref('1');
const configuredReady = ref(false);
const modelName = ref('');
const snapshot = ref<Snapshot | null>(null);
const trace = ref<Trace[]>([]);
const history = ref<Array<{ run_id: string; scenario_name: string; mode: string }>>([]);
const error = ref('');
const working = ref(false);
const playing = ref(false);
const current = ref<LiveTurn | null>(null);
const playbackState = ref('等待开始');
const nickname = ref('我');
const content = ref('');
const failNext = ref(false);
const stageReady = ref(false);
const report = ref<{ run_id: string; mode: string; scenario_name: string; summary: { received: number; turns: number; pending_paid: number; model_failures: number; real_model_responses: number; outcomes: Record<string, number> }; checks: Record<string, boolean> } | null>(null);
const feed = ref<HTMLElement | null>(null);
let cursor = 0;
let polling = false;
let timer: ReturnType<typeof setInterval>;
let playbackAbort: AbortController | null = null;
let seen = '';
let pendingAck: { turn_id: string; outcome: PlaybackOutcome } | null = null;
let clientId = 0;
const playerToken = crypto.randomUUID();
let closed = false;
let reportState = '';
const live = computed(() => ['running', 'paused', 'draining'].includes(snapshot.value?.state || ''));
const selected = computed(() => scenarios.value.find(s => s.id === scenario.value));
const incoming = computed(() => trace.value.filter(r => r.kind === 'received').slice(-70));
const conversation = computed(() => trace.value.filter(r => r.kind === 'turn').slice(-30));
const receipts = computed(() => trace.value.filter(r => r.kind === 'ack'));
const faultLog = computed(() => trace.value.filter(r => ['fault', 'model_failure', 'source_disconnected', 'source_reconnected', 'error'].includes(r.kind)).slice(-12));
const states: Record<string, string> = { idle: '尚未开始', running: '正在试播', paused: '弹幕已暂停', draining: '收尾中', completed: '彩排完成', stopped: '已停止', error: '运行异常' };
const outcomes: Record<string, string> = { completed: '播放完成', displayed: '仅文字展示', failed: '播放失败', interrupted: '被打断' };

async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/live-lab/${path}`, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `请求失败 ${response.status}`);
  }
  return response.json();
}

async function action(fn: () => Promise<void>) {
  working.value = true;
  error.value = '';
  try { await fn(); } catch (e) { error.value = e instanceof Error ? e.message : String(e); }
  finally { working.value = false; }
}

function cancelPlayback() {
  playbackAbort?.abort();
  playbackAbort = null;
  speechPlayer.onUserBargeIn();
  playing.value = false;
}

async function begin() {
  await action(async () => {
    cancelPlayback();
    clientId += 1;
    pendingAck = null;
    seen = '';
    if (voice.value === 'product') {
      await useSettingsStore().load();
      useSettingsStore().applyTts();
    } else speechPlayer.engine = voice.value === 'text' ? 'off' : 'browser';
    speechPlayer.unlock();
    snapshot.value = await api<Snapshot>('start', { scenario: scenario.value, mode: mode.value, speed: Number(speed.value) });
    trace.value = snapshot.value.trace;
    cursor = trace.value.length ? trace.value[trace.value.length - 1].seq : 0;
    current.value = null;
    report.value = null;
    playbackState.value = '等待第一轮回应';
    await poll();
  });
}

async function stop() {
  await action(async () => {
    const interrupted = current.value;
    cancelPlayback();
    if (interrupted && playing.value === false && seen === interrupted.id) {
      await api('ack', { turn_id: interrupted.id, outcome: 'interrupted', player_id: playerToken });
    }
    clientId += 1;
    pendingAck = null;
    snapshot.value = await api<Snapshot>('stop', {});
    playbackState.value = '已停止播报';
    await poll();
  });
}

async function consume(turn: LiveTurn) {
  const generation = clientId;
  const controller = new AbortController();
  playbackAbort = controller;
  current.value = turn;
  playing.value = true;
  playbackState.value = voice.value === 'text' ? '展示文字' : '正在播报';
  let outcome: PlaybackOutcome = 'failed';
  try {
    if (failNext.value) { failNext.value = false; outcome = 'failed'; }
    else outcome = await playLiveTurn(turn, controller.signal);
  } catch (e) { error.value = String(e); }
  if (closed || generation !== clientId) return;
  playing.value = false;
  playbackState.value = outcomes[outcome];
  pendingAck = { turn_id: turn.id, outcome };
  await poll();
}

async function poll() {
  if (polling || closed) return;
  polling = true;
  const generation = clientId;
  try {
    if (pendingAck) {
      const ack = pendingAck;
      await api('ack', { ...ack, player_id: playerToken });
      if (pendingAck === ack) pendingAck = null;
    }
    const data = await api<Snapshot>(`state?after=${cursor}`);
    if (closed || generation !== clientId) return;
    if (snapshot.value?.run_id && snapshot.value.run_id !== data.run_id) {
      cancelPlayback(); clientId += 1; seen = ''; trace.value = []; cursor = 0;
      snapshot.value = data;
      return;
    }
    if (!snapshot.value?.run_id && data.run_id) { mode.value = data.mode; scenario.value = data.scenario; }
    snapshot.value = data;
    if (data.trace.length) {
      trace.value = [...trace.value, ...data.trace].slice(-5000);
      cursor = data.trace[data.trace.length - 1].seq;
      await nextTick();
      if (feed.value) feed.value.scrollTop = feed.value.scrollHeight;
      if (!current.value && !live.value) {
        const last = [...data.trace].reverse().find(row => row.kind === 'turn');
        if (last) {
          current.value = last.data as LiveTurn;
          playbackState.value = statusFor(last.data.id);
        }
      }
    }
    if (!live.value && playing.value) cancelPlayback();
    const reportKey = `${data.run_id}:${data.state}`;
    if (data.run_id && !live.value && reportState !== reportKey) {
      await loadReport(data.run_id);
      reportState = reportKey;
    }
    const turn = data.host?.turn;
    if (turn && live.value && !playing.value && turn.id !== seen) {
      if (!(await api<{ ok: boolean }>('claim', { turn_id: turn.id, player_id: playerToken })).ok) {
        playbackState.value = '另一窗口正在播报';
        return;
      }
      seen = turn.id;
      void consume(turn);
    }
  } catch (e) { error.value = e instanceof Error ? e.message : String(e); }
  finally { polling = false; }
}

async function loadReport(run: string) {
  report.value = await api(`report?run_id=${encodeURIComponent(run)}`);
}

async function recover(run: string) {
  await action(async () => {
    cancelPlayback(); clientId += 1; pendingAck = null; seen = '';
    if (voice.value === 'product') { await useSettingsStore().load(); useSettingsStore().applyTts(); }
    else speechPlayer.engine = voice.value === 'text' ? 'off' : 'browser';
    speechPlayer.unlock();
    snapshot.value = await api<Snapshot>('recover', { run_id: run });
    mode.value = snapshot.value.mode;
    trace.value = snapshot.value.trace;
    cursor = trace.value.length ? trace.value[trace.value.length - 1].seq : 0;
    current.value = null; report.value = null;
  });
}

async function inject(kind = 'comment') {
  await action(async () => {
    const text = kind === 'gift' ? '送出 小心心×1' : content.value.trim();
    if (!text) return;
    await api('inject', { nickname: nickname.value || '我', content: text, kind, gift: '小心心', count: 1 });
    content.value = '';
    await poll();
  });
}

async function fault(kind: string) {
  await action(async () => { await api('fault', { kind }); await poll(); });
}

async function loadStage() {
  await action(async () => {
    await nextTick();
    const assets = useAssetsStore(), chars = useCharacterStore();
    await Promise.all([assets.refresh(), chars.loadList()]);
    if (!chars.currentId) throw new Error('尚未安装角色模型。可继续使用下方音频舞台验收。');
    await chars.switchTo(chars.currentId);
    if (chars.modelError || !chars.modelInfo) throw new Error(chars.modelError || '角色模型未加载成功');
    caster.indexFrom(assets.motions, chars.modelInfo?.morphNames || []);
    shots.indexFrom(assets.cameras);
    stageReady.value = true;
  });
}

function statusFor(id: string) { return outcomes[receipts.value.find(r => r.data.id === id)?.data.outcome] || '等待播放回执'; }
function time(at: number) { return new Date(at * 1000).toLocaleTimeString('zh-CN', { hour12: false }); }
onMounted(async () => {
  try {
    const config = await api<{ scenarios: Scenario[]; configured_model_ready: boolean; model: string; history: typeof history.value }>('config');
    scenarios.value = config.scenarios;
    configuredReady.value = config.configured_model_ready;
    modelName.value = config.model;
    history.value = config.history;
    await poll();
  } catch (e) { error.value = String(e); }
  timer = setInterval(() => { void poll(); }, 500);
});
onBeforeUnmount(() => { closed = true; clearInterval(timer); cancelPlayback(); });
</script>

<template>
  <main class="lab">
    <header class="top"><a class="brand" href="/live-lab.html">小伴 <span>LIVE LAB</span></a><div class="safe">隔离彩排 · 不连接真实直播平台</div><a href="/" class="quiet-link">返回</a></header>
    <section class="intro"><div><p class="eyebrow">先把直播体验跑通</p><h1>让弹幕进来，让对话发生。</h1><p>虚构观众，真实的选题、排队与播报链路。可以旁观，也可以自己发一句。</p></div><div class="session-state"><i :class="{ active: live }"></i>{{ states[snapshot?.state || 'idle'] }}</div></section>
    <div v-if="error" role="alert" class="error">{{ error }}<button @click="error = ''" aria-label="关闭错误">×</button></div>
    <section class="controls" aria-label="彩排设置">
      <label>试播场景<select v-model="scenario" :disabled="live"><option v-for="s in scenarios" :key="s.id" :value="s.id">{{ s.name }} · {{ s.duration }} 秒</option></select></label>
      <label>回应来源<select v-model="mode" :disabled="live"><option value="scripted">脚本替身 · 零凭据</option><option value="configured" :disabled="!configuredReady">真实模型{{ configuredReady ? ` · ${modelName}` : ' · 尚未配置' }}</option></select></label>
      <label>播报方式<select v-model="voice" :disabled="live"><option value="browser">浏览器中文语音</option><option value="product">产品已配置的语音引擎</option><option value="text">仅文字 · 不计作有声验收</option></select></label>
      <label class="speed">弹幕速度<select v-model="speed" :disabled="live"><option value="0.5">0.5×</option><option value="1">1×</option><option value="2">2×</option><option value="4">4×</option></select></label>
      <button class="primary" :disabled="working || live" @click="begin">开始彩排</button><button v-if="live" :disabled="working" @click="stop">停止</button>
    </section>
    <p class="scenario-note">{{ selected?.description }}<span v-if="mode === 'scripted'"> · 脚本替身只验证流程，回答质量请切换真实模型验收。</span></p>
    <section class="workspace">
      <div class="show">
        <div class="show-head"><span><i class="dot"></i> 主播舞台</span><span>{{ mode === 'scripted' ? '脚本替身' : '真实模型' }} / {{ voice === 'text' ? '文字' : voice === 'browser' ? '浏览器语音' : '产品语音' }}</span></div>
        <div class="broadcast-stage" :class="{ speaking: playing }">
          <div class="model-stage" :style="{ visibility: stageReady ? 'visible' : 'hidden' }"><StageView /></div>
          <div v-if="!stageReady" class="audio-stage"><div class="avatar" aria-label="音频舞台"><span>伴</span></div><div class="wave" aria-hidden="true"><i v-for="n in 15" :key="n" :style="{ animationDelay: `${n * .08}s` }"></i></div><p>{{ playbackState }}</p></div>
          <div class="caption" aria-live="polite">{{ current?.text || '按下开始，观众会陆续进场。' }}</div>
        </div>
        <div class="stage-toolbar"><button :disabled="working || stageReady" @click="loadStage">{{ stageReady ? '已加载产品角色' : '加载已安装的 3D 角色' }}</button><span>使用正式直播的播放入口</span><button v-if="playing" @click="cancelPlayback">打断当前播报</button></div>
        <div class="progress"><div :style="{ width: `${(snapshot?.elapsed || 0) / (snapshot?.duration || 1) * 100}%` }"></div></div>
        <div class="progress-label"><span>场景 {{ snapshot?.elapsed || 0 }} / {{ snapshot?.duration || selected?.duration || 0 }} 秒</span><span>已送入 {{ snapshot?.emitted || 0 }} / {{ snapshot?.total || selected?.events || 0 }} 条</span></div>
        <section class="transcript"><div class="section-head"><h2>主播回应</h2><a v-if="snapshot?.run_id" :href="`/api/live-lab/report?run_id=${snapshot.run_id}`" download>导出验收记录 JSON ↓</a></div>
          <p v-if="!conversation.length" class="empty">每轮会显示选中了哪些弹幕，以及语音是否真的播放完成。</p>
          <article v-for="row in conversation.slice().reverse()" :key="row.seq" class="reply"><div class="reply-meta"><span>{{ time(row.at) }} · {{ row.data.cue === 'gift' ? '感谢支持' : row.data.cue === 'idle' ? '主动开口' : '接住话题' }}</span><span>{{ statusFor(row.data.id) }}</span></div><p>{{ row.data.text }}</p><div v-if="row.data.sources?.length" class="sources">回应对象：{{ row.data.sources.map((s: any) => `${s.nickname}「${s.content}」`).join(' · ') }}</div></article>
        </section>
      </div>
      <aside class="audience"><div class="section-head"><h2>观众席</h2><span>{{ snapshot?.disconnected ? '接入暂时断开' : '模拟弹幕源' }}</span></div><div ref="feed" class="feed" aria-label="观众弹幕"><p v-if="!incoming.length" class="empty">小雨、阿哲、泡芙正在等候开场。你也可以加入。</p><article v-for="row in incoming" :key="row.seq" :class="{ gift: row.data.kind === 'gift' }"><div><b>{{ row.data.nickname }}</b><time>{{ time(row.at) }}</time></div><p>{{ row.data.content }}</p></article></div><form class="composer" @submit.prevent="inject()"><input v-model="nickname" aria-label="观众昵称" maxlength="24" placeholder="你的昵称"><textarea v-model="content" aria-label="发送弹幕" placeholder="发一句，看看主播怎么接……" maxlength="300" :disabled="!live" @keydown.ctrl.enter.prevent="inject()"></textarea><div><button :disabled="!live || working" @click.prevent="inject('gift')">模拟送小心心</button><button class="primary" :disabled="!live || working || !content.trim()">发送弹幕</button></div></form></aside>
    </section>
    <section class="diagnostics"><div><h2>故障演练</h2><p>故障会写入本轮记录，不影响正式直播配置。</p><div class="fault-buttons"><button :disabled="!live" @click="fault('duplicate')">重复投递上一条</button><button :disabled="!live" @click="fault('disconnect')">接入断开 6 秒</button><button :disabled="!live" @click="fault('model')">下一次模型失败</button><button :disabled="!live" @click="failNext = true">{{ failNext ? '下一次播报将失败' : '下一次播报失败' }}</button><button :disabled="!['running','paused'].includes(snapshot?.state || '')" @click="action(async () => { await api('pause', { paused: snapshot?.state !== 'paused' }); await poll(); })">{{ snapshot?.state === 'paused' ? '继续弹幕' : '暂停弹幕源' }}</button></div><p v-for="row in faultLog.slice().reverse()" :key="row.seq" class="fault-line">{{ time(row.at) }} · {{ ({ fault: '故障已注入', model_failure: '模型失败，进入兜底', source_disconnected: '接入断开', source_reconnected: '接入已恢复', error: '运行异常' } as Record<string,string>)[row.kind] }} {{ row.data.kind || row.data.message || '' }}</p></div><div class="metrics"><h2>处理状态</h2><dl><div><dt>待处理</dt><dd>{{ snapshot?.host?.queue || 0 }}</dd></div><div><dt>过滤重复</dt><dd>{{ snapshot?.host?.processing.intake.duplicate || 0 }}</dd></div><div><dt>过期 / 溢出</dt><dd>{{ snapshot?.host?.processing.expired || 0 }} / {{ snapshot?.host?.processing.overflow || 0 }}</dd></div><div><dt>完成 / 失败</dt><dd>{{ receipts.filter(r => r.data.outcome === 'completed').length }} / {{ receipts.filter(r => r.data.outcome === 'failed').length }}</dd></div></dl><p v-if="snapshot?.host?.health.last_error">{{ snapshot.host.health.last_error }}</p></div></section>
    <section v-if="report" class="report">
      <div class="section-head"><h2>验收记录 · {{ report.scenario_name }}</h2><a :href="`/api/live-lab/report?run_id=${report.run_id}`" download>下载完整记录 ↓</a></div>
      <p>收到 {{ report.summary.received }} 条消息，产生 {{ report.summary.turns }} 轮回应。
        有声完成 {{ report.summary.outcomes.completed || 0 }} 轮，失败 {{ report.summary.outcomes.failed || 0 }} 轮，待补播礼物 {{ report.summary.pending_paid }} 条。</p>
      <p>{{ report.checks.source_completed ? '场景已完整结束' : '场景未完整结束' }} · {{ report.checks.has_playback_evidence ? '已有真实播放完成回执' : '尚无真实有声播放证据' }} · {{ report.checks.no_unsettled_paid ? '礼物回执完整' : '存在未完成的礼物回应' }}</p>
      <p v-if="report.mode === 'configured'">真实模型成功回应 {{ report.summary.real_model_responses || 0 }} 次，调用失败 {{ report.summary.model_failures }} 次。{{ !report.summary.real_model_responses ? '本轮只有兜底，真实模型验收未通过。' : '' }}</p>
      <button v-if="report.summary.pending_paid" :disabled="working || live" @click="recover(report.run_id)">补播未完成的礼物</button>
    </section>
    <footer><span>脚本与语音分别标注；播放失败会如实记录，不会算作成功。</span><details v-if="history.length"><summary>历史彩排记录</summary><div v-for="run in history" :key="run.run_id"><a :href="`/api/live-lab/report?run_id=${run.run_id}`" download>{{ run.scenario_name }} · {{ run.mode }} · {{ run.run_id.slice(0, 8) }} ↓</a><button @click="action(() => loadReport(run.run_id))">查看与补播</button></div></details></footer>
  </main>
</template>

<style scoped>
:global(*){box-sizing:border-box}:global(body){margin:0;background:#0e1217;color:#dce2e8;font-family:Inter,'Microsoft YaHei',sans-serif;font-size:14px}:global(button),:global(input),:global(select),:global(textarea){font:inherit}:global(button),:global(a),:global(select){touch-action:manipulation}button,a,select,input,textarea{outline-offset:4px}button{cursor:pointer;background:#212a34;border:1px solid #35404c;border-radius:7px;padding:9px 13px;color:#e1e8ef}button:hover:enabled{background:#2e3c49}button:disabled{opacity:.4;cursor:default}a{color:#88cdb9;text-decoration:none}.lab{max-width:1440px;padding:0 36px 32px;margin:auto}.top{height:76px;display:flex;align-items:center;border-bottom:1px solid #29313a;gap:26px}.brand{font-size:20px;color:#f0f4f7;font-weight:700}.brand span{margin-left:10px;font-size:11px;letter-spacing:2px;color:#82919f}.safe{font-size:12px;color:#82919f}.quiet-link{margin-left:auto;color:#9ca9b5}.intro{display:flex;align-items:center;justify-content:space-between;padding:32px 0 24px;gap:15px}.eyebrow{color:#88cdb9;font-size:12px;margin:0 0 10px}h1{font-weight:500;font-size:28px;letter-spacing:.03em;margin:0 0 12px}.intro p:last-child{margin:0;color:#95a4b2;font-size:13px}.session-state{color:#b5c4cf;font-size:13px;white-space:nowrap}.session-state i,.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#71808e;margin-right:8px}.session-state i.active{background:#8dd1b5}.controls{display:flex;gap:12px;align-items:end;padding:18px;background:#171e26;border:1px solid #2c3540;border-radius:10px}.controls label{display:flex;flex:1;flex-direction:column;gap:8px;font-size:11px;color:#9daab7}.controls .speed{flex:.5}select,input,textarea{background:#10171e;color:#dde5ec;border:1px solid #36414d;padding:9px 10px;border-radius:6px;width:100%;min-width:0}select{height:38px}.primary{background:#a6d9c5;color:#12281f;border-color:#a6d9c5;font-weight:600;white-space:nowrap}.primary:hover:enabled{background:#bfebd8}.scenario-note{font-size:11px;color:#8b9aa8;line-height:1.8;margin:12px 0 20px}.workspace{display:grid;grid-template-columns:minmax(0,1.8fr) minmax(300px,1fr);gap:20px}.show{min-width:0}.show-head{display:flex;justify-content:space-between;padding:13px 18px;background:#171e26;border:1px solid #2c3540;border-radius:10px 10px 0 0;font-size:12px}.show-head>span:last-child{color:#8f9fac;font-size:11px}.broadcast-stage{height:330px;background:#111920;position:relative;overflow:hidden;border:1px solid #2c3540;border-top:0}.model-stage{position:absolute;inset:0}.audio-stage{position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;height:255px}.avatar{width:86px;height:86px;border-radius:24px;background:#263e39;display:grid;place-items:center;border:1px solid #4b6b60;color:#b7e2d2;font-size:36px;font-weight:300;transition:transform .3s}.speaking .avatar{transform:translateY(-3px)}.audio-stage p{font-size:11px;color:#8da99f;margin:9px}.wave{height:27px;display:flex;gap:4px;align-items:center;margin-top:15px}.wave i{width:3px;height:5px;background:#659784;border-radius:2px}.speaking .wave i{animation:wave .65s ease-in-out infinite alternate}@keyframes wave{to{height:24px}}.caption{z-index:2;position:absolute;bottom:19px;left:6%;right:6%;text-align:center;color:#eef4f2;font-size:16px;line-height:1.8;background:#111920e8;border-radius:5px;padding:8px 14px}.stage-toolbar{display:flex;gap:10px;align-items:center;padding:10px 0;font-size:10px;color:#7f919e}.stage-toolbar button{font-size:10px;padding:6px 9px}.stage-toolbar span{margin-left:auto}.progress{height:3px;background:#2a343d;border-radius:4px;margin-top:2px}.progress div{height:100%;background:#8fbda9;transition:width .5s}.progress-label{display:flex;justify-content:space-between;margin:8px 0 24px;font-size:11px;color:#8496a4}.section-head{display:flex;justify-content:space-between;align-items:center;gap:10px}.section-head a,.section-head>span{font-size:11px}h2{font-size:13px;font-weight:500;margin:0 0 14px}.section-head h2{margin:0}.transcript>.section-head{margin-bottom:15px}.transcript{min-height:190px}.reply{padding:16px 0;border-top:1px solid #28313a}.reply-meta{display:flex;justify-content:space-between;gap:10px;font-size:10px;color:#8ba094}.reply p{line-height:1.8;font-size:13px;margin:9px 0}.sources{font-size:10px;color:#80939f;line-height:1.8}.audience{background:#171e26;border:1px solid #2c3540;border-radius:10px;display:flex;flex-direction:column;align-self:start;overflow:hidden}.audience>.section-head{padding:16px;border-bottom:1px solid #2c3540}.audience>.section-head>span{color:#859aa6}.feed{height:363px;overflow:auto;padding:0 16px;scrollbar-width:thin;scrollbar-color:#3b4854 transparent}.feed article{padding:12px 0;border-bottom:1px solid #242e38}.feed article>div{display:flex;justify-content:space-between;gap:12px}.feed b{color:#9ebfb2;font-weight:500;font-size:11px}.feed time{font-size:10px;color:#687c8c}.feed p{font-size:12px;line-height:1.7;margin:5px 0 0}.feed .gift p{color:#dfc49a}.composer{padding:13px;border-top:1px solid #2c3540;display:flex;flex-direction:column;gap:8px}.composer>input{font-size:11px;width:130px;padding:6px 9px}.composer textarea{resize:vertical;min-height:78px;font-size:12px;line-height:1.6}.composer>div{display:flex;justify-content:space-between;gap:8px}.composer button{font-size:11px;padding:8px 11px}.empty{color:#748b9b;font-size:12px;line-height:1.9;padding:20px 0}.diagnostics{display:grid;grid-template-columns:1.7fr 1fr;gap:32px;border-top:1px solid #2c3540;margin-top:26px;padding-top:22px}.diagnostics p{font-size:11px;color:#869aa7;line-height:1.8}.fault-buttons{display:flex;flex-wrap:wrap;gap:7px;margin:12px 0}.fault-buttons button{font-size:10px;padding:7px 9px}.fault-line{margin:4px 0}.metrics dl{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:20px 0}.metrics dt{font-size:10px;color:#869aa7}.metrics dd{font-size:19px;margin:9px 0 0;color:#dde8e2}.error{background:#382728;color:#efb4ab;padding:12px 15px;border-radius:7px;display:flex;justify-content:space-between;margin-bottom:15px;font-size:12px}.error button{background:none;border:0;padding:0;color:inherit}footer{border-top:1px solid #29313a;padding:19px 0;margin-top:24px;color:#687e8d;font-size:10px;display:flex;justify-content:space-between;gap:20px}footer a{display:block;margin:10px 0}footer summary{cursor:pointer}@media(max-width:900px){.lab{padding:0 18px 20px}.controls{flex-wrap:wrap}.controls label{flex-basis:40%}.workspace{grid-template-columns:1fr}.diagnostics{grid-template-columns:1fr}.broadcast-stage{height:320px}.intro{align-items:start}h1{font-size:22px}.safe{display:none}.feed{height:280px}.session-state{font-size:11px}.metrics dl{margin-bottom:0}}@media(prefers-reduced-motion:reduce){.wave i{animation:none!important}.progress div{transition:none}}
</style>
<style scoped>
.report { border-top: 1px solid #29313a; margin-top: 24px; padding-top: 20px; }
.report p { font-size: 12px; color: #9eb0ba; line-height: 1.9; }
footer details button { padding: 4px 8px; font-size: 10px; }
</style>
