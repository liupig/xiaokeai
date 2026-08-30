<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue';
import { NButton, useMessage } from 'naive-ui';
import { stage } from '../../engine/stage';
import { stripCatPrefix } from '../assets/motionMeta';
import { caster } from '../performance/caster';
import { shots } from '../performance/shotConductor';
import { useAssetsStore } from '../../stores/assets';
import { distanceOfShot } from '../performance/grammar';
import {
  MOVES, SIZES, STANDS,
  type ActFilter, type ActionPick, type CamPick, type ComboSel, type Verdict,
  actionKey, actionMatchesFilter, allActions, allCamPicks, camKey,
  comboAt, comboCount, comboId, comboLabel, expandCompatOk, filterOfAction, formatReport,
  hydrateVerdicts, indexOfCombo, intentFilters, labelFromId,
  loadLocalVerdicts, persistVerdicts, saveLocalVerdicts,
} from './camReview';

const props = defineProps<{ show: boolean }>();
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>();

const assets = useAssetsStore();
const message = useMessage();
const verdicts = ref<Record<string, Verdict>>(loadLocalVerdicts());
const persistHint = ref('审查标记会写入后端磁盘');
const persistOk = ref(false);
let saveTimer = 0;
const size = ref(SIZES[0].id);
const camKeySel = ref('hold');
const stand = ref(STANDS[0].id);
const actKey = ref('none');
const actFilter = ref<ActFilter>('none');
let playSeq = 0;

const cams = computed(() => allCamPicks(
  assets.cameras.map((c) => ({ name: c.name, label: stripCatPrefix(c.label) || c.name })),
));
const actions = computed(() => allActions(assets.motions));
const filters = computed(() => intentFilters(actions.value));
const visibleActs = computed(() =>
  actions.value.filter((a) => actionMatchesFilter(a, actFilter.value)),
);

const camPick = computed(() => cams.value.find((c) => camKey(c) === camKeySel.value) ?? cams.value[0]);
const vmdCams = computed(() =>
  cams.value.filter((c): c is Extract<CamPick, { kind: 'vmd' }> => c.kind === 'vmd'),
);
const holdCam: CamPick = { kind: 'hold', label: '定镜' };
const noneAct: ActionPick = { kind: 'none', label: '无动作' };
const actionPick = computed(() =>
  actions.value.find((a) => actionKey(a) === actKey.value) ?? noneAct,
);

const sel = computed<ComboSel>(() => ({
  size: size.value,
  cam: camPick.value,
  stand: stand.value,
  action: actionPick.value,
}));

const id = computed(() => comboId(sel.value));
const idx = computed(() => indexOfCombo(sel.value, cams.value, actions.value));
const total = computed(() => comboCount(cams.value.length, actions.value.length));
const currentVerdict = computed(() => verdicts.value[id.value] || 'unset');

const stats = computed(() => {
  let ok = 0, bad = 0;
  for (const v of Object.values(verdicts.value)) {
    if (v === 'ok') ok += 1;
    else if (v === 'bad') bad += 1;
  }
  return { ok, bad, marked: ok + bad };
});

watch(() => props.show, (v) => {
  shots.reviewLock = v;
  if (v) {
    shots.indexFrom(assets.cameras);
    void hydrate();
  }
}, { immediate: true });

async function hydrate() {
  try {
    const r = await hydrateVerdicts();
    verdicts.value = r.map;
    persistOk.value = true;
    const bits = [];
    if (r.migrated) bits.push('已把浏览器旧标记迁到数据库');
    if (r.inherited) bits.push(`按兼容规则补标 ${r.inherited} 条`);
    persistHint.value = bits.length
      ? `${bits.join('；')}（表 cam_review）`
      : '已长久保存在数据库表 cam_review，JSON 只做备份';
    jumpToFirstUnset();
  } catch {
    persistOk.value = false;
    persistHint.value = '后端暂未连上，先写在本机浏览器；连上后会自动迁过去';
  }
}

onUnmounted(() => {
  shots.reviewLock = false;
  playSeq += 1;
  window.clearTimeout(saveTimer);
});

function applySel(next: ComboSel, play = true) {
  size.value = next.size;
  camKeySel.value = camKey(next.cam);
  stand.value = next.stand;
  actKey.value = actionKey(next.action);
  actFilter.value = filterOfAction(next.action);
  if (play) void playCurrent(next);
}

function setFilter(f: ActFilter) {
  actFilter.value = f;
  if (f === 'none') applySel({ ...sel.value, action: noneAct });
}

async function playCurrent(target: ComboSel = sel.value) {
  const seq = ++playSeq;
  stage.stopCamera();
  stage.stopMotion();
  const needWalk = stage.standSlot !== target.stand;
  if (needWalk) stage.goToStand(target.stand);
  if (needWalk) await wait(1100, seq);
  if (seq !== playSeq) return;

  const dist = distanceOfShot(target.size);
  if (target.cam.kind === 'vmd') {
    shots.forceVmd(target.cam.name, dist);
  } else {
    shots.forceShot(target.size, dist);
    if (target.cam.kind === 'move') {
      await wait(420, seq);
      if (seq !== playSeq) return;
      shots.forceShot(target.cam.id, dist);
    }
  }
  const act = target.action;
  if (act.kind === 'none') return;
  await wait(target.cam.kind === 'hold' ? 280 : 700, seq);
  if (seq !== playSeq) return;
  if (act.kind === 'builtin') {
    stage.triggerAction(act.id);
    return;
  }
  const ok = caster.playAssetForReview(act.name);
  if (!ok) message.warning(`动作库没有「${act.label}」`);
}

function wait(ms: number, seq: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(() => resolve(), ms);
  });
}

function mark(v: Verdict) {
  let next: Record<string, Verdict> = { ...verdicts.value, [id.value]: v };
  if (v === 'ok' || v === 'bad') next = expandCompatOk(next);
  verdicts.value = next;
  saveLocalVerdicts(next);
  persistHint.value = v === 'ok'
    ? '可用：更远景别、更右站位已一并标可用'
    : v === 'bad'
      ? '不可用：还没标的更远景别、更右站位已一并标不可用'
      : '正在写入数据库…';
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(() => {
    void persistVerdicts(next).then(() => {
      persistOk.value = true;
      persistHint.value = '已写入数据库表 cam_review（可用/不可用均已继承）';
    }).catch(() => {
      persistOk.value = false;
      persistHint.value = '数据库写入失败，本机浏览器里还有一份备份';
    });
  }, 280);
}

function jumpToFirstUnset() {
  const n = total.value;
  for (let i = 0; i < n; i++) {
    const next = comboAt(i, cams.value, actions.value);
    const key = comboId(next);
    if (!verdicts.value[key] || verdicts.value[key] === 'unset') {
      applySel(next);
      return;
    }
  }
}

function markAndNext(v: Verdict) {
  mark(v);
  step(1, true);
}

function step(dir: 1 | -1, onlyUnset = false) {
  let i = idx.value;
  const n = total.value;
  for (let k = 0; k < n; k++) {
    i = (i + dir + n) % n;
    const next = comboAt(i, cams.value, actions.value);
    const key = comboId(next);
    if (!onlyUnset || !verdicts.value[key] || verdicts.value[key] === 'unset') {
      applySel(next);
      return;
    }
  }
  message.info('没有未审的组合了');
}

async function copyReport() {
  const text = formatReport(
    verdicts.value,
    cams.value,
    actions.value,
    (cid) => labelFromId(cid, cams.value, actions.value),
  );
  try {
    await navigator.clipboard.writeText(text);
    message.success('审查报告已复制，贴回对话即可');
  } catch {
    message.error('复制失败');
  }
}

function resetVerdicts() {
  verdicts.value = {};
  saveLocalVerdicts({});
  persistHint.value = '正在清空数据库标记…';
  void persistVerdicts({}).then(() => {
    persistOk.value = true;
    persistHint.value = '数据库标记已清空';
    message.info('已清空标记');
  }).catch(() => {
    persistOk.value = false;
    message.error('清空数据库失败');
  });
}
</script>

<template>
  <transition name="slide">
    <div v-if="show" class="panel glass">
      <div class="head">
        <span class="title">镜头审查</span>
        <n-button size="tiny" quaternary @click="emit('update:show', false)">收起 ›</n-button>
      </div>
      <p class="lead">
        每个组合按 <b>运镜 × 站位 × 动作</b> 走，从左站位、特写开始。
        三种状态：没标 / 可用 / 不可用（没标不是不可用）。
        景别近→远、站位左→右：可用和不可用都会继承到还没标的格子。
      </p>
      <div class="now" :class="currentVerdict">
        {{ comboLabel(sel) }}
      </div>
      <div class="stats">
        第 {{ idx + 1 }} / {{ total }} 条 · 动作 {{ actions.length }} · 已标 {{ stats.marked }}（可用 {{ stats.ok }} / 不可用 {{ stats.bad }}）
      </div>
      <div class="persist" :class="{ ok: persistOk }">{{ persistHint }}</div>

      <div class="row">
        <span class="lab">景别</span>
        <n-button v-for="s in SIZES" :key="s.id" size="tiny"
                  :type="size === s.id ? 'primary' : 'default'"
                  :quaternary="size !== s.id"
                  @click="applySel({ ...sel, size: s.id })">{{ s.label }}</n-button>
      </div>
      <div class="row">
        <span class="lab">运镜</span>
        <n-button size="tiny"
                  :type="camKeySel === 'hold' ? 'primary' : 'default'"
                  :quaternary="camKeySel !== 'hold'"
                  @click="applySel({ ...sel, cam: holdCam })">定镜</n-button>
        <n-button v-for="m in MOVES" :key="m.id" size="tiny"
                  :type="camKeySel === `move:${m.id}` ? 'primary' : 'default'"
                  :quaternary="camKeySel !== `move:${m.id}`"
                  @click="applySel({ ...sel, cam: { kind: 'move', id: m.id, label: m.label } })">{{ m.label }}</n-button>
      </div>
      <div class="row vmd">
        <span class="lab">镜头库</span>
        <n-button v-for="c in vmdCams" :key="c.name" size="tiny"
                  :type="camKeySel === `vmd:${c.name}` ? 'primary' : 'default'"
                  :quaternary="camKeySel !== `vmd:${c.name}`"
                  @click="applySel({ ...sel, cam: c })">{{ c.label }}</n-button>
      </div>
      <div class="row">
        <span class="lab">站位</span>
        <n-button v-for="s in STANDS" :key="s.id" size="tiny"
                  :type="stand === s.id ? 'primary' : 'default'"
                  :quaternary="stand !== s.id"
                  @click="applySel({ ...sel, stand: s.id })">{{ s.label }}</n-button>
      </div>
      <div class="row">
        <span class="lab">分类</span>
        <n-button v-for="f in filters" :key="f.id" size="tiny"
                  :type="actFilter === f.id ? 'primary' : 'default'"
                  :quaternary="actFilter !== f.id"
                  @click="setFilter(f.id)">{{ f.label }} {{ f.id === 'none' ? '' : f.n }}</n-button>
      </div>
      <div class="row acts">
        <span class="lab">具体</span>
        <div v-if="actFilter === 'none'" class="hint">当前不播动作，只看景别 / 运镜 / 站位。</div>
        <template v-else>
          <n-button v-for="a in visibleActs" :key="actionKey(a)" size="tiny"
                    :type="actKey === actionKey(a) ? 'primary' : 'default'"
                    :quaternary="actKey !== actionKey(a)"
                    @click="applySel({ ...sel, action: a })">{{ a.label }}</n-button>
        </template>
      </div>

      <div class="tools">
        <n-button size="small" type="primary" @click="playCurrent()">再播一次</n-button>
        <n-button size="small" secondary @click="step(-1)">上一条</n-button>
        <n-button size="small" secondary @click="step(1)">下一条</n-button>
        <n-button size="small" type="info" secondary @click="step(1, true)">下一条未审</n-button>
      </div>
      <div class="tools">
        <n-button size="small" type="success" @click="markAndNext('ok')">可用跳下一条</n-button>
        <n-button size="small" type="error" @click="markAndNext('bad')">不可用跳下一条</n-button>
        <n-button size="small" class="ok" :type="currentVerdict === 'ok' ? 'success' : 'default'"
                  @click="mark('ok')">可用</n-button>
        <n-button size="small" :type="currentVerdict === 'bad' ? 'error' : 'default'"
                  @click="mark('bad')">不可用</n-button>
        <n-button size="small" type="primary" secondary @click="copyReport">复制报告</n-button>
        <n-button size="small" quaternary @click="resetVerdicts">清空标记</n-button>
        <n-button size="small" type="warning" secondary @click="stage.stopCamera(); stage.stopMotion()">停止</n-button>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.panel {
  position: absolute;
  top: 70px;
  right: 16px;
  bottom: 20px;
  width: 460px;
  z-index: 9;
  padding: 14px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-radius: 16px;
  background: rgba(15, 15, 26, 0.82);
  backdrop-filter: blur(18px);
  box-shadow: 0 14px 44px rgba(0, 0, 0, 0.4);
}
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.title { font-size: 14px; font-weight: 600; }
.lead { font-size: 12px; line-height: 1.5; opacity: 0.7; margin: 0 0 8px; }
.now {
  font-size: 13px;
  font-weight: 600;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.12);
  margin-bottom: 6px;
  line-height: 1.4;
}
.now.ok { border-color: #50c878; }
.now.bad { border-color: #ff6e6e; }
.stats { font-size: 12px; opacity: 0.75; margin-bottom: 4px; }
.persist { font-size: 11px; opacity: 0.55; margin-bottom: 10px; line-height: 1.4; }
.persist.ok { opacity: 0.8; color: #8fd9a8; }
.row {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.lab {
  font-size: 12px;
  opacity: 0.55;
  width: 40px;
  flex-shrink: 0;
  padding-top: 4px;
}
.row.vmd {
  max-height: 72px;
  overflow-y: auto;
  padding-right: 4px;
}
.row.acts {
  flex: 1;
  min-height: 120px;
  overflow-y: auto;
  padding-right: 4px;
  align-content: flex-start;
}
.hint { font-size: 12px; opacity: 0.55; padding-top: 4px; }
.tools { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.slide-enter-active, .slide-leave-active { transition: transform 0.25s ease, opacity 0.25s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(30px); opacity: 0; }
</style>
