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
import {
  MOTION_CATS, catLabel, guessWorkCat, parseMotionCat, stripCatPrefix,
  type MotionCat,
} from './motionMeta';

defineProps<{ show: boolean }>();
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>();

const assets = useAssetsStore();
const characters = useCharacterStore();
const message = useMessage();
const downloadUrl = ref('');
const search = ref('');
const motionFilter = ref<MotionCat | 'all'>('all');
const recategorizing = ref(false);

const SEARCH_CHIPS: { kw: string; cat: MotionCat | 'cinematic' | ''; label: string }[] = [
  { kw: '待机', cat: 'idle', label: '待机' },
  { kw: '打招呼', cat: 'greet', label: '打招呼' },
  { kw: '挥手', cat: 'greet', label: '挥手' },
  { kw: '鞠躬', cat: 'interact', label: '鞠躬' },
  { kw: '比心', cat: 'interact', label: '比心' },
  { kw: '坐姿', cat: 'interact', label: '坐姿' },
  { kw: '思考', cat: 'interact', label: '思考' },
  { kw: '害羞', cat: 'interact', label: '害羞' },
  { kw: '叉腰', cat: 'interact', label: '叉腰' },
  { kw: '点头', cat: 'interact', label: '点头' },
  { kw: '动作包', cat: '', label: '动作包' },
  { kw: '镜头', cat: 'cinematic', label: '运镜' },
  { kw: 'カメラ', cat: 'cinematic', label: 'カメラ' },
];

const catSelectOptions = MOTION_CATS.map((c) => ({ label: c.label, value: c.key }));

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
    message.success('下载任务已创建，导入后会自动归类');
  } catch (e) {
    message.error(`创建失败：${e}`);
  }
}

async function customUpload({ file, onFinish, onError }: UploadCustomRequestOptions) {
  try {
    const created = await assets.importFile(file.file as File);
    const cats = created.map((c: AssetItem) => stripCatPrefix(c.label)).join('、');
    message.success(`导入成功：${cats}`);
    onFinish();
  } catch (e) {
    message.error(`导入失败：${e}`);
    onError();
  }
}

async function useModel(asset: AssetItem) {
  const char = characters.current;
  if (!char) return;
  await characters.save({ ...char, model_asset_id: asset.id });
  message.success(`已切换到模型「${asset.label}」`);
}

async function removeAsset(asset: AssetItem) {
  await assets.remove(asset.id, true);
  message.success('已删除');
}

async function changeCat(asset: AssetItem, cat: MotionCat) {
  await assets.setMotionCategory(asset.id, cat);
}

async function recategorize() {
  recategorizing.value = true;
  try {
    const n = await assets.recategorize();
    message.success(n ? `已重新归类 ${n} 个动作` : '类别没有变化');
  } catch (e) {
    message.error(`归类失败：${e}`);
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
    message.error(`搜索失败：${e}`);
  } finally {
    onlineLoading.value = false;
  }
}

function clickChip(chip: (typeof SEARCH_CHIPS)[number]) {
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
    const tag = cat === 'cinematic' ? '运镜' : catLabel(cat as MotionCat);
    message.success(`已开始下载「${work.work_name}」，导入后归到「${tag}」`);
  } catch (e) {
    message.error(`创建下载失败：${e}`);
  } finally {
    downloading.value.delete(work.work_uuid);
    downloading.value = new Set(downloading.value);
  }
}
</script>

<template>
  <n-drawer :show="show" @update:show="(v: boolean) => emit('update:show', v)"
            :width="520" placement="right" show-mask="transparent" to="body">
    <n-drawer-content title="资产中心" closable :native-scrollbar="false">
    <div class="toolbar">
      <n-input v-model:value="downloadUrl" placeholder="粘贴模之屋链接，如 https://www.aplaybox.com/details/motion/xxxx" clearable
               @keydown.enter="startDownload" />
      <n-button type="primary" @click="startDownload">下载</n-button>
      <n-upload :custom-request="customUpload" :show-file-list="false"
                accept=".zip,.rar,.7z,.vmd,.vpd,.vrm,.glb" multiple>
        <n-button secondary>导入本地</n-button>
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
      <n-tab-pane name="online" tab="在线下载">
        <p class="hint">
          点下面分类搜索，一次下一个即可。下完会按待机 / 打招呼 / 互动 / 舞蹈 / 运镜自动归类。
          下太快会触发模之屋验证码，隔几秒再下下一个。
        </p>
        <div class="chips">
          <n-button v-for="c in SEARCH_CHIPS" :key="c.kw" size="tiny"
                    :type="onlineKeyword === c.kw ? 'primary' : 'default'"
                    :secondary="onlineKeyword !== c.kw"
                    @click="clickChip(c)">{{ c.label }}</n-button>
        </div>
        <div class="online-bar">
          <n-radio-group v-model:value="onlineKind" size="small">
            <n-radio-button value="motion">动作</n-radio-button>
            <n-radio-button value="model">模型</n-radio-button>
          </n-radio-group>
          <n-input v-model:value="onlineKeyword" size="small" clearable
                   placeholder="或自己输入关键词，如：挥手再见"
                   @keydown.enter="searchOnline(1)" />
          <n-button size="small" type="primary" :loading="onlineLoading"
                    @click="searchOnline(1)">搜索</n-button>
        </div>
        <n-spin :show="onlineLoading">
          <n-empty v-if="onlineSearched && !onlineResults.length && !onlineLoading"
                   description="没有找到相关作品" style="padding: 30px 0" />
          <div class="cards online-cards">
            <div v-for="w in onlineResults" :key="w.work_uuid" class="card">
              <img v-if="w.cover" :src="w.cover" class="cover" loading="lazy" />
              <div class="card-title" :title="w.work_name">{{ w.work_name }}</div>
              <div class="card-meta">
                <n-tag v-if="onlineKind === 'motion'" size="tiny" :bordered="false"
                       :type="catType(guessWorkCat(w.work_name))">
                  {{ catLabel(guessWorkCat(w.work_name)) }}
                </n-tag>
                <span>{{ w.author }}</span>
                <span>{{ w.downloads }} 次下载</span>
              </div>
              <div class="card-actions">
                <n-button size="tiny" type="primary" secondary
                          :loading="downloading.has(w.work_uuid)"
                          @click="downloadWork(w)">下载并导入</n-button>
                <n-button size="tiny" quaternary tag="a" :href="w.url" target="_blank">
                  官网
                </n-button>
              </div>
            </div>
          </div>
          <div v-if="onlineResults.length && onlineResults.length < onlineTotal" class="more">
            <n-button size="small" quaternary :loading="onlineLoading"
                      @click="searchOnline(onlinePage + 1)">
              加载更多（{{ onlineResults.length }} / {{ onlineTotal }}）
            </n-button>
          </div>
        </n-spin>
      </n-tab-pane>

      <n-tab-pane name="motions" :tab="`我的动作 (${assets.motions.length})`">
        <div class="lib-bar">
          <n-input v-model:value="search" placeholder="搜索已入库动作…" clearable size="small" />
          <n-button size="small" :loading="recategorizing" @click="recategorize">
            重新归类全部
          </n-button>
        </div>
        <div class="chips">
          <n-button size="tiny" :type="motionFilter === 'all' ? 'primary' : 'default'"
                    :secondary="motionFilter !== 'all'" @click="motionFilter = 'all'">
            全部 {{ motionCounts.all }}
          </n-button>
          <n-button v-for="c in MOTION_CATS" :key="c.key" size="tiny"
                    :type="motionFilter === c.key ? 'primary' : 'default'"
                    :secondary="motionFilter !== c.key"
                    @click="motionFilter = c.key">
            {{ c.label }} {{ motionCounts[c.key] }}
          </n-button>
        </div>
        <n-empty v-if="!filteredMotions.length" description="这一类还没有动作，去「在线下载」搜一下" />
        <div class="cards">
          <div v-for="a in filteredMotions" :key="a.id" class="card">
            <div class="card-title" :title="a.label">{{ stripCatPrefix(a.label) }}</div>
            <div class="card-meta">
              <n-tag size="tiny" :bordered="false" :type="catType(parseMotionCat(a))">
                {{ catLabel(parseMotionCat(a)) }}
              </n-tag>
              <span>{{ fmtSize(a.size) }}</span>
            </div>
            <div class="card-actions">
              <n-select size="tiny" :value="parseMotionCat(a)" :options="catSelectOptions"
                        style="width: 92px"
                        @update:value="(v: MotionCat) => changeCat(a, v)" />
              <n-popconfirm @positive-click="removeAsset(a)">
                <template #trigger>
                  <n-button size="tiny" quaternary type="error">删除</n-button>
                </template>
                确定删除该动作及文件？
              </n-popconfirm>
            </div>
          </div>
        </div>
      </n-tab-pane>

      <n-tab-pane name="cameras" :tab="`我的运镜 (${assets.cameras.length})`">
        <n-input v-model:value="search" placeholder="搜索镜头…" clearable size="small"
                 style="margin-bottom: 8px" />
        <n-empty v-if="!filteredCameras.length" description="还没有镜头，去「在线下载」搜运镜，或等内置运镜自动生成" />
        <div class="cards">
          <div v-for="a in filteredCameras" :key="a.id" class="card">
            <div class="card-title" :title="a.label">{{ stripCatPrefix(a.label) }}</div>
            <div class="card-meta">
              <n-tag size="tiny" :bordered="false" type="info">镜头</n-tag>
              <span>{{ fmtSize(a.size) }}</span>
            </div>
            <div class="card-actions">
              <n-popconfirm @positive-click="removeAsset(a)">
                <template #trigger>
                  <n-button size="tiny" quaternary type="error">删除</n-button>
                </template>
                确定删除该镜头及文件？
              </n-popconfirm>
            </div>
          </div>
        </div>
      </n-tab-pane>

      <n-tab-pane name="models" :tab="`模型 (${assets.models.length})`">
        <n-input v-model:value="search" placeholder="搜索模型…" clearable size="small"
                 style="margin-bottom: 8px" />
        <n-empty v-if="!filteredModels.length" description="暂无模型" />
        <div class="cards">
          <div v-for="a in filteredModels" :key="a.id" class="card">
            <div class="card-title">{{ a.label }}</div>
            <div class="card-meta">
              <n-tag size="tiny" :bordered="false">{{ a.fmt }}</n-tag>
              <span>{{ fmtSize(a.size) }}</span>
            </div>
            <div class="card-actions">
              <n-button size="tiny" type="primary" secondary @click="useModel(a)">
                当前角色使用
              </n-button>
              <n-popconfirm @positive-click="removeAsset(a)">
                <template #trigger>
                  <n-button size="tiny" quaternary type="error">删除</n-button>
                </template>
                确定删除该模型及文件？
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
