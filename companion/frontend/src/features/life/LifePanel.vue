<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue';
import { NDrawer, NDrawerContent } from 'naive-ui';
import { useCharacterStore } from '../../stores/character';
import { coins, refreshCoinsSoon } from '../coins/session';
import { stage } from '../../engine/stage';
import { useChatStore } from '../../stores/chat';
import { useSettingsStore } from '../../stores/settings';
import { beginMeal, beginRide, beginTeaTime, endLifePreview, enterLifeStage, leaveLifeStage, returnLifeHome, setLifeHome, stageLife, visitLifeDestination, recordLifeGift, configureLifeItems, setLifeInteraction } from './stageLife';
import { isPetShell } from '../shell/mode';
import JourneyPanel from '../journey/JourneyPanel.vue';
import type { JourneyReward } from '../../api/client';
import { api } from '../../api/client';

const props = defineProps<{ show: boolean }>();
const emit = defineEmits<{ (e: 'update:show', value: boolean): void }>();
type Item = { id: string; category: string; name: string; icon: string; price: number; description: string; slot?: string; art?: string; destination?: string; kind?: string; market?: string; brand?: string; model?: string; reference_price?: string; tier?: string };
type LifeState = { catalog: Item[]; owned: { item_id: string; placed: number }[]; orders: { id: string; item_id: string; price: number; state: string; created: number }[]; memories: { id: string; item_id: string; text: string; created: number; allow_recall: number }[]; preferences: { taste: string; avoid: string; context_allowed: number }; recovery_errors: string[] };
const characters = useCharacterStore();
const settings = useSettingsStore();
const data = ref<LifeState | null>(null);
const tab = ref('space');
const selected = ref<Item | null>(null);
const result = ref<Item | null>(null);
const activity = ref<Item | null>(null);
const preview = ref<Item | null>(null);
const windowWidth = ref(window.innerWidth);
const onResize = () => { windowWidth.value = window.innerWidth; };
onMounted(() => window.addEventListener('resize', onResize));
onUnmounted(() => { window.removeEventListener('resize', onResize); stopFoodDrag(); });
const note = ref('');
const memory = ref('');
const draftMemory = ref('');
const editingMemory = ref('');
const editedMemory = ref('');
const memorySearch = ref('');
const orderFilter = ref('all');
const error = ref('');
const taste = ref('');
const avoid = ref('');
const contextAllowed = ref(false);
const preferenceStatus = ref('');
const busy = ref(false);
const giftReward = ref<JourneyReward | null>(null);
const giftCoinRewards = ref<{ id: string; title: string; coin: number }[]>([]);
const giftPreferenceIds = ref<string[]>([]);
const journeyLevel = ref(1);
const giftTags: Record<string, string[]> = {
  flower: ['romance', 'nature'], tea: ['daily', 'quiet'], book: ['quiet', 'creative'],
  brush: ['creative', 'daily'], card: ['romance', 'memory'], album: ['memory', 'creative'],
  wind_chime: ['nature', 'quiet'], glasses: ['style', 'daily'], hat: ['style', 'nature'],
  casual_outfit: ['style', 'daily'], coat_outfit: ['style', 'quiet'], dress_outfit: ['style', 'romance'],
};
function preferredGift(item: Item) {
  return item.category === 'gift' && journeyLevel.value >= 3 && (giftTags[item.id] || []).some(tag => giftPreferenceIds.value.includes(tag));
}
const dragging = ref<Item | null>(null);
const outingMode = ref<'places' | 'garage'>('places');
const placeKind = ref('全部');
const vehicleTier = ref('全部');
const mealSection = ref<'menu' | 'daily' | 'taste'>('menu');
const mealKind = ref('全部');
const dragPoint = ref({ x: 0, y: 0 });
const owned = computed(() => new Set(data.value?.owned.map(x => x.item_id) || []));
const visibleMemories = computed(() => {
  const query = memorySearch.value.trim().toLocaleLowerCase();
  return (data.value?.memories || []).filter(m => !query || m.text.toLocaleLowerCase().includes(query));
});
const visibleOrders = computed(() => (data.value?.orders || []).filter(order => {
  if (orderFilter.value === 'all') return true;
  const category = data.value?.catalog.find(item => item.id === order.item_id)?.category;
  return orderFilter.value === 'done' ? order.state === 'done' : category === orderFilter.value;
}));
const displayed = computed(() => {
  const current = (data.value?.catalog || []).filter(x => data.value?.owned.some(o => o.item_id === x.id && o.placed));
  return preview.value ? [...current.filter(x => x.slot !== preview.value?.slot), preview.value] : current;
});
const items = computed(() => (data.value?.catalog || []).filter(x => x.category === tab.value));
const mealKinds = [
  { id:'全部', label:'全部', art:'rice_set' }, { id:'noodles', label:'面食', art:'tomato_noodles' },
  { id:'home_dish', label:'米饭小炒', art:'braised_pork' }, { id:'hotpot', label:'火锅', art:'tomato_pot' },
  { id:'cake', label:'蛋糕', art:'celebration_cake' }, { id:'dessert', label:'甜点', art:'pudding' },
  { id:'coffee', label:'咖啡', art:'cappuccino' }, { id:'milk_tea', label:'奶茶', art:'pearl_tea' },
  { id:'fruit_tea', label:'果茶', art:'peach_tea' },
];
const meals = computed(() => (data.value?.catalog || []).filter(x => x.category === 'meal'));
const visibleMeals = computed(() => meals.value.filter(x => mealKind.value === '全部' || x.kind === mealKind.value));
const dailyMeals = [
  {id:'noodles',name:'家常面',kind:'主食'}, {id:'hotpot',name:'番茄火锅',kind:'热锅'},
  {id:'home_dish',name:'家常饭',kind:'主食'}, {id:'cake',name:'草莓蛋糕',kind:'甜点'},
  {id:'dessert',name:'水果布丁',kind:'甜点'}, {id:'coffee',name:'拿铁咖啡',kind:'饮品'},
  {id:'milk_tea',name:'珍珠奶茶',kind:'饮品'}, {id:'fruit_tea',name:'水果茶',kind:'饮品'},
];
const vehicleMarket = computed(() => settings.locale.ui || 'zh-CN');
const vehicles = computed(() => (data.value?.catalog || []).filter(x => x.category === 'vehicle' && x.market === vehicleMarket.value));
const vehicleTiers = computed(() => ['全部', ...new Set(vehicles.value.map(x => x.tier || '其他'))]);
const visibleVehicles = computed(() => vehicles.value.filter(x => vehicleTier.value === '全部' || x.tier === vehicleTier.value));
const destinations = [
  { id:'park', name:'公园小道', kind:'散步', note:'沿着树影慢慢走一圈。' },
  { id:'coast', name:'海边栈道', kind:'自然', note:'听海浪，把日落留到最后。' },
  { id:'mountain', name:'山间观景台', kind:'自然', note:'越过云海，看一场开阔的晨光。' },
  { id:'camp', name:'湖边营地', kind:'自然', note:'在湖风和灯火旁坐一会儿。' },
  { id:'cafe', name:'街角咖啡馆', kind:'约会', note:'找个靠窗的位置喝杯热饮。' },
  { id:'bookstore', name:'雨夜书店', kind:'约会', note:'在书架之间挑一本共同读物。' },
  { id:'cinema', name:'屋顶影院', kind:'约会', note:'在城市夜景里选一部电影。' },
  { id:'aquarium', name:'海洋馆', kind:'约会', note:'隔着蓝色水光看鱼群游过。' },
  { id:'museum', name:'美术馆', kind:'文化', note:'边看展，边聊各自喜欢的作品。' },
  { id:'night_market', name:'灯火夜市', kind:'烟火', note:'沿着摊位慢慢逛，找点想吃的。' },
  { id:'teashop', name:'茶饮店', kind:'烟火', note:'选一杯今天最想喝的味道。' },
  { id:'restaurant', name:'家常餐厅', kind:'烟火', note:'认真坐下来，一起吃顿热饭。' },
  { id:'hotpot_restaurant', name:'热气火锅店', kind:'烟火', note:'围着热锅，把聊天慢慢煮开。' },
  { id:'kitchen', name:'共同厨房', kind:'日常', note:'回到厨房，准备一顿家常饭。' },
];
const placeKinds = ['全部', '散步', '自然', '约会', '文化', '烟火', '日常'];
const visibleDestinations = computed(() => destinations.filter(x => placeKind.value === '全部' || x.kind === placeKind.value));
function formatCoins(value: number) { return new Intl.NumberFormat('zh-CN').format(value); }
function productArt(item: Item) {
  if (item.category === 'home') return `/assets/life/${item.art || item.id}.jpg`;
  if (item.id === 'rain' || item.id === 'stars') return '/assets/life/room.jpg';
  return `/assets/life/${item.art || item.id}.png`;
}
function companionship(value: number) {
  const perHour = Math.max(1, coins.perMin || 2) * 60;
  const hours = Math.ceil(value / perHour);
  if (hours < 24) return `约 ${hours} 小时陪伴`;
  return `约 ${Math.ceil(hours / 24)} 个陪伴日`;
}
const illustrated = new Set(['flower', 'tea', 'book', 'brush', 'card', 'album', 'wind_chime', 'glasses', 'hat', 'casual_outfit', 'coat_outfit', 'dress_outfit', 'lamp', 'picture', 'plant']);
let loadGeneration = 0;

async function request(path: string, method = 'GET', body?: unknown) {
  const response = await fetch('/api/life' + path, { method, headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined });
  if (!response.ok) { const obj = await response.json().catch(() => ({})); throw new Error(obj.detail || 'unavailable'); }
  return response.status === 204 ? null : response.json();
}
async function load() {
  if (!characters.currentId) return;
  const characterId = characters.currentId;
  const generation = ++loadGeneration;
  try {
    const row: LifeState = await request(`?character_id=${characterId}`);
    void api.journeyState(characterId).then(journey => {
      giftPreferenceIds.value = journey.preferences.map(x => x.id);
      journeyLevel.value = journey.ai_level.level;
    }).catch(() => {});
    if (generation !== loadGeneration || characters.currentId !== characterId) return;
    data.value = row;
    configureLifeItems(row.catalog);
    taste.value = data.value?.preferences?.taste || '';
    avoid.value = data.value?.preferences?.avoid || '';
    contextAllowed.value = !!data.value?.preferences?.context_allowed;
    stageLife.placed = data.value?.owned.filter(x => x.placed).map(x => x.item_id) || [];
    if (!stageLife.previewHome) setLifeHome(stageLife.placed.find(x => row.catalog.some(item => item.id === x && item.category === 'home')) || 'room');
    if (data.value?.recovery_errors.length) error.value = '有一笔订单正在确认中，可在购买记录中查看进度。';
  } catch { if (generation === loadGeneration && characters.currentId === characterId) error.value = '共同空间没有加载成功，请稍后再来。'; }
}
watch(() => [props.show, characters.currentId], () => {
  if (props.show) {
    data.value = null; result.value = null;
    if (stageLife.memoryDraft) { draftMemory.value = stageLife.memoryDraft; stageLife.memoryDraft = ''; tab.value = 'memory'; }
    void load();
  }
});
function lifeReply(type: 'preview' | 'purchased' | 'offered', item: Item) {
  if (!characters.currentId) return;
  setLifeInteraction(type, item.id);
  void useChatStore().send('回应刚发生的共同生活互动', { hideUser: true, scripted: true, mode: 'life' });
}
function choose(item: Item) {
  selected.value = item; note.value = ''; error.value = '';
  lifeReply('preview', item);
}
function startAgain(itemId: string) {
  const item = data.value?.catalog.find(x => x.id === itemId && x.category === 'activity');
  if (item) { activity.value = item; tab.value = 'space'; }
}
async function purchaseItem(item: Item, offerAfter = false) {
  if (busy.value) return false;
  const characterId = characters.currentId;
  busy.value = true; error.value = '';
  // Keep the same id across a lost response; the server also recovers pending orders on load.
  const orderId = crypto.randomUUID();
  try {
    const response = await request('/purchase', 'POST', { order_id: orderId, character_id: characterId, item_id: item.id, note: note.value });
    giftReward.value = item.category === 'gift' ? response?.journey?.reward || null : null;
    giftCoinRewards.value = item.category === 'gift' ? response?.journey?.coin_granted_now || [] : [];
    memory.value = note.value; selected.value = null;
    if (item.category === 'activity') activity.value = item;
    if (item.category === 'gift') {
      if (characters.currentId === characterId) recordLifeGift(item.id, characterId);
    }
    refreshCoinsSoon(); await load();
    if (characters.currentId === characterId) {
      result.value = item;
      if (offerAfter && item.category === 'meal') {
        await beginMeal(item.id);
        emit('update:show', false);
        lifeReply('offered', item);
      } else {
        lifeReply('purchased', item);
      }
    }
    return true;
  } catch (e) {
    const code = e instanceof Error ? e.message : '';
    error.value = code === 'funds' ? '金币还不够，先去陪伴和互动中攒一些吧。' : code === 'upgrade_required' ? '当前版本无法完成购买，请更新应用后再试。' : '这笔订单正在确认中，请稍后在购买记录中查看。';
    selected.value = null;
    await load();
    return false;
  } finally { busy.value = false; }
}
async function buy() {
  if (!selected.value) return;
  await purchaseItem(selected.value);
}
function stopFoodDrag() {
  dragging.value = null;
  window.removeEventListener('pointermove', moveFoodDrag);
  window.removeEventListener('pointerup', finishFoodDrag);
  window.removeEventListener('pointercancel', stopFoodDrag);
}
function moveFoodDrag(event: PointerEvent) {
  dragPoint.value = { x: event.clientX, y: event.clientY };
}
async function finishFoodDrag(event: PointerEvent) {
  const item = dragging.value;
  const hit = !!item && stage.hitsAvatar(event.clientX, event.clientY);
  stopFoodDrag();
  if (!item || !hit) return;
  await purchaseItem(item, true);
}
function startFoodDrag(event: PointerEvent, item: Item) {
  if (busy.value || event.button !== 0) return;
  event.preventDefault();
  dragging.value = item;
  dragPoint.value = { x: event.clientX, y: event.clientY };
  window.addEventListener('pointermove', moveFoodDrag);
  window.addEventListener('pointerup', finishFoodDrag, { once: true });
  window.addEventListener('pointercancel', stopFoodDrag, { once: true });
}
async function place(item: Item, placed: boolean) {
  try { await request('/place', 'POST', { item_id: item.id, placed }); preview.value = null; endLifePreview(); await load(); } catch { error.value = '这次布置没有保存下来，请再试一次。'; }
}
async function moveIntoHome(item: Item) {
  if (busy.value) return;
  if (isPetShell) { error.value = '请先切换到舞台模式，再搬入新家。'; return; }
  const previousHome = stageLife.home;
  const alreadyActive = data.value?.owned.some(row => row.item_id === item.id && !!row.placed);
  error.value = '';
  endLifePreview();
  setLifeHome(item.id);
  if (!enterLifeStage()) { setLifeHome(previousHome); error.value = '请先切换到舞台模式，再搬入新家。'; return; }
  emit('update:show', false);
  if (alreadyActive) return;
  busy.value = true;
  try {
    await request('/place', 'POST', { item_id: item.id, placed: true });
    await load();
    if (stageLife.home !== item.id) setLifeHome(item.id);
    lifeReply('purchased', item);
  } catch {
    setLifeHome(previousHome);
    error.value = '这次搬家没有保存下来，已经回到原来的住处，请再试一次。';
  } finally { busy.value = false; }
}
function enterHome() {
  if (stageLife.destination) returnLifeHome();
  if (enterLifeStage()) emit('update:show', false);
  else error.value = '请先切换到舞台模式，再进入我们的家。';
}
function previewOnStage(item: Item) {
  if (isPetShell) { error.value = '请先切换到舞台模式，再试摆。'; return; }
  if (stageLife.destination) returnLifeHome();
  if (item.category === 'home') setLifeHome(item.id, true);
  if (!enterLifeStage()) { error.value = '请先切换到舞台模式，再试摆。'; return; }
  if (item.category !== 'home') stageLife.preview = item.id;
  emit('update:show', false);
}
function visit(destination: string) {
  if (visitLifeDestination(destination)) emit('update:show', false);
  else error.value = '请先切换到舞台模式。';
}
async function teaTogether() {
  try {
    if (await beginTeaTime()) emit('update:show', false);
    else error.value = '请先切换到舞台模式。';
  } catch { error.value = '这次相聚没有开始，可以继续在咖啡馆聊聊天。'; }
}
async function eatTogether(item: string) {
  try {
    if (await beginMeal(item)) emit('update:show', false);
    else error.value = '请先切换到舞台模式。';
  } catch { error.value = '这次互动没有开始，请再试一次。'; }
}
async function savePreferences() {
  preferenceStatus.value = '';
  try {
    await request('/preferences', 'PUT', { character_id: characters.currentId, taste: taste.value, avoid: avoid.value, context_allowed: contextAllowed.value });
    preferenceStatus.value = '已经记下了。清空内容并保存即可删除。';
  } catch { preferenceStatus.value = '保存失败，请重试。'; }
}
async function rideTogether(item: string) {
  try {
    if (await beginRide(item)) emit('update:show', false);
    else error.value = '请先切换到舞台模式。';
  } catch { error.value = '这次互动没有开始，请再试一次。'; }
}
async function saveMemory() {
  if (!result.value || !memory.value.trim()) return;
  try { await request('/memories', 'POST', { character_id: characters.currentId, item_id: result.value.id, text: memory.value }); result.value = null; await load(); }
  catch { error.value = '回忆暂时未保存，请重试。'; }
}
async function removeMemory(id: string) {
  try { await request(`/memories/${id}?character_id=${characters.currentId}`, 'DELETE'); await load(); }
  catch { error.value = '删除失败，请重试。'; }
}
async function addFreeMemory() {
  if (!draftMemory.value.trim()) return;
  try { await request('/memories', 'POST', { character_id: characters.currentId, item_id: 'manual', text: draftMemory.value }); draftMemory.value = ''; await load(); }
  catch { error.value = '回忆暂时未保存，请重试。'; }
}
async function editMemory(id: string) {
  if (!editedMemory.value.trim()) return;
  try { await request(`/memories/${id}`, 'PUT', { character_id: characters.currentId, text: editedMemory.value }); editingMemory.value = ''; await load(); }
  catch { error.value = '回忆暂时未保存，请重试。'; }
}
async function setRecall(id: string, allowed: boolean) {
  try { await request(`/memories/${id}/recall`, 'PUT', { character_id: characters.currentId, allowed }); await load(); }
  catch { error.value = '回忆设置未保存，请重试。'; }
}
function exportMemories() {
  const blob = new Blob([(data.value?.memories || []).map(m => `${new Date(m.created * 1000).toLocaleDateString()}\n${m.text}`).join('\n\n')], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = '我们的回忆.txt'; a.click(); URL.revokeObjectURL(url);
}
</script>

<template>
  <n-drawer :show="show" :width="Math.min(760, Math.max(320, windowWidth - 16))" placement="right" show-mask="transparent" @update:show="v => emit('update:show', v)">
    <n-drawer-content title="我们的空间" closable :native-scrollbar="false">
      <div class="life">
        <header class="life-head"><div><div class="eyebrow">A LITTLE PLACE FOR US</div><h1>一起生活，慢慢抵达</h1><p class="intro">每一次选择都会留在共同生活里。普通陪伴一直免费。</p></div><div class="wallet"><small>共同生活基金</small><strong>{{ formatCoins(Math.floor(coins.balanceMilli / 1000)) }}</strong><span>金币 · 当前约 {{ Math.max(1, Math.round(coins.perMin || 2)) }}/分钟</span></div></header>
        <nav><button v-for="x in [['space','空间'],['home','住宅'],['meal','餐桌'],['gift','心意'],['decor','布置'],['visit','出门'],['memory','回忆'],['orders','记录']]" :key="x[0]" :class="{active: tab === x[0]}" @click="tab = x[0]">{{ x[1] }}</button><button v-if="settings.modules.journey !== false" :class="{active: tab === 'journey'}" @click="tab = 'journey'">我们的故事</button></nav>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <section v-if="tab === 'space'" class="home-card">
          <p class="eyebrow">OUR LITTLE CORNER</p><h2>回到我们的家</h2><p>选一处喜欢的住处，把熟悉的物件和共同经历留在这里。</p>
          <button v-if="!stageLife.active" :disabled="isPetShell" @click="enterHome">回家</button>
          <button v-else @click="leaveLifeStage">回到原来的地方</button>
          <button v-if="stageLife.preview || stageLife.previewHome" @click="endLifePreview">结束预览</button>
          <button @click="tab = 'decor'">看看布置</button><p v-if="isPetShell">请回到完整窗口后进入共同空间。</p>
        </section>
        <section v-else-if="tab === 'meal'" class="table-page">
          <div class="section-lead meal-lead"><div><span class="eyebrow">OUR TABLE</span><h2>今天一起吃什么？</h2><p>想认真准备一份餐点，或从日常餐桌直接开饭。</p></div><div class="segmented meal-sections"><button :class="{active: mealSection === 'menu'}" @click="mealSection = 'menu'">精选菜单</button><button :class="{active: mealSection === 'daily'}" @click="mealSection = 'daily'">日常餐桌</button><button :class="{active: mealSection === 'taste'}" @click="mealSection = 'taste'">口味档案</button></div></div>
          <template v-if="mealSection === 'menu'">
            <div class="meal-filter" aria-label="餐点分类"><button v-for="kind in mealKinds" :key="kind.id" :class="{active: mealKind === kind.id}" @click="mealKind = kind.id"><img :src="`/assets/life/${kind.art}.png`" alt="" />{{ kind.label }}<small>{{ kind.id === '全部' ? meals.length : meals.filter(x => x.kind === kind.id).length }}</small></button></div>
            <p class="meal-guide">拖动餐点到角色身上可以直接送出；点击卡片则先查看详情。</p>
            <div class="meal-grid"><article v-for="dish in visibleMeals" :key="dish.id" class="meal-card"><div class="meal-visual"><img class="food-draggable" :src="`/assets/life/${dish.art}.png`" :alt="dish.name" draggable="false" @pointerdown="startFoodDrag($event, dish)" /></div><div class="meal-copy"><small>{{ mealKinds.find(x => x.id === dish.kind)?.label }} · 单次餐点</small><h3>{{ dish.name }}</h3><p>{{ dish.description }}</p><div class="meal-buy"><b>{{ formatCoins(dish.price) }} <small>金币/份</small></b><button @click="choose(dish)">购买一份</button></div></div></article></div>
            <div v-if="!visibleMeals.length" class="empty-state">这个分类还没有餐点。</div>
          </template>
          <template v-else-if="mealSection === 'daily'">
            <div class="daily-note"><span>今日家常</span><div><strong>不用金币，随时开饭</strong><p>日常餐桌不会因为没有金币而关闭。选择一份，她会感知眼前的食物并自然聊天。</p></div></div>
            <div class="daily-grid"><article v-for="dish in dailyMeals" :key="dish.id" class="daily-card"><img :src="`/assets/life/${dish.id}.png`" :alt="dish.name" /><div><small>{{ dish.kind }}</small><strong>{{ dish.name }}</strong><button @click="eatTogether(dish.id)">一起享用</button></div></article></div>
          </template>
          <template v-else>
            <div class="taste-card"><div class="taste-intro"><img :src="'/assets/life/card.png'" alt="" /><div><h3>让她记得你的口味</h3><p>这些内容只在聊到吃饭时提供参考，你可以随时修改或清空。</p></div></div><div class="taste-fields"><label><span>喜欢的味道</span><textarea v-model="taste" class="memory-input" maxlength="200" placeholder="例如：微辣、喜欢热饮、偏爱甜口" /></label><label><span>不喜欢或需要避开</span><textarea v-model="avoid" class="memory-input" maxlength="200" placeholder="例如：香菜、花生、太甜" /></label></div><label class="memory-consent"><input v-model="contextAllowed" type="checkbox" /><span><b>在饮食聊天中记得这些偏好</b><small>关闭后将不再用于对话。</small></span></label><div class="taste-actions"><button class="buy-main" @click="savePreferences">保存口味档案</button><p v-if="preferenceStatus" role="status">{{ preferenceStatus }}</p></div></div>
          </template>
        </section>
        <section v-else-if="tab === 'visit'" class="outing"><div class="section-lead"><div><span class="eyebrow">GO SOMEWHERE TOGETHER</span><h2>今天想去哪里？</h2><p>地点与车库分开整理。去哪里免费，想收藏一辆车则是长期目标。</p></div><div class="segmented"><button :class="{active: outingMode === 'places'}" @click="outingMode = 'places'">目的地</button><button :class="{active: outingMode === 'garage'}" @click="outingMode = 'garage'">共同车库</button></div></div>
          <template v-if="outingMode === 'places'"><div class="filters"><button v-for="kind in placeKinds" :key="kind" :class="{active: placeKind === kind}" @click="placeKind = kind">{{ kind }}</button></div><div class="destination-grid"><article v-for="place in visibleDestinations" :key="place.id" class="destination-card" @click="visit(place.id)"><img :src="`/assets/life/${place.id}.jpg`" :alt="place.name" /><div><span>{{ place.kind }}</span><h3>{{ place.name }}</h3><p>{{ place.note }}</p><button @click.stop="visit(place.id)">现在出发</button><button v-if="place.id === 'cafe'" @click.stop="teaTogether">一起喝茶</button></div></article></div></template>
          <template v-else><div class="garage-summary"><div><small>当前市场</small><strong>{{ vehicleMarket === 'zh-CN' ? '中国大陆' : vehicleMarket === 'ja' ? '日本' : vehicleMarket === 'ko' ? '韩国' : vehicleMarket === 'ru' ? '俄罗斯' : 'United States' }}</strong></div><p>车辆随界面语言切换当地品牌与官方起售价。购买所需金币与当地原价数值一致，不再设置第二套折算价格。</p></div><div class="filters"><button v-for="tier in vehicleTiers" :key="tier" :class="{active: vehicleTier === tier}" @click="vehicleTier = tier">{{ tier }}</button></div><div class="vehicle-list"><article v-for="vehicle in visibleVehicles" :key="vehicle.id" class="vehicle-card"><div class="vehicle-visual"><img :src="`/assets/life/${vehicle.art}.png`" :alt="vehicle.name" /><span v-if="owned.has(vehicle.id)">已收藏</span></div><div class="vehicle-copy"><small>{{ vehicle.brand }} · {{ vehicle.tier }}</small><h3>{{ vehicle.model }}</h3><p>{{ vehicle.description }}</p><div class="price-stack vehicle-price"><span>原价 <b>{{ vehicle.reference_price }}</b></span><em>购买需要 {{ formatCoins(vehicle.price) }} 金币 · {{ companionship(vehicle.price) }}</em></div><button v-if="owned.has(vehicle.id)" @click="rideTogether(vehicle.id)">在车库看看</button><button v-else @click="choose(vehicle)">了解并收藏</button></div></article></div></template>
        </section>
        <section v-else-if="['home','gift','decor'].includes(tab)" class="grid">
          <article v-for="item in items" :key="item.id" :class="['item',{preferred:preferredGift(item)}]">
            <div class="item-art" :class="item.category" :style="item.category === 'home' ? { backgroundImage: `linear-gradient(0deg,#31262288,#31262210),url('/assets/life/${item.art || item.id}.jpg')` } : {}"><img v-if="illustrated.has(item.id)" class="object-art" :src="`/assets/life/${item.id}.png`" :alt="item.name" /><span v-if="item.tier" class="tier-badge">{{ item.tier }}</span></div><strong>{{ item.name }}</strong><p>{{ item.description }}</p><div v-if="item.reference_price" class="real-price">现实参考 {{ item.reference_price }}</div><div v-if="item.category === 'home' && !owned.has(item.id)" class="goal-time">{{ companionship(item.price) }}</div>
            <template v-if="owned.has(item.id)"><button v-if="item.category === 'home'" :disabled="busy" @click="moveIntoHome(item)">{{ data?.owned.find(x => x.item_id === item.id)?.placed ? '回到这里' : '立即搬入' }}</button><button v-else @click="place(item, !data?.owned.find(x => x.item_id === item.id)?.placed)">{{ data?.owned.find(x => x.item_id === item.id)?.placed ? '收起' : '摆放' }}</button></template>
            <template v-else><button @click="choose(item)">{{ formatCoins(item.price) }} 金币 · 查看</button><button v-if="item.category === 'home' || (item.category === 'decor' && ['lamp','picture','plant','rain','stars'].includes(item.id))" @click="previewOnStage(item)">免费预览</button></template>
          </article>
        </section>
        <section v-else-if="tab === 'memory'" class="memory-page">
          <div class="memory-compose"><div><p class="eyebrow">OUR STORY</p><h2>写下想共同记住的事</h2><p>只有你主动保存的内容才会留在这里；每条回忆都可以单独决定是否允许她自然提起。</p></div><textarea v-model="draftMemory" class="memory-input" maxlength="500" placeholder="例如：今天我们第一次搬进海边的家……" /><div class="memory-actions"><span>{{ draftMemory.length }}/500</span><button :disabled="!draftMemory.trim()" @click="addFreeMemory">保存这段回忆</button><button @click="exportMemories">导出全部</button></div></div>
          <div class="memory-toolbar"><strong>{{ data?.memories.length || 0 }} 段共同回忆</strong><input v-model="memorySearch" type="search" placeholder="搜索回忆内容" /></div>
          <div class="memory-list"><article v-for="m in visibleMemories" :key="m.id" class="record memory-record"><header><time>{{ new Date(m.created * 1000).toLocaleDateString() }}</time><span :class="{remembered: m.allow_recall}">{{ m.allow_recall ? '她可以自然提起' : '仅你可见' }}</span></header><template v-if="editingMemory === m.id"><textarea v-model="editedMemory" class="memory-input" maxlength="500" /><div class="record-actions"><button @click="editMemory(m.id)">保存修改</button><button @click="editingMemory = ''">取消</button></div></template><template v-else><p>{{ m.text }}</p><div class="record-actions"><button class="recall-toggle" @click="setRecall(m.id, !m.allow_recall)">{{ m.allow_recall ? '改为仅自己保留' : '允许她自然提起' }}</button><button @click="editingMemory = m.id; editedMemory = m.text">编辑</button><button class="danger" @click="removeMemory(m.id)">删除</button></div></template></article></div>
          <p v-if="!data?.memories.length" class="empty-state">还没有回忆。送出心意、搬入新家或一起做点什么之后，都可以回来记下一笔。</p><p v-else-if="!visibleMemories.length" class="empty-state">没有找到包含“{{ memorySearch }}”的回忆。</p>
        </section>
        <JourneyPanel v-else-if="tab === 'journey'" :show="show" />
        <section v-else class="orders-page"><div class="section-lead"><div><p class="eyebrow">LIFE LEDGER</p><h2>共同生活记录</h2><p>每一笔金币去向都清楚保留，未完成订单不会重复扣款。</p></div></div><div class="order-filters"><button v-for="filter in [['all','全部'],['gift','心意'],['meal','餐饮'],['home','住宅'],['vehicle','出行'],['done','已完成']]" :key="filter[0]" :class="{active:orderFilter===filter[0]}" @click="orderFilter=filter[0]">{{ filter[1] }}</button></div><div class="order-list"><article v-for="o in visibleOrders" :key="o.id" class="record order-record"><div class="order-art"><img :src="productArt(data?.catalog.find(x => x.id === o.item_id) || { id:'card', category:'gift', name:'生活记录', icon:'card', price:0, description:'' })" alt="" /></div><div><small>{{ new Date(o.created * 1000).toLocaleString() }}</small><strong>{{ data?.catalog.find(x => x.id === o.item_id)?.name || '已下架物品' }}</strong><span>{{ formatCoins(o.price) }} 金币</span></div><b :class="`state-${o.state}`">{{ o.state === 'done' ? '已完成' : o.state === 'failed' ? '未扣款' : '确认中' }}</b></article></div><p v-if="!visibleOrders.length" class="empty-state">这个分类还没有记录。</p></section>
        <div v-if="selected" class="dialog" role="dialog" aria-label="确认购买"><div class="purchase-sheet"><img class="purchase-art" :src="productArt(selected)" :alt="selected.name" /><small v-if="selected.brand">{{ selected.brand }} · {{ selected.tier }}</small><h3>{{ selected.name }}</h3><p>{{ selected.description }}</p><div v-if="selected.reference_price" class="reference-row"><span>{{ selected.category === 'vehicle' ? '原价' : '现实参考' }}</span><b>{{ selected.reference_price }}</b></div><div class="reference-row primary" v-if="selected.category !== 'vehicle'"><span>{{ selected.category === 'meal' ? '本次餐点' : '共同生活价' }}</span><b>{{ formatCoins(selected.price) }} 金币</b></div><p v-if="selected.category === 'meal'" class="meal-once-note">食品按份购买，这一份上桌后即消费，不会进入永久收藏。</p><p v-else class="goal-time">按当前速度 {{ companionship(selected.price) }}，它应该是值得期待的目标。</p><textarea v-if="selected.category === 'gift'" v-model="note" maxlength="200" placeholder="想说的话（可不填）" /><button class="buy-main" :disabled="busy" @click="buy">{{ selected.category === 'meal' ? '购买并端上餐桌' : selected.category === 'vehicle' ? `按原价支付 ${formatCoins(selected.price)} 金币` : '确认收藏 · 永久拥有' }}</button><button :disabled="busy" @click="selected = null">再想想</button></div></div>
        <div v-if="dragging" class="food-ghost" :style="{ left: `${dragPoint.x}px`, top: `${dragPoint.y}px` }"><img :src="`/assets/life/${dragging.art}.png`" :alt="dragging.name" /><span>拖到角色身上</span></div>
        <div v-if="result" class="dialog" role="dialog" aria-label="购买结果"><div><img class="purchase-art" :src="productArt(result)" :alt="result.name" /><h3>{{ result.name }}</h3><div v-if="giftReward" class="gift-reward"><strong>{{ giftReward.first_of_kind ? '第一份同类心意 · 首送加成' : '心意已经收到' }}</strong><div class="reward-numbers"><span>好感 <b>+{{ giftReward.affection_gained }}</b></span><span>陪伴经验 <b>+{{ giftReward.ai_xp_gained }}</b></span></div><p v-if="giftReward.preference_matched">投其所好 · 偏好礼物加成</p><p v-if="giftReward.affection_stage_up">关系进阶 · {{ giftReward.affection_stage }}</p><p v-if="giftReward.level_up">AI 陪伴等级提升 · Lv.{{ giftReward.new_level }}</p><p v-for="name in giftReward.inner_unlocked" :key="name">内心档案解锁 · {{ name }}</p><p v-for="coin in giftCoinRewards" :key="coin.id">{{ coin.title }} · +{{ coin.coin }} 金币</p><div v-if="giftReward.return_gift" class="return-gift"><strong>她也为你准备了回礼 · {{ giftReward.return_gift.name }}</strong><p>“{{ giftReward.return_gift.text }}”</p></div><small>已永久收进礼物图鉴</small></div><p>{{ result.category === 'meal' ? '这一份已经端上餐桌。下次想吃时需要重新购买。' : '已经收进你们共同的生活里了。' }}</p><p>想为这一刻留句话吗？由你决定是否保存。</p><textarea v-model="memory" maxlength="500" placeholder="写下这一刻（可不填）" /><button :disabled="!memory.trim()" @click="saveMemory">保存回忆</button><button @click="result = null">关闭</button><button v-if="result.category === 'vehicle'" @click="rideTogether(result.id); result = null">看看车辆</button></div></div>
      </div>
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
.memory-input{display:block;width:100%;box-sizing:border-box;min-height:80px;margin:10px 0;padding:10px;background:#201c1a;color:#f5e8d9;border:1px solid #ffffff33;border-radius:8px;resize:vertical}
.food-draggable{cursor:grab;touch-action:none;user-select:none}.food-draggable:active{cursor:grabbing}.food-ghost{position:fixed;z-index:5000;pointer-events:none;transform:translate(-50%,-50%);display:grid;place-items:center;filter:drop-shadow(0 12px 18px #0009)}.food-ghost img{width:120px;height:120px;object-fit:contain}.food-ghost span{padding:5px 9px;border-radius:999px;background:#211a16dd;color:#ffe7c2;font-size:12px}
.life{color:#f5e8d9;font-size:14px}.intro{color:#c8b7a8;line-height:1.7}.balance{color:#f7cf83}nav{display:flex;gap:5px;flex-wrap:wrap;margin:20px 0}button{cursor:pointer;border:1px solid #ae8f7055;border-radius:9px;padding:8px 12px;background:#41342f;color:#fae8d2}button:hover,.active{background:#765442}button:disabled{opacity:.5;cursor:default}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.item,.record{background:#302724;border:1px solid #ffffff12;border-radius:14px;padding:15px}.item p{min-height:44px;color:#c8b7a8;line-height:1.5}.icon{font-size:34px;display:block;margin-bottom:8px}.room{position:relative;min-height:290px;padding:24px;border-radius:18px;background:linear-gradient(#816e64,#493b36);text-align:center}.room.rainy{background:linear-gradient(#435669,#4b3f45)}.room.starry{background:linear-gradient(#343657,#4b3f45)}.window{font-size:54px;padding:20px;background:#ffffff19;border:6px solid #c9b4a0;border-radius:12px;width:90px;margin:auto}.wall{position:absolute;top:65px;left:35px;font-size:36px}.shelf{font-size:40px;margin:25px auto 8px;border-bottom:8px solid #ad846b;max-width:230px}.shelf span{margin-left:70px}.dialog{position:fixed;inset:0;background:#0009;display:flex;align-items:center;justify-content:center;z-index:3000;padding:20px}.dialog>div{width:min(380px,100%);background:#332a27;border-radius:18px;padding:24px;box-shadow:0 12px 40px #0008}.dialog button{margin:5px}.dialog textarea{display:block;width:100%;min-height:70px;box-sizing:border-box;background:#201c1a;color:white;border:1px solid #ffffff33;border-radius:8px;padding:10px}.error{color:#ffbcae}.record{margin:10px 0}.record p{white-space:pre-wrap;overflow-wrap:anywhere}
.eyebrow{letter-spacing:.24em;font-size:10px;color:#caab82;margin-top:5px}.intro{margin:8px 0}.balance{font-variant-numeric:tabular-nums}.life nav{gap:4px;border-bottom:1px solid #ffffff16;padding-bottom:12px}.life nav button{border:0;background:transparent;color:#b8aaa0;padding:8px 13px}.life nav button.active{background:#ead0ad;color:#292019}.room,.room.rainy,.room.starry{overflow:hidden;min-height:390px;padding:0;text-align:left;background:#564538 url('/assets/life/room.jpg') center/cover}.room-shade{position:absolute;inset:0;background:linear-gradient(90deg,rgba(26,20,19,.80),rgba(26,20,19,.05) 80%),linear-gradient(0deg,rgba(26,20,19,.45),transparent 60%)}.rainy .room-shade{background:linear-gradient(90deg,#1e2634c9,#1d324360)}.starry .room-shade{background:linear-gradient(90deg,#141a38d9,#22244777)}.room-copy{position:absolute;z-index:2;left:30px;bottom:30px;max-width:260px}.room-copy small{letter-spacing:.2em;color:#f2d1a5;font-size:10px}.room-copy h2{font-size:24px;line-height:1.3;margin:10px 0}.room-copy p{line-height:1.6;color:#f3e2d2}.room-copy button{background:#f2dfc5;color:#34271e;border:0}.placed{position:absolute;z-index:2;font-size:38px;filter:drop-shadow(0 3px 4px #25161088)}.plant{right:14%;bottom:28%}.lamp{right:27%;bottom:30%;width:90px}.picture{right:15%;top:20%;width:80px}.rain-effect,.stars-effect{display:none;position:absolute;inset:-100%;pointer-events:none}.rainy .rain-effect{display:block;background:repeating-linear-gradient(105deg,transparent 0 17px,#d8edff55 18px 19px,transparent 20px 42px);animation:rainfall .7s linear infinite}.starry .stars-effect{display:block;inset:12% 8% auto auto;letter-spacing:8px;font-size:21px;color:#fbe5a6;animation:twinkle 3s ease-in-out infinite}.activity-props{position:absolute;right:20%;bottom:23%;font-size:64px;z-index:2;filter:drop-shadow(0 5px 9px #24171099);animation:float 3s ease-in-out infinite}.steam{position:absolute;left:30px;top:-32px;font-size:32px;opacity:.75}.item{padding:0 0 16px;overflow:hidden}.item strong,.item p,.item button{margin-left:15px;margin-right:15px}.item-art{height:135px;margin-bottom:14px;background:linear-gradient(0deg,#31262288,#31262210),url('/assets/life/gifts.jpg') center/cover;display:flex;align-items:center;justify-content:center}.item-art.decor{background-image:linear-gradient(0deg,#31262288,#31262210),url('/assets/life/room.jpg')}.item-art.activity{background-image:linear-gradient(0deg,#31262288,#31262210),url('/assets/life/activities.jpg')}.object-art{height:125px;width:145px;object-fit:contain;filter:drop-shadow(0 5px 8px #24171099)}.item-art .icon{font-size:42px;filter:drop-shadow(0 4px 6px #241710bb);background:#211a1677;border-radius:50%;padding:12px}.item p{min-height:38px}.dialog>div{border:1px solid #d4b48a44;background:linear-gradient(140deg,#43342f,#282120)}@keyframes rainfall{to{transform:translate(-22px,42px)}}@keyframes twinkle{50%{opacity:.35}}@keyframes float{50%{transform:translateY(-7px)}}@media(max-width:500px){.grid{grid-template-columns:1fr 1fr}.room,.room.rainy,.room.starry{min-height:330px}.room-copy{left:20px;bottom:20px}}@media(prefers-reduced-motion:reduce){.rain-effect,.stars-effect,.activity-props{animation:none!important}}
.life-head{display:grid;grid-template-columns:1fr auto;gap:28px;align-items:end;padding:8px 2px 20px}.life-head h1{font-family:Georgia,'Noto Serif SC',serif;font-size:28px;font-weight:500;margin:8px 0 4px}.wallet{min-width:180px;padding:16px 18px;border:1px solid #e4bf8d38;border-radius:16px;background:linear-gradient(135deg,#5a4034aa,#281f1c);box-shadow:inset 0 1px #fff1}.wallet small,.wallet span{display:block;color:#baa89b;font-size:11px}.wallet strong{display:block;margin:3px 0;color:#f5d29c;font:500 27px/1.2 Georgia,serif;font-variant-numeric:tabular-nums}.life nav{position:sticky;top:-1px;z-index:20;padding:9px 0 12px;background:linear-gradient(#332925 78%,transparent);backdrop-filter:blur(14px)}.section-lead{display:flex;justify-content:space-between;gap:24px;align-items:end;margin:10px 0 18px}.section-lead h2{font:500 25px/1.2 Georgia,'Noto Serif SC',serif;margin:7px 0}.section-lead p{color:#bca99b;margin:0;max-width:430px}.segmented{display:flex;padding:4px;border:1px solid #ffffff12;border-radius:12px;background:#211a18}.segmented button{border:0;background:transparent;margin:0}.segmented button.active{background:#ead0ad;color:#2b211c}.filters{display:flex;gap:7px;overflow:auto;padding:3px 0 15px}.filters button{white-space:nowrap;border-radius:999px;padding:6px 12px;background:transparent}.filters button.active{background:#ead0ad;color:#2b211c}.destination-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.destination-card{position:relative;min-height:235px;border-radius:18px;overflow:hidden;border:1px solid #ffffff17;background:#271f1c;cursor:pointer}.destination-card>img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;transition:transform .45s ease}.destination-card:hover>img{transform:scale(1.035)}.destination-card:after{content:'';position:absolute;inset:0;background:linear-gradient(0deg,#191311f2 5%,#241a1588 48%,transparent 78%)}.destination-card>div{position:absolute;z-index:2;left:18px;right:18px;bottom:16px}.destination-card span{font-size:10px;letter-spacing:.18em;color:#eac698}.destination-card h3{font-size:20px;margin:4px 0}.destination-card p{color:#d1c0b1;margin:0 0 10px}.destination-card button{margin:0 6px 0 0;padding:6px 10px}.garage-summary{display:grid;grid-template-columns:150px 1fr;gap:22px;align-items:center;margin-bottom:14px;padding:15px 18px;border-left:2px solid #d5ad78;background:#ffffff08}.garage-summary small{display:block;color:#aa988b}.garage-summary strong{font-size:18px}.garage-summary p{margin:0;color:#baa99c;line-height:1.6}.vehicle-list{display:grid;gap:14px}.vehicle-card{display:grid;grid-template-columns:minmax(220px,42%) 1fr;min-height:220px;border:1px solid #ffffff14;border-radius:18px;overflow:hidden;background:linear-gradient(130deg,#2b2320,#201a18)}.vehicle-visual{position:relative;display:grid;place-items:center;background:radial-gradient(circle at 50% 65%,#80604855,transparent 58%),linear-gradient(160deg,#44352e,#241d1a)}.vehicle-visual img{width:90%;height:190px;object-fit:contain;filter:drop-shadow(0 18px 16px #0e090777)}.vehicle-visual span{position:absolute;left:13px;top:13px;padding:5px 9px;border-radius:999px;background:#dac198;color:#2b211c;font-size:11px}.vehicle-copy{padding:22px}.vehicle-copy>small{letter-spacing:.12em;color:#c8a97e}.vehicle-copy h3{font:500 25px/1.2 Georgia,'Noto Serif SC',serif;margin:6px 0}.vehicle-copy>p{color:#baa99c;line-height:1.55}.price-stack{display:grid;grid-template-columns:1fr 1fr;gap:5px 14px;margin:14px 0}.price-stack span{color:#9f8e82;font-size:12px}.price-stack b{display:block;color:#ebd8c0;font-size:14px}.price-stack em{grid-column:1/-1;color:#d3ae7a;font-size:11px;font-style:normal}.real-price,.goal-time{margin:6px 15px;color:#a89586;font-size:11px}.goal-time{color:#d3ae7a}.tier-badge{position:absolute;left:11px;top:11px;padding:5px 8px;border-radius:999px;background:#261d19cc;color:#f0d2aa;font-size:10px;letter-spacing:.1em}.item-art{position:relative}.reference-row{display:flex;justify-content:space-between;gap:18px;padding:10px 0;border-top:1px solid #ffffff12;color:#ab9a8e}.reference-row b{color:#e7d3bc}.reference-row.primary b{font-size:18px;color:#f1c987}.purchase-sheet .goal-time{margin:2px 0 15px}.buy-main{background:#e6c392;color:#2c211b;border:0}.home-card{padding:26px;border:1px solid #ffffff14;border-radius:18px;background:linear-gradient(135deg,#48362f,#281f1c)}
.meal-lead{align-items:flex-start}.meal-sections{flex-shrink:0}.meal-filter{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:4px 0 10px}.meal-filter button{position:relative;display:flex;flex-direction:column;align-items:center;gap:3px;min-height:72px;margin:0;padding:7px 5px;background:#2b2320;border-color:#ffffff10;color:#cbbcaf}.meal-filter button>img{width:34px;height:34px;object-fit:contain;filter:drop-shadow(0 4px 5px #120b0877)}.meal-filter button>small{position:absolute;right:6px;top:5px;color:#8f7f75;font-size:9px}.meal-filter button.active{color:#2c211b;background:#ead0ad}.meal-filter button.active small{color:#6b5140}.meal-guide{margin:12px 2px;color:#a89588;font-size:12px}.meal-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.meal-card{display:grid;grid-template-columns:128px 1fr;min-height:165px;overflow:hidden;border:1px solid #ffffff12;border-radius:16px;background:linear-gradient(135deg,#302724,#241d1a)}.meal-visual{position:relative;display:grid;place-items:center;background:radial-gradient(circle,#a5764b35,transparent 68%)}.meal-visual img{width:118px;height:118px;object-fit:contain;filter:drop-shadow(0 10px 12px #120b0877)}.meal-copy{display:flex;min-width:0;flex-direction:column;padding:14px 14px 12px 4px}.meal-copy>small{color:#c49f70;font-size:10px;letter-spacing:.12em}.meal-copy h3{margin:4px 0;font-size:16px}.meal-copy>p{display:-webkit-box;overflow:hidden;margin:2px 0 10px;color:#a9998e;font-size:11px;line-height:1.45;-webkit-line-clamp:2;-webkit-box-orient:vertical}.meal-buy{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:auto}.meal-buy>b{color:#efca92;font-size:15px;white-space:nowrap}.meal-buy>b small{font-size:9px;font-weight:400}.meal-buy button{margin:0;padding:6px 9px;font-size:11px}.daily-note{display:grid;grid-template-columns:100px 1fr;gap:18px;align-items:center;padding:18px;border:1px solid #d7b47a30;border-radius:16px;background:linear-gradient(120deg,#59403288,#2b211d)}.daily-note>span{display:grid;place-items:center;height:64px;border-right:1px solid #ffffff18;color:#edca98;font-family:Georgia,'Noto Serif SC',serif}.daily-note strong{font-size:18px}.daily-note p{margin:5px 0 0;color:#b7a69a}.daily-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:14px}.daily-card{overflow:hidden;border:1px solid #ffffff10;border-radius:14px;background:#2b2320}.daily-card>img{display:block;width:100%;height:115px;object-fit:contain;background:radial-gradient(circle,#936b4933,transparent 68%)}.daily-card>div{padding:11px}.daily-card small,.daily-card strong{display:block}.daily-card small{color:#ac8e6b;font-size:9px}.daily-card strong{margin:3px 0 10px}.daily-card button{width:100%;margin:0;padding:6px;font-size:11px}.taste-card{max-width:620px;margin:auto;padding:24px;border:1px solid #ffffff12;border-radius:18px;background:linear-gradient(140deg,#342925,#241d1a)}.taste-intro{display:flex;gap:14px;align-items:center}.taste-intro>img{width:48px;height:48px;object-fit:contain}.taste-intro h3{margin:0 0 4px;font-size:20px}.taste-intro p{margin:0;color:#ad9c90}.taste-fields{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:20px}.taste-fields label>span{font-size:12px;color:#d7c2ad}.memory-consent{display:flex;align-items:flex-start;gap:10px;margin:8px 0 18px;padding:12px;border-radius:12px;background:#ffffff08}.memory-consent input{margin-top:3px}.memory-consent b,.memory-consent small{display:block}.memory-consent small{margin-top:3px;color:#9d8c81}.taste-actions{display:flex;align-items:center;gap:12px}.taste-actions p{margin:0;color:#d7b47f}.empty-state{padding:40px;text-align:center;color:#9d8c81}.purchase-art{display:block;width:100%;height:150px;object-fit:contain;margin:0 auto 12px;border-radius:12px;background:radial-gradient(circle,#91684633,transparent 68%)}.meal-once-note{padding:10px 12px;border-left:2px solid #d4ab75;background:#ffffff08;color:#c8b7aa;font-size:12px}
.memory-page,.orders-page{display:grid;gap:16px}.memory-compose{padding:24px;border:1px solid #d4b47a2e;border-radius:18px;background:linear-gradient(135deg,#49352c,#271f1c)}.memory-compose h2{margin:5px 0 7px;font:500 23px/1.3 Georgia,'Noto Serif SC',serif}.memory-compose>div>p:last-child{max-width:560px;color:#b7a69a;line-height:1.6}.memory-compose .memory-input{min-height:110px;margin-top:18px;border-color:#d2ad7855;background:#1d1715aa}.memory-actions,.record-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.memory-actions span{margin-right:auto;color:#8f7f75;font-size:11px}.memory-toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:2px}.memory-toolbar strong{font:500 17px Georgia,'Noto Serif SC',serif}.memory-toolbar input{width:min(260px,50%);padding:9px 12px;border:1px solid #ffffff20;border-radius:999px;background:#211a18;color:#f5e8d9}.memory-list,.order-list{display:grid;gap:10px}.memory-record{margin:0;padding:18px 20px;background:linear-gradient(135deg,#302724,#28201d)}.memory-record header{display:flex;align-items:center;justify-content:space-between;gap:12px}.memory-record time{color:#a99586;font-size:11px}.memory-record header span{padding:4px 8px;border-radius:999px;background:#ffffff09;color:#9e8c80;font-size:10px}.memory-record header span.remembered{background:#d4ac7330;color:#efcc9c}.memory-record p{margin:14px 0 18px;color:#eadbce;line-height:1.75}.record-actions button{margin:0;padding:6px 10px;font-size:11px}.record-actions .recall-toggle{border-color:#d4ad7555;color:#edc792}.record-actions .danger{margin-left:auto;border-color:#a9605544;color:#d99e95;background:transparent}.order-filters{display:flex;gap:7px;overflow:auto}.order-filters button{margin:0;white-space:nowrap;border-radius:999px;background:transparent}.order-filters button.active{background:#ead0ad;color:#2b211c}.order-record{display:grid;grid-template-columns:54px 1fr auto;gap:14px;align-items:center;margin:0;padding:12px 15px}.order-art{display:grid;place-items:center;width:54px;height:54px;border-radius:12px;background:radial-gradient(circle,#956d4938,transparent 70%)}.order-art img{width:48px;height:48px;object-fit:contain}.order-record>div:nth-child(2){display:grid;gap:2px}.order-record small{color:#8f7f75;font-size:10px}.order-record strong{font-size:14px}.order-record span{color:#c4a77e;font-size:11px}.order-record>b{padding:5px 8px;border-radius:999px;font-size:10px}.state-done{background:#64845f2b;color:#b9d7b2}.state-failed{background:#a75e5428;color:#e4aaa2}.state-pending{background:#a7804928;color:#e0bd87}
@media(max-width:640px){.life-head{grid-template-columns:1fr}.wallet{min-width:0}.section-lead{align-items:stretch;flex-direction:column}.destination-grid{grid-template-columns:1fr}.vehicle-card{grid-template-columns:1fr}.vehicle-visual{min-height:180px}.garage-summary{grid-template-columns:1fr}.grid{grid-template-columns:1fr}.life nav{overflow-x:auto;flex-wrap:nowrap}.life nav button{white-space:nowrap}.meal-sections{overflow:auto}.meal-sections button{white-space:nowrap}.meal-filter{display:flex;overflow:auto}.meal-filter button{min-width:76px}.meal-grid{grid-template-columns:1fr}.daily-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.taste-fields{grid-template-columns:1fr}.daily-note{grid-template-columns:70px 1fr}.meal-card{grid-template-columns:112px 1fr}.memory-toolbar{align-items:stretch;flex-direction:column}.memory-toolbar input{width:100%;box-sizing:border-box}.order-record{grid-template-columns:48px 1fr auto}.memory-compose{padding:18px}}
.gift-reward{margin:12px 0;padding:14px;border:1px solid #d4b47a55;border-radius:12px;background:#5a403466;text-align:center}.gift-reward>strong{color:#f3cf96}.reward-numbers{display:flex;justify-content:center;gap:24px;margin:12px 0}.reward-numbers span{color:#c9b6a4}.reward-numbers b{display:block;color:#ffd79e;font-size:24px}.gift-reward p{margin:5px 0;color:#f0c48d}.gift-reward small{color:#baa796}
.return-gift{margin:12px 0;padding:12px;border-top:1px solid #d4b47a44;border-bottom:1px solid #d4b47a44}.return-gift strong{color:#f2d4a7}.return-gift p{color:#e2d2c1!important;line-height:1.7}
.item.preferred{border-color:#d4b47a88}.item.preferred:after{content:'投其所好 · 额外加成';display:block;margin:8px 15px;color:#edc992;font-size:11px}
</style>
