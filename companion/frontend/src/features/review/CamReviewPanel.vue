<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue';
import { NButton, useMessage } from 'naive-ui';
import { stage } from '../../engine/stage';
import { stripCatPrefix } from '../assets/motionMeta';
import { caster } from '../performance/caster';
import { shots } from '../performance/shotConductor';
import { useAssetsStore } from '../../stores/assets';
import { useSettingsStore } from '../../stores/settings';
import { t } from '../../i18n';
import { distanceOfShot } from '../performance/grammar';
import {
  MOVES, SIZES, STANDS,
  type ActFilter, type ActionPick, type CamPick, type ComboSel, type Verdict,
  actionKey, actionMatchesFilter, allActions, allCamPicks, camKey,
  comboAt, comboCount, comboId, expandCompatOk, filterOfAction, formatReport,
  hydrateVerdicts, indexOfCombo, intentFilters, labelFromId,
  loadLocalVerdicts, persistVerdicts, saveLocalVerdicts,
} from './camReview';

const props = defineProps<{ show: boolean }>();
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>();

const assets = useAssetsStore();
const settings = useSettingsStore();
const message = useMessage();
const verdicts = ref<Record<string, Verdict>>(loadLocalVerdicts());
const persistHint = ref('');
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

function camText(cam: CamPick) {
  settings.locale.ui;
  if (cam.kind === 'hold') return t('beat.hold');
  if (cam.kind === 'move') return t(`cam.${cam.id}`);
  const id = cam.name.replace(/\.vmd$/i, '');
  const key = `camlib.${id}`;
  const hit = t(key);
  return hit === key ? cam.label : hit;
}

function showCombo(s: ComboSel) {
  settings.locale.ui;
  const act = s.action.kind === 'none'
    ? t('beat.none')
    : s.action.kind === 'builtin'
      ? t(s.action.id === 'nod' ? 'review.nodProg' : 'review.shakeProg')
      : `${s.action.tags[0] ? t(`intent.${s.action.tags[0]}`) : t('review.other')} · ${s.action.label}`;
  return `${t(`cam.${s.size}`)} × ${camText(s.cam)} × ${t(`stand.${s.stand}`)} × ${act}`;
}

function filterText(id: ActFilter) {
  settings.locale.ui;
  if (id === 'all') return t('review.all');
  if (id === 'none') return t('beat.none');
  return t(`intent.${id}`);
}

function actButton(a: ActionPick) {
  settings.locale.ui;
  if (a.kind === 'builtin') return t(a.id === 'nod' ? 'review.nodProg' : 'review.shakeProg');
  return a.label;
}
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
    if (r.migrated) bits.push(t('review.migrated'));
    if (r.inherited) bits.push(t('review.inherited', { n: r.inherited }));
    persistHint.value = bits.length
      ? `${bits.join('；')}（cam_review）`
      : t('review.saved');
    jumpToFirstUnset();
  } catch {
    persistOk.value = false;
    persistHint.value = t('review.offline');
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
  if (!ok) message.warning(t('review.missingMotion', { name: act.label }));
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
    ? t('review.okInherit')
    : v === 'bad'
      ? t('review.badInherit')
      : t('review.writing');
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(() => {
    void persistVerdicts(next).then(() => {
      persistOk.value = true;
      persistHint.value = t('review.wrote');
    }).catch(() => {
      persistOk.value = false;
      persistHint.value = t('review.writeFail');
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
  message.info(t('review.noUnset'));
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
    message.success(t('review.copied'));
  } catch {
    message.error(t('review.copyFail'));
  }
}

function resetVerdicts() {
  verdicts.value = {};
  saveLocalVerdicts({});
  persistHint.value = t('review.clearing');
  void persistVerdicts({}).then(() => {
    persistOk.value = true;
    persistHint.value = t('review.clearedDb');
    message.info(t('review.cleared'));
  }).catch(() => {
    persistOk.value = false;
    message.error(t('review.clearFail'));
  });
}
</script>

<template>
  <transition name="slide">
    <div v-if="show" class="panel glass">
      <div class="head">
        <span class="title">{{ t('review.title') }}</span>
        <n-button size="tiny" quaternary @click="emit('update:show', false)">{{ t('common.close') }} ›</n-button>
      </div>
      <p class="lead">{{ t('review.lead') }}</p>
      <div class="now" :class="currentVerdict">
        {{ showCombo(sel) }}
      </div>
      <div class="stats">
        {{ t('review.pos', { n: idx + 1, total, acts: actions.length, marked: stats.marked, ok: stats.ok, bad: stats.bad }) }}
      </div>
      <div class="persist" :class="{ ok: persistOk }">{{ persistHint }}</div>

      <div class="row">
        <span class="lab">{{ t('beat.size') }}</span>
        <n-button v-for="s in SIZES" :key="s.id" size="tiny"
                  :type="size === s.id ? 'primary' : 'default'"
                  :quaternary="size !== s.id"
                  @click="applySel({ ...sel, size: s.id })">{{ t('cam.' + s.id) }}</n-button>
      </div>
      <div class="row">
        <span class="lab">{{ t('beat.cam') }}</span>
        <n-button size="tiny"
                  :type="camKeySel === 'hold' ? 'primary' : 'default'"
                  :quaternary="camKeySel !== 'hold'"
                  @click="applySel({ ...sel, cam: holdCam })">{{ t('beat.hold') }}</n-button>
        <n-button v-for="m in MOVES" :key="m.id" size="tiny"
                  :type="camKeySel === `move:${m.id}` ? 'primary' : 'default'"
                  :quaternary="camKeySel !== `move:${m.id}`"
                  @click="applySel({ ...sel, cam: { kind: 'move', id: m.id, label: m.label } })">{{ t('cam.' + m.id) }}</n-button>
      </div>
      <div class="row vmd">
        <span class="lab">{{ t('review.library') }}</span>
        <n-button v-for="c in vmdCams" :key="c.name" size="tiny"
                  :type="camKeySel === `vmd:${c.name}` ? 'primary' : 'default'"
                  :quaternary="camKeySel !== `vmd:${c.name}`"
                  @click="applySel({ ...sel, cam: c })">{{ camText(c) }}</n-button>
      </div>
      <div class="row">
        <span class="lab">{{ t('beat.stand') }}</span>
        <n-button v-for="s in STANDS" :key="s.id" size="tiny"
                  :type="stand === s.id ? 'primary' : 'default'"
                  :quaternary="stand !== s.id"
                  @click="applySel({ ...sel, stand: s.id })">{{ t('stand.' + s.id) }}</n-button>
      </div>
      <div class="row">
        <span class="lab">{{ t('review.filter') }}</span>
        <n-button v-for="f in filters" :key="f.id" size="tiny"
                  :type="actFilter === f.id ? 'primary' : 'default'"
                  :quaternary="actFilter !== f.id"
                  @click="setFilter(f.id)">{{ filterText(f.id) }} {{ f.id === 'none' ? '' : f.n }}</n-button>
      </div>
      <div class="row acts">
        <span class="lab">{{ t('review.concrete') }}</span>
        <div v-if="actFilter === 'none'" class="hint">{{ t('review.noneHint') }}</div>
        <template v-else>
          <n-button v-for="a in visibleActs" :key="actionKey(a)" size="tiny"
                    :type="actKey === actionKey(a) ? 'primary' : 'default'"
                    :quaternary="actKey !== actionKey(a)"
                    @click="applySel({ ...sel, action: a })">{{ actButton(a) }}</n-button>
        </template>
      </div>

      <div class="tools">
        <n-button size="small" type="primary" @click="playCurrent()">{{ t('review.replay') }}</n-button>
        <n-button size="small" secondary @click="step(-1)">{{ t('review.prev') }}</n-button>
        <n-button size="small" secondary @click="step(1)">{{ t('review.next') }}</n-button>
        <n-button size="small" type="info" secondary @click="step(1, true)">{{ t('review.nextUnset') }}</n-button>
      </div>
      <div class="tools">
        <n-button size="small" type="success" @click="markAndNext('ok')">{{ t('review.okNext') }}</n-button>
        <n-button size="small" type="error" @click="markAndNext('bad')">{{ t('review.badNext') }}</n-button>
        <n-button size="small" class="ok" :type="currentVerdict === 'ok' ? 'success' : 'default'"
                  @click="mark('ok')">{{ t('review.ok') }}</n-button>
        <n-button size="small" :type="currentVerdict === 'bad' ? 'error' : 'default'"
                  @click="mark('bad')">{{ t('review.bad') }}</n-button>
        <n-button size="small" type="primary" secondary @click="copyReport">{{ t('review.copy') }}</n-button>
        <n-button size="small" quaternary @click="resetVerdicts">{{ t('review.clear') }}</n-button>
        <n-button size="small" type="warning" secondary @click="stage.stopCamera(); stage.stopMotion()">{{ t('review.stop') }}</n-button>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.panel {
  position: absolute;
  top: calc(70px + var(--desk-chrome, 0px));
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
  width: 72px;
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
