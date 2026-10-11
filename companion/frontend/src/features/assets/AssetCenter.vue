<script setup lang="ts">
import { computed, ref } from 'vue';
import {
  NButton, NDrawer, NDrawerContent, NEmpty, NInput, NPopconfirm, NProgress,
  NRadioButton, NRadioGroup, NSelect, NSpin, NTabPane, NTabs, NTag, NUpload,
  useMessage, type UploadCustomRequestOptions,
} from 'naive-ui';
import { api, type AssetItem, type OnlineWork } from '../../api/client';
import { useAssetsStore } from '../../stores/assets';
import { useCharacterStore } from '../../stores/character';
import { useSettingsStore } from '../../stores/settings';
import { t } from '../../i18n';
import {
  MOTION_CATS, guessWorkCat, parseMotionCat, stripCatPrefix,
  type MotionCat,
} from './motionMeta';

defineProps<{ show: boolean }>();
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>();

const assets = useAssetsStore();
const characters = useCharacterStore();
const settings = useSettingsStore();
const message = useMessage();
const downloadUrl = ref('');
const search = ref('');
const motionFilter = ref<MotionCat | 'all'>('all');
const recategorizing = ref(false);

const searchChips = computed(() => {
  settings.locale.ui;
  return [
    { kw: '待机', cat: 'idle' as const, label: t('cat.idle') },
    { kw: '打招呼', cat: 'greet' as const, label: t('cat.greet') },
    { kw: '挥手', cat: 'greet' as const, label: t('intent.greet') },
    { kw: '鞠躬', cat: 'interact' as const, label: t('intent.bow') },
    { kw: '比心', cat: 'interact' as const, label: t('intent.heart') },
    { kw: '坐姿', cat: 'interact' as const, label: t('intent.sit') },
    { kw: '思考', cat: 'interact' as const, label: t('intent.think') },
    { kw: '害羞', cat: 'interact' as const, label: t('intent.shy') },
    { kw: '叉腰', cat: 'interact' as const, label: t('assets.chipAkimbo') },
    { kw: '点头', cat: 'interact' as const, label: t('intent.nod') },
    { kw: '动作包', cat: '' as const, label: t('assets.chipPack') },
    { kw: '镜头', cat: 'cinematic' as const, label: t('quick.move') },
    { kw: 'カメラ', cat: 'cinematic' as const, label: t('assets.chipCamJa') },
  ];
});

const catSelectOptions = computed(() => {
  settings.locale.ui;
  return MOTION_CATS.map((c) => ({ label: t(`cat.${c.key}`), value: c.key }));
});

function catName(cat: MotionCat) {
  settings.locale.ui;
  return t(`cat.${cat}`);
}

const filteredCameras = computed(() => filterAssets(assets.cameras));
const filteredMotions = computed(() => {
  let list = filterAssets(assets.motions);
  if (motionFilter.value !== 'all') {
    list = list.filter((a) => parseMotionCat(a) === motionFilter.value);
  }
  return list;
});

const motionCounts = computed(() => {
  const c: Record<string, number> = { all: assets.motions.length };
  for (const k of MOTION_CATS) c[k.key] = 0;
  for (const m of assets.motions) c[parseMotionCat(m)] += 1;
  return c;
});

function filterAssets(list: AssetItem[]) {
  const q = search.value.trim();
  if (!q) return list;
  return list.filter((a) => a.label.includes(q) || a.name.includes(q));
}

function fmtSize(bytes: number) {
  if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.round(bytes / 1024)} KB`;
}

async function startDownload() {
  const url = downloadUrl.value.trim();
  if (!url) return;
  try {
    await assets.startDownload(url, searchCat.value);
    downloadUrl.value = '';
    message.success(t('assets.taskOk'));
  } catch (e) {
    message.error(t('assets.createFail', { err: String(e) }));
  }
}

async function customUpload({ file, onFinish, onError }: UploadCustomRequestOptions) {
  try {
    const created = await assets.importFile(file.file as File);
    const cats = created.map((c: AssetItem) => stripCatPrefix(c.label)).join('、');
    message.success(t('assets.imported', { cats }));
    onFinish();
  } catch (e) {
    message.error(t('assets.importFail', { err: String(e) }));
    onError();
  }
}

async function useModel(asset: AssetItem) {
  const char = characters.current;
  if (!char) return;
  await characters.save({ ...char, model_asset_id: asset.id });
  message.success(t('assets.switched', { name: asset.label }));
}

async function removeAsset(asset: AssetItem) {
  await assets.remove(asset.id, true);
  message.success(t('assets.removed'));
}

async function changeCat(asset: AssetItem, cat: MotionCat) {
  await assets.setMotionCategory(asset.id, cat);
}

async function recategorize() {
  recategorizing.value = true;
  try {
    const n = await assets.recategorize();
    message.success(n ? t('assets.recatOk', { n }) : t('assets.recatSame'));
  } catch (e) {
    message.error(t('assets.recatFail', { err: String(e) }));
  } finally {
    recategorizing.value = false;
  }
}

function taskPercent(t: { downloaded: number; total: number }) {
  return t.total ? Math.round((t.downloaded / t.total) * 100) : 0;
}

function catType(cat: MotionCat): 'default' | 'info' | 'success' | 'warning' {
  if (cat === 'idle') return 'info';
  if (cat === 'greet') return 'success';
  if (cat === 'interact') return 'warning';
  return 'default';
}

// --- 模之屋在线搜索 ---
const onlineKeyword = ref('');
const onlineKind = ref<'motion' | 'model'>('motion');
const searchCat = ref<MotionCat | 'cinematic' | ''>('');
const onlineResults = ref<OnlineWork[]>([]);
const onlineLoading = ref(false);
const onlineSearched = ref(false);
const onlinePage = ref(1);
const onlineTotal = ref(0);
const downloading = ref(new Set<string>());

async function searchOnline(page = 1) {
  const kw = onlineKeyword.value.trim();
  if (!kw) return;
  onlineLoading.value = true;
  onlineSearched.value = true;
  onlinePage.value = page;
  try {
    const { items, total } = await api.searchOnline(kw, onlineKind.value, page);
    onlineResults.value = page === 1 ? items : [...onlineResults.value, ...items];
    onlineTotal.value = total || items.length;
  } catch (e) {
    message.error(t('assets.searchFail', { err: String(e) }));
  } finally {
    onlineLoading.value = false;
  }
}

function clickChip(chip: { kw: string; cat: MotionCat | 'cinematic' | '' }) {
  onlineKind.value = 'motion';
  onlineKeyword.value = chip.kw;
  searchCat.value = chip.cat;
  void searchOnline(1);
}

async function downloadWork(work: OnlineWork) {
  downloading.value.add(work.work_uuid);
  downloading.value = new Set(downloading.value);
  try {
    const cat = searchCat.value || guessWorkCat(work.work_name);
    await assets.startDownload(work.url, cat);
    const tag = cat === 'cinematic' ? t('quick.move') : catName(cat as MotionCat);
    message.success(t('assets.started', { name: work.work_name, tag }));
  } catch (e) {
    message.error(t('assets.fail', { err: String(e) }));
  } finally {
    downloading.value.delete(work.work_uuid);
    downloading.value = new Set(downloading.value);
  }
}
</script>

<template>
  <n-drawer :show="show" @update:show="(v: boolean) => emit('update:show', v)"
            :width="520" placement="right" show-mask="transparent" to="body">
    <n-drawer-content :title="t('top.assets')" closable :native-scrollbar="false">
    <div class="toolbar">
      <n-input v-model:value="downloadUrl" :placeholder="t('assets.urlPh')" clearable
               @keydown.enter="startDownload" />
      <n-button type="primary" @click="startDownload">{{ t('assets.download') }}</n-button>
      <n-upload :custom-request="customUpload" :show-file-list="false"
                accept=".zip,.rar,.7z,.vmd,.vpd,.vrm,.glb" multiple>
        <n-button secondary>{{ t('assets.import') }}</n-button>
      </n-upload>
    </div>

    <div v-if="assets.tasks.length" class="tasks">
      <div v-for="t in assets.tasks" :key="t.id" class="task">
        <span class="task-name">{{ t.filename || t.url }}</span>
        <n-progress v-if="t.status === 'downloading'" type="line"
                    :percentage="taskPercent(t)" :height="6" style="flex:1" />
        <n-tag v-else size="small"
               :type="t.status === 'done' ? 'success' : t.status === 'error' ? 'error' : 'info'">
          {{ t.message }}
        </n-tag>
      </div>
    </div>

    <n-tabs type="line" default-value="online">
      <n-tab-pane name="online" :tab="t('assets.online')">
        <p class="hint">{{ t('assets.onlineHint') }}</p>
        <div class="chips">
          <n-button v-for="c in searchChips" :key="c.kw" size="tiny"
                    :type="onlineKeyword === c.kw ? 'primary' : 'default'"
                    :secondary="onlineKeyword !== c.kw"
                    @click="clickChip(c)">{{ c.label }}</n-button>
        </div>
        <div class="online-bar">
          <n-radio-group v-model:value="onlineKind" size="small">
            <n-radio-button value="motion">{{ t('assets.motion') }}</n-radio-button>
            <n-radio-button value="model">{{ t('assets.model') }}</n-radio-button>
          </n-radio-group>
          <n-input v-model:value="onlineKeyword" size="small" clearable
                   :placeholder="t('assets.searchPh')"
                   @keydown.enter="searchOnline(1)" />
          <n-button size="small" type="primary" :loading="onlineLoading"
                    @click="searchOnline(1)">{{ t('assets.search') }}</n-button>
        </div>
        <n-spin :show="onlineLoading">
          <n-empty v-if="onlineSearched && !onlineResults.length && !onlineLoading"
                   :description="t('assets.emptyOnline')" style="padding: 30px 0" />
          <div class="cards online-cards">
            <div v-for="w in onlineResults" :key="w.work_uuid" class="card">
              <img v-if="w.cover" :src="w.cover" class="cover" loading="lazy" />
              <div class="card-title" :title="w.work_name">{{ w.work_name }}</div>
              <div class="card-meta">
                <n-tag v-if="onlineKind === 'motion'" size="tiny" :bordered="false"
                       :type="catType(guessWorkCat(w.work_name))">
                  {{ catName(guessWorkCat(w.work_name)) }}
                </n-tag>
                <span>{{ w.author }}</span>
                <span>{{ t('assets.downloads', { n: w.downloads }) }}</span>
              </div>
              <div class="card-actions">
                <n-button size="tiny" type="primary" secondary
                          :loading="downloading.has(w.work_uuid)"
                          @click="downloadWork(w)">{{ t('assets.downloadImport') }}</n-button>
                <n-button size="tiny" quaternary tag="a" :href="w.url" target="_blank">
                  {{ t('assets.site') }}
                </n-button>
              </div>
            </div>
          </div>
          <div v-if="onlineResults.length && onlineResults.length < onlineTotal" class="more">
            <n-button size="small" quaternary :loading="onlineLoading"
                      @click="searchOnline(onlinePage + 1)">
              {{ t('assets.more', { have: onlineResults.length, total: onlineTotal }) }}
            </n-button>
          </div>
        </n-spin>
      </n-tab-pane>

      <n-tab-pane name="motions" :tab="t('assets.myMotions', { n: assets.motions.length })">
        <div class="lib-bar">
          <n-input v-model:value="search" :placeholder="t('assets.searchLib')" clearable size="small" />
          <n-button size="small" :loading="recategorizing" @click="recategorize">
            {{ t('assets.recat') }}
          </n-button>
        </div>
        <div class="chips">
          <n-button size="tiny" :type="motionFilter === 'all' ? 'primary' : 'default'"
                    :secondary="motionFilter !== 'all'" @click="motionFilter = 'all'">
            {{ t('assets.all', { n: motionCounts.all }) }}
          </n-button>
          <n-button v-for="c in MOTION_CATS" :key="c.key" size="tiny"
                    :type="motionFilter === c.key ? 'primary' : 'default'"
                    :secondary="motionFilter !== c.key"
                    @click="motionFilter = c.key">
            {{ catName(c.key) }} {{ motionCounts[c.key] }}
          </n-button>
        </div>
        <n-empty v-if="!filteredMotions.length" :description="t('assets.emptyMotion')" />
        <div class="cards">
          <div v-for="a in filteredMotions" :key="a.id" class="card">
            <div class="card-title" :title="a.label">{{ stripCatPrefix(a.label) }}</div>
            <div class="card-meta">
              <n-tag size="tiny" :bordered="false" :type="catType(parseMotionCat(a))">
                {{ catName(parseMotionCat(a)) }}
              </n-tag>
              <span>{{ fmtSize(a.size) }}</span>
            </div>
            <div class="card-actions">
              <n-select size="tiny" :value="parseMotionCat(a)" :options="catSelectOptions"
                        style="width: 92px"
                        @update:value="(v: MotionCat) => changeCat(a, v)" />
              <n-popconfirm @positive-click="removeAsset(a)">
                <template #trigger>
                  <n-button size="tiny" quaternary type="error">{{ t('assets.delete') }}</n-button>
                </template>
                {{ t('assets.deleteMotion') }}
              </n-popconfirm>
            </div>
          </div>
        </div>
      </n-tab-pane>

      <n-tab-pane name="cameras" :tab="t('assets.myCams', { n: assets.cameras.length })">
        <n-input v-model:value="search" :placeholder="t('assets.searchCam')" clearable size="small"
                 style="margin-bottom: 8px" />
        <n-empty v-if="!filteredCameras.length" :description="t('assets.emptyCam')" />
        <div class="cards">
          <div v-for="a in filteredCameras" :key="a.id" class="card">
            <div class="card-title" :title="a.label">{{ stripCatPrefix(a.label) }}</div>
            <div class="card-meta">
              <n-tag size="tiny" :bordered="false" type="info">{{ t('assets.camTag') }}</n-tag>
              <span>{{ fmtSize(a.size) }}</span>
            </div>
            <div class="card-actions">
              <n-popconfirm @positive-click="removeAsset(a)">
                <template #trigger>
                  <n-button size="tiny" quaternary type="error">{{ t('assets.delete') }}</n-button>
                </template>
                {{ t('assets.deleteCam') }}
              </n-popconfirm>
            </div>
          </div>
        </div>
      </n-tab-pane>

      <n-tab-pane name="models" :tab="t('assets.myModels', { n: assets.models.length })">
        <n-input v-model:value="search" :placeholder="t('assets.searchModel')" clearable size="small"
                 style="margin-bottom: 8px" />
        <n-empty v-if="!filteredModels.length" :description="t('assets.emptyModel')" />
        <div class="cards">
          <div v-for="a in filteredModels" :key="a.id" class="card">
            <div class="card-title">{{ a.label }}</div>
            <div class="card-meta">
              <n-tag size="tiny" :bordered="false">{{ a.fmt }}</n-tag>
              <span>{{ fmtSize(a.size) }}</span>
            </div>
            <div class="card-actions">
              <n-button size="tiny" type="primary" secondary @click="useModel(a)">
                {{ t('assets.useModel') }}
              </n-button>
              <n-popconfirm @positive-click="removeAsset(a)">
                <template #trigger>
                  <n-button size="tiny" quaternary type="error">{{ t('assets.delete') }}</n-button>
                </template>
                {{ t('assets.deleteModel') }}
              </n-popconfirm>
            </div>
          </div>
        </div>
      </n-tab-pane>
    </n-tabs>
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
}

.hint {
  margin: 8px 0 4px;
  font-size: 12px;
  line-height: 1.55;
  opacity: 0.65;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 0;
}

.tasks {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.task {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
}

.task-name {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0.8;
}

.lib-bar {
  display: flex;
  gap: 8px;
  padding-top: 8px;
}

.lib-bar :deep(.n-input) {
  flex: 1;
}

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
  padding-top: 10px;
}

.card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: rgba(255, 255, 255, 0.03);
}

.card-title {
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  opacity: 0.7;
  flex-wrap: wrap;
}

.card-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.online-bar {
  display: flex;
  gap: 8px;
  align-items: center;
}

.online-bar :deep(.n-input) {
  flex: 1;
}

.cover {
  width: 100%;
  height: 96px;
  object-fit: cover;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
}

.more {
  display: flex;
  justify-content: center;
  padding: 10px 0 4px;
}
</style>
