<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { api, type JourneyMode, type JourneyState } from '../../api/client';
import { useCharacterStore } from '../../stores/character';
import { journeyI18n } from './i18n';

const props = defineProps<{ show: boolean }>();
const characters = useCharacterStore();
const data = ref<JourneyState | null>(null);
let autonomyAttempts = 0;
let autonomyTimer = 0;
const activeTab = ref<'overview' | 'gifts' | 'story' | 'settings'>('overview');
const summary = ref('');
const newThread = ref('');
const busy = ref(false);
const error = ref('');
const confirmReset = ref(false);
const selectedGift = ref<JourneyState['gifts'][number] | null>(null);
const selectedSet = ref<JourneyState['sets'][number] | null>(null);
const detailRoot = ref<HTMLElement | null>(null);
let previousFocus: HTMLElement | null = null;
function closeDetails() { selectedGift.value = null; selectedSet.value = null; }
function onDetailKeys(event: KeyboardEvent) {
  if (!detailRoot.value) return;
  if (event.key === 'Escape') { event.preventDefault(); closeDetails(); return; }
  if (event.key !== 'Tab') return;
  const items = [...detailRoot.value.querySelectorAll<HTMLElement>('button,[href],input,textarea,select,[tabindex]:not([tabindex="-1"])')].filter(el => !el.hasAttribute('disabled'));
  if (!items.length) return;
  const first = items[0], last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}
watch(() => selectedGift.value || selectedSet.value, async current => {
  if (current) {
    previousFocus = document.activeElement as HTMLElement | null;
    await nextTick();
    detailRoot.value?.querySelector<HTMLElement>('button')?.focus();
  } else {
    document.body.style.overflow = '';
    previousFocus?.focus();
    previousFocus = null;
  }
});
watch(() => props.show, visible => {
  if (!visible) {
    closeDetails();
    document.body.style.overflow = '';
  }
});
onMounted(() => document.addEventListener('keydown', onDetailKeys));
onUnmounted(() => {
  document.removeEventListener('keydown', onDetailKeys);
  document.body.style.overflow = '';
  previousFocus?.focus();
});
const giftNames: Record<string, string> = {
  flower: '一朵小花', tea: '一杯热茶', book: '窗边读物', brush: '一支画笔',
  card: '手写卡片', album: '共同相册', wind_chime: '窗边风铃', glasses: '日常眼镜',
  hat: '出门帽子', casual_outfit: '舒适便装', coat_outfit: '暖意大衣', dress_outfit: '纪念礼服',
};
const chapters: Record<string, { name: string; note: string }> = {
  this_moment: { name: '这一刻', note: '从现在开始，把普通的日子写成我们的故事。' },
  i_remember: { name: '我记得', note: '说过的话有了下文，共同经历也开始被认真记得。' },
  our_habits: { name: '我们的习惯', note: '相处不再只是偶然，慢慢有了彼此熟悉的日常。' },
  lasting_story: { name: '长久的故事', note: '那些一起走过的时间，已经成为值得回看的篇章。' },
};
const chapter = computed(() => chapters[data.value?.chapter.id || 'this_moment']);
const giftTotal = computed(() => (data.value?.gifts || []).reduce((sum, item) => sum + item.count, 0));
const pendingCoins = computed(() => (data.value?.rewards || []).filter(row => !row.claimed && row.coin > 0).reduce((sum, row) => sum + row.coin, 0));
const latestInner = computed(() => {
  const entries = data.value?.inner_story.entries || [];
  return [...entries].reverse().find(row => row.unlocked) || entries.find(row => !row.unlocked) || null;
});
const nextUnlock = computed(() => {
  if (!data.value) return { title: '', text: '', remaining: 0, unit: '' };
  const level = data.value.ai_level.level;
  const names: Record<number, [string, string]> = {
    2: ['角色回礼', '好感进入第二阶段后，她也可能准备一份心意。'],
    3: ['偏好加倍', '投其所好，会收获更多好感与陪伴经验。'],
    4: ['套装纪念', '集齐一组心意，解锁套装金币与共同纪念。'],
    5: ['共同纪念日', '让相识的 7、30、100、365 天都有回响。'],
  };
  if (level < 5) {
    const [title, text] = names[level + 1];
    return { title, text, remaining: Math.max(0, data.value.ai_level.next_at - data.value.ai_level.xp), unit: 'XP' };
  }
  const affection = data.value.affection;
  if (affection.next_at) return { title: `关系进阶 · ${affection.stage}`, text: '继续聊天、一起活动，或送上一份心意。', remaining: affection.next_at - affection.value, unit: '点好感' };
  const anniversary = [7, 30, 100, 365, 730, 1095, 1825].find(days => days > data.value!.known_days);
  if (anniversary) return { title: `相识 ${anniversary} 天纪念`, text: '把普通的日子，慢慢过成值得纪念的一天。', remaining: anniversary - data.value.known_days, unit: '天' };
  return { title: '故事仍在继续', text: '等级不是终点，下一段共同经历还在前面。', remaining: 0, unit: '' };
});
const progress = computed(() => {
  const current = data.value?.chapter;
  if (!current) return 0;
  if (!current.next_at) return 100;
  return Math.round(100 * (current.progress - current.floor) / (current.next_at - current.floor));
});
const aiProgress = computed(() => {
  const current = data.value?.ai_level;
  return current ? Math.round(100 * (current.xp - current.floor) / (current.next_at - current.floor)) : 0;
});
const affectionProgress = computed(() => {
  const current = data.value?.affection;
  if (!current) return 0;
  if (!current.next_at) return 100;
  return Math.round(100 * (current.value - current.floor) / (current.next_at - current.floor));
});

async function load() {
  const id = characters.currentId;
  if (!id || !props.show) return;
  error.value = '';
  try {
    const row = await api.journeyState(id);
    if (characters.currentId !== id) return;
    data.value = row;
    summary.value = row.summary;
    if (row.autonomy.forming && autonomyAttempts < 3) {
      autonomyAttempts += 1;
      window.clearTimeout(autonomyTimer);
      autonomyTimer = window.setTimeout(() => { void load(); }, 1200 + autonomyAttempts * 1000);
    }
  } catch { error.value = '共同时光暂时没有加载成功。'; }
}
watch(() => [props.show, characters.currentId], () => {
  confirmReset.value = false;
  selectedGift.value = null;
  selectedSet.value = null;
  activeTab.value = 'overview';
  autonomyAttempts = 0;
  window.clearTimeout(autonomyTimer);
  void load();
}, { immediate: true });

async function changeMode(mode: JourneyMode) {
  if (!data.value || busy.value) return;
  busy.value = true;
  try { data.value = await api.journeyMode(data.value.character_id, mode); }
  catch { error.value = '模式没有保存成功。'; }
  finally { busy.value = false; }
}
async function changePath(path: 'card' | 'romance') {
  if (!data.value || busy.value) return;
  busy.value = true;
  try { data.value = await api.journeyPath(data.value.character_id, path); }
  catch { error.value = '关系表达没有保存成功。'; }
  finally { busy.value = false; }
}
async function saveSummary() {
  if (!data.value || busy.value) return;
  busy.value = true;
  try { data.value = await api.journeySummary(data.value.character_id, summary.value); }
  catch { error.value = '成长摘要没有保存成功。'; }
  finally { busy.value = false; }
}
async function addThread() {
  const text = newThread.value.trim();
  if (!text || !data.value || busy.value) return;
  busy.value = true;
  try {
    await api.journeyThread(data.value.character_id, text);
    newThread.value = '';
    await load();
  } catch { error.value = '待续话题没有保存成功。'; }
  finally { busy.value = false; }
}
async function finishThread(id: string) {
  if (!data.value) return;
  try { data.value = await api.journeyThreadDone(data.value.character_id, id); }
  catch { error.value = '这个话题暂时无法完成。'; }
}
async function removeThread(id: string) {
  if (!data.value) return;
  try {
    await api.journeyThreadDelete(data.value.character_id, id);
    await load();
  } catch { error.value = '这个话题暂时无法删除。'; }
}
async function reset() {
  if (!data.value || !confirmReset.value) return;
  busy.value = true;
  try {
    await api.journeyReset(data.value.character_id);
    confirmReset.value = false;
    summary.value = '';
    await load();
  } catch { error.value = '共同时光暂时无法重置。'; }
  finally { busy.value = false; }
}
</script>

<template>
  <section v-if="data" v-journey-i18n class="journey-book">
    <header class="journey-hero">
      <img :src="'/assets/journey/hero.jpg'" alt="" class="hero-art" />
      <div class="hero-shade" />
      <div class="hero-copy">
        <p class="hero-eyebrow">OUR SHARED TIME · CHAPTER {{ data.chapter.number }}</p>
        <h2>{{ chapter.name }}</h2>
        <p class="hero-note">{{ chapter.note }}</p>
        <div class="hero-facts"><span>相识第 {{ data.known_days }} 天</span><i /><span>{{ data.memory_count }} 段共同回忆</span><i /><span>{{ giftTotal }} 份心意</span></div>
      </div>
      <div class="hero-level"><small>AI 陪伴</small><strong>Lv.{{ data.ai_level.level }}</strong><span>{{ data.ai_level.xp }} XP</span></div>
      <div class="hero-next"><span>下一章</span><div><i :style="{width:`${progress}%`}" /></div><b v-if="data.chapter.next_at">{{ data.chapter.next_at - data.chapter.progress }}</b><b v-else>继续书写</b></div>
    </header>

    <nav class="journey-tabs" aria-label="我们的故事栏目">
      <button :class="{active:activeTab==='overview'}" @click="activeTab='overview'"><span>01</span>总览</button>
      <button :class="{active:activeTab==='gifts'}" @click="activeTab='gifts'"><span>02</span>心意</button>
      <button :class="{active:activeTab==='story'}" @click="activeTab='story'"><span>03</span>故事</button>
      <button :class="{active:activeTab==='settings'}" @click="activeTab='settings'"><span>04</span>设置</button>
    </nav>

    <div v-if="activeTab==='overview'" class="journey-page overview-page">
      <section class="growth-band">
        <div><span>AI 陪伴等级</span><strong>Lv.{{ data.ai_level.level }}</strong><div class="fine-progress"><i :style="{width:`${aiProgress}%`}" /></div><small>距离下一级 {{ data.ai_level.next_at - data.ai_level.xp }} XP</small></div>
        <div class="affection-band"><span>{{ data.affection.path==='romance' ? '恋爱好感' : '角色羁绊' }}</span><strong>{{ data.affection.stage }} <em>{{ data.affection.value }}</em></strong><div class="fine-progress"><i :style="{width:`${affectionProgress}%`}" /></div><small>{{ data.affection.next_at ? `下一阶段 ${data.affection.next_at}` : '故事仍在继续' }}</small></div>
        <div class="inner-band"><span>内心发现</span><strong>{{ data.inner_story.unlocked_count }}<em> / {{ data.inner_story.total }}</em></strong><div class="fine-progress"><i :style="{width:`${100*data.inner_story.unlocked_count/data.inner_story.total}%`}" /></div><small>每个片段都有真实经历作为来源</small></div>
      </section>

      <div class="overview-grid">
        <section class="next-unlock paper-panel">
          <p class="section-kicker">SOMETHING TO LOOK FORWARD TO</p><span class="soft-label">下一项期待</span>
          <h3>{{ nextUnlock.title }}</h3><p>{{ nextUnlock.text }}</p>
          <div v-if="nextUnlock.remaining" class="remaining"><strong>{{ nextUnlock.remaining }}</strong><span>{{ nextUnlock.unit }}，就能再近一步</span></div>
          <button @click="activeTab='gifts'">去准备一份心意</button>
        </section>
        <section v-if="latestInner" class="inner-note paper-panel" :class="{locked:!latestInner.unlocked}">
          <p class="section-kicker">A PAGE FROM HER HEART</p><span class="soft-label">时光札记</span>
          <h3>{{ latestInner.title }}</h3><p v-if="latestInner.unlocked">“{{ latestInner.text }}”</p><p v-else>内心成长达到 {{ latestInner.at }} 后，这一页会自然打开。</p>
          <span class="note-status">{{ latestInner.unlocked ? '已经发现的心里话' : '尚未发现的内心片段' }}</span>
        </section>
      </div>

      <section class="recent-rewards paper-panel">
        <div class="section-heading"><div><p class="section-kicker">RECENT KEEPSAKES</p><h3>最近收获</h3></div><span>{{ pendingCoins ? `${pendingCoins} 金币待确认` : '所有奖励永久保存' }}</span></div>
        <div v-if="data.rewards.length" class="reward-list"><article v-for="reward in data.rewards.slice(0,4)" :key="reward.id"><span class="reward-mark" /><div><strong>{{ reward.title }}</strong><p>{{ reward.text }}</p></div><b>{{ reward.coin ? `+${reward.coin} 金币` : '已解锁' }}</b></article></div>
        <div v-else class="quiet-empty"><img :src="'/assets/journey/empty-gifts.png'" alt="" /><div><strong>故事的第一页，还等着落笔</strong><p>聊一件最近在意的事，或从一份小小的心意开始。</p><button @click="activeTab='story'">留下第一件事</button></div></div>
      </section>
      <details class="inner-archive paper-panel">
        <summary><span><p class="section-kicker">PAGES OF HER HEART</p><strong>查看全部内心档案</strong></span><b>{{ data.inner_story.unlocked_count }} / {{ data.inner_story.total }}</b></summary>
        <div class="archive-pages"><article v-for="entry in data.inner_story.entries" :key="entry.id" :class="{locked:!entry.unlocked}"><span>{{ entry.unlocked ? '已发现' : `内心成长 ${entry.at}` }}</span><h4>{{ entry.title }}</h4><p>{{ entry.unlocked ? entry.text : '继续相处，等待这个片段自然显露。' }}</p></article></div>
      </details>
    </div>

    <div v-else-if="activeTab==='gifts'" class="journey-page gifts-page">
      <section class="preference-panel paper-panel">
        <div class="section-heading"><div><p class="section-kicker">HER OWN LITTLE PREFERENCES</p><h3>她最近偏爱</h3></div><span>{{ data.autonomy.error ? '这次还没想好，稍后会自己再想想' : data.autonomy.forming ? '她正在想想自己的答案' : `由她自己形成 · 第 ${data.autonomy.revision} 次内心整理` }}</span></div>
        <blockquote v-if="data.autonomy.self_note" class="self-note">“{{ data.autonomy.self_note }}”</blockquote>
        <blockquote v-else class="self-note forming">{{ data.autonomy.error ? '这次内心整理没有完成。不会用随便的标签冒充她的想法，稍后会自动重试。' : '她正在结合自己的性格与你们的相处，形成真正属于自己的偏好。' }}</blockquote>
        <div class="preference-list owned"><span v-for="item in data.preferences" :key="item.id">{{ item.name }}<i>她喜欢</i></span></div>
        <details v-if="data.autonomy.preference_reason" class="preference-reason"><summary>听她怎么说</summary><p>{{ data.autonomy.preference_reason }}</p></details>
        <div v-if="data.autonomy.current_mood || data.autonomy.personal_value" class="self-traits"><span v-if="data.autonomy.current_mood">此刻 · {{ data.autonomy.current_mood }}</span><span v-if="data.autonomy.personal_value">看重 · {{ data.autonomy.personal_value }}</span></div>
        <p class="field-hint">这些偏好由她根据人设和真实相处形成，不由用户替她选择。AI Lv.3 起，投其所好会有额外加成。</p>
      </section>

      <section class="collection-section">
        <div class="section-heading"><div><p class="section-kicker">A COLLECTION OF LITTLE STORIES</p><h3>心意套装</h3></div><span>Lv.4 解锁结算 · 可提前收集</span></div>
        <div class="set-grid"><button v-for="set in data.sets" :key="set.id" :class="{complete:set.complete&&set.unlocked}" @click="selectedSet=set"><div class="set-art"><img v-for="item in set.items" :key="item" :src="`/assets/life/${item}.png`" :alt="giftNames[item]" /></div><div class="set-title"><strong>{{ set.name }}</strong><span>{{ set.owned }}/{{ set.items.length }}</span></div><div class="fine-progress"><i :style="{width:`${100*set.owned/set.items.length}%`}" /></div><small>{{ set.complete&&set.unlocked ? `已集齐 · +${set.coin} 金币` : `集齐奖励 ${set.coin} 金币` }}</small></button></div>
      </section>

      <section v-if="data.returns.length" class="return-section paper-panel">
        <div class="section-heading"><div><p class="section-kicker">SOMETHING FOR YOU</p><h3>她给你的回礼</h3></div><span>被她认真留下的心意</span></div>
        <article v-for="item in data.returns" :key="item.id"><img :src="`/assets/life/${item.icon}.png`" :alt="item.name" /><div><strong>{{ item.name }}</strong><p>“{{ item.text }}”</p><time>{{ new Date(item.created*1000).toLocaleDateString() }}</time></div></article>
      </section>

      <section class="collection-section">
        <div class="section-heading"><div><p class="section-kicker">EVERY GIFT HAS A PLACE</p><h3>礼物图鉴</h3></div><span>{{ giftTotal }} 份心意 · {{ data.gifts.length }} 种收藏</span></div>
        <div v-if="data.gifts.length" class="gift-grid"><button v-for="gift in data.gifts" :key="gift.item_id" @click="selectedGift=gift"><span class="gift-count">×{{ gift.count }}</span><img :src="`/assets/life/${gift.item_id}.png`" :alt="gift.item_name||gift.item_id" /><strong>{{ gift.item_name||gift.item_id }}</strong><small>最近好感 +{{ gift.affection }}</small></button></div>
        <div v-else class="quiet-empty gift-empty"><img :src="'/assets/journey/empty-gifts.png'" alt="" /><div><strong>第一份心意，会有专门的位置</strong><p>首送有额外加成，礼物和回礼都会永久收藏。</p></div></div>
      </section>
    </div>

    <div v-else-if="activeTab==='story'" class="journey-page story-page">
      <section class="chapter-strip paper-panel"><p class="section-kicker">HOW FAR WE HAVE COME</p><h3>我们的共同章节</h3><div class="chapter-line"><i :style="{width:`${progress}%`}" /></div><div class="chapter-labels"><span :class="{active:data.chapter.number>=1}">这一刻</span><span :class="{active:data.chapter.number>=2}">我记得</span><span :class="{active:data.chapter.number>=3}">我们的习惯</span><span :class="{active:data.chapter.number>=4}">长久的故事</span></div></section>
      <section class="thread-section paper-panel">
        <div class="section-heading"><div><p class="section-kicker">TO BE CONTINUED</p><h3>待续的话题</h3></div><span>有下文，比记住更多事实更重要</span></div>
        <div class="thread-compose"><input v-model="newThread" maxlength="160" placeholder="例如：周五想听听她面试的结果" @keyup.enter="addThread" /><button :disabled="!newThread.trim()||busy" @click="addThread">记下</button></div>
        <article v-for="thread in data.threads" :key="thread.id" class="thread-row"><div><p>{{ thread.text }}</p><time>{{ new Date(thread.created*1000).toLocaleDateString() }}</time></div><button @click="finishThread(thread.id)">已有下文</button><button class="quiet" @click="removeThread(thread.id)">删除</button></article>
        <p v-if="!data.threads.length" class="field-hint">有明确时间安排的对话会留在这里，也可以自己添加。</p>
      </section>
      <section class="summary-section paper-panel">
        <div class="section-heading"><div><p class="section-kicker">WHERE WE ARE NOW</p><h3>关系近况</h3></div><span>可查看、修改，不作为新的人设</span></div>
        <textarea v-model="summary" maxlength="800" placeholder="例如：最近一起布置了窗边的小家；下雨时喜欢安静坐一会儿。" />
        <button :disabled="busy" @click="saveSummary">保存近况</button>
      </section>
    </div>

    <div v-else class="journey-page settings-page">
      <section class="paper-panel">
        <div class="section-heading"><div><p class="section-kicker">HOW THE STORY GROWS</p><h3>共同时光模式</h3></div><span>每个角色独立保存</span></div>
        <div class="setting-options"><button :class="{active:data.mode==='full'}" @click="changeMode('full')"><strong>完整共同时光</strong><span>全部互动成长、主动回访与自主人格</span></button><button :class="{active:data.mode==='memories'}" @click="changeMode('memories')"><strong>安静陪伴</strong><span>全部互动正常成长，不主动回访</span></button><button :class="{active:data.mode==='fixed'}" @click="changeMode('fixed')"><strong>原卡演绎</strong><span>全部互动正常成长，不改变原角色表达</span></button></div>
      </section>
      <section class="paper-panel">
        <div class="section-heading"><div><p class="section-kicker">HOW SHE RESPONDS</p><h3>关系表达</h3></div><span>好感增长，也不会丢失角色</span></div>
        <div class="setting-options two"><button :class="{active:data.affection.path==='card'}" @click="changePath('card')"><strong>遵循角色卡</strong><span>增加熟悉与默契，不改变原关系</span></button><button :class="{active:data.affection.path==='romance'}" @click="changePath('romance')"><strong>自由心动路线</strong><span>由你明确开启恋爱阶段表达</span></button></div>
      </section>
      <section class="paper-panel rules-panel">
        <div class="section-heading"><div><p class="section-kicker">FAIR BY DESIGN</p><h3>成长规则</h3></div><span>首次与多样性最划算，重复也有回报</span></div>
        <ul><li>有效聊天与舒适触碰每天各记录一次。</li><li>共同回忆每天前 {{ data.rules.memories_per_day }} 段产生成长，全部仍可永久保存。</li><li>共同活动每天前 {{ data.rules.activities_per_day }} 次产生成长，避免切换菜单刷分。</li><li>同类礼物后续经验为 {{ data.rules.gift_xp_repeat.slice(1).join(' / ') }}%，好感为 {{ data.rules.gift_affection_repeat.slice(1).join(' / ') }}%。</li><li>套装奖励始终低于收集成本，不形成无限金币循环。</li></ul>
      </section>
      <section class="paper-panel danger-zone"><div><h3>重置共同时光</h3><p>清除当前角色的章节、事件、回礼和待续话题，不删除角色卡与共同回忆。</p></div><button :disabled="busy" @click="confirmReset=true">重置</button><p v-if="confirmReset" class="reset-warning" role="alert">确定要重新开始吗？<button @click="reset">确认重置</button><button @click="confirmReset=false">取消</button></p></section>
    </div>
  </section>

  <div v-if="selectedGift||selectedSet" v-journey-i18n class="journey-detail-mask" @click.self="selectedGift=null;selectedSet=null">
    <section ref="detailRoot" class="journey-detail" role="dialog" aria-modal="true" :aria-label="selectedGift?'心意详情':'套装详情'">
      <button class="detail-close" aria-label="关闭" @click="closeDetails">×</button>
      <template v-if="selectedGift"><img class="detail-art" :src="`/assets/life/${selectedGift.item_id}.png`" :alt="selectedGift.item_name||selectedGift.item_id" /><p class="section-kicker">A GIFT REMEMBERED</p><h3>{{ selectedGift.item_name||selectedGift.item_id }}</h3><p>这份心意已经永久收进你们的故事。</p><dl><div><dt>累计送出</dt><dd>{{ selectedGift.count }} 份</dd></div><div><dt>最近好感</dt><dd>+{{ selectedGift.affection }}</dd></div><div><dt>礼物价格</dt><dd>{{ selectedGift.price }} 金币</dd></div><div><dt>最近赠送</dt><dd>{{ new Date(selectedGift.created*1000).toLocaleDateString() }}</dd></div></dl></template>
      <template v-else-if="selectedSet"><p class="section-kicker">A COMPLETE LITTLE STORY</p><h3>{{ selectedSet.name }}</h3><p>{{ selectedSet.unlocked?'集齐下列心意后，自动结算套装纪念与金币奖励。':'AI 陪伴达到 Lv.4 后解锁套装奖励结算；现在仍可提前收集。' }}</p><div class="detail-set-art"><img v-for="item in selectedSet.items" :key="item" :src="`/assets/life/${item}.png`" :alt="giftNames[item]" /></div><ul class="set-items"><li v-for="item in selectedSet.items" :key="item"><span>{{ giftNames[item]||item }}</span><b>{{ data?.gifts.some(gift=>gift.item_id===item)?'已拥有':'未收集' }}</b></li></ul><div class="set-reward">套装奖励 · {{ selectedSet.coin }} 金币</div></template>
      <button type="button" class="detail-done" @click="closeDetails">关闭</button>
    </section>
  </div>
  <p v-if="error" class="journey-error" role="alert">{{ error }}</p>
</template>

<style scoped>
.journey-book{--paper:#fffaf1;--paper-deep:#f3e8d8;--ink:#40352d;--muted:#8f7d6d;--gold:#ad7d3f;--line:#e4d6c3;color:var(--ink);font-family:Inter,'Noto Sans SC',sans-serif}.journey-book button{font:inherit}.journey-page{display:grid;gap:18px;padding-top:18px}.journey-hero{position:relative;height:248px;overflow:hidden;border-radius:20px;background:#372820;color:#fff8ec}.hero-art{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center}.hero-shade{position:absolute;inset:0;background:linear-gradient(90deg,#2a1c17f2 0%,#2a1c17d9 39%,#2a1c1740 70%,#2a1c1708 100%)}.hero-copy{position:absolute;z-index:1;left:30px;top:31px;width:63%}.hero-eyebrow,.section-kicker{margin:0;color:var(--gold);font-size:9px;font-weight:650;letter-spacing:.19em}.hero-eyebrow{color:#e0bc84}.hero-copy h2{margin:12px 0 10px;font:500 34px/1.15 Georgia,'Noto Serif SC',serif;letter-spacing:.05em}.hero-note{max-width:370px;margin:0;color:#eadac8;font:400 14px/1.8 'Noto Serif SC',serif}.hero-facts{display:flex;align-items:center;gap:9px;margin-top:23px;color:#d4c0aa;font-size:11px}.hero-facts i{width:3px;height:3px;border-radius:50%;background:#c69b62}.hero-level{position:absolute;z-index:1;right:23px;top:22px;display:grid;min-width:82px;padding:11px 12px;text-align:center;background:#2c201ac7;border:1px solid #f0d2a64d;border-radius:12px;backdrop-filter:blur(6px)}.hero-level small{color:#d6b990;font-size:9px}.hero-level strong{margin:2px 0;color:#ffe1ae;font:500 25px Georgia,serif}.hero-level span{color:#cbb79f;font-size:10px}.hero-next{position:absolute;z-index:1;left:30px;right:30px;bottom:20px;display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;color:#d5bea3;font-size:10px}.hero-next>div{height:3px;background:#ffffff26}.hero-next i{display:block;height:100%;background:#e3bd7d}.hero-next b{font-weight:500;color:#f2d4a6}.journey-tabs{display:grid;grid-template-columns:repeat(4,1fr);margin-top:16px;padding:4px;background:#e9dfd2;border-radius:12px}.journey-tabs button{margin:0;padding:10px 6px;border:0;border-radius:9px;background:transparent;color:#877466;cursor:pointer}.journey-tabs button span{margin-right:7px;color:#b09a83;font-size:9px}.journey-tabs button.active{background:#fffaf2;color:#68492f;box-shadow:0 1px 4px #59412d14}.paper-panel{padding:20px;background:var(--paper);border:1px solid var(--line);border-radius:16px}.growth-band{display:grid;grid-template-columns:repeat(3,1fr);padding:8px 0;background:var(--paper);border:1px solid var(--line);border-radius:16px}.growth-band>div{padding:14px 18px;border-right:1px solid var(--line)}.growth-band>div:last-child{border:0}.growth-band span{color:var(--muted);font-size:11px}.growth-band strong{display:block;margin:6px 0 9px;color:#6c4d31;font:500 23px Georgia,'Noto Serif SC',serif}.growth-band strong em{margin-left:5px;color:#9a8065;font:400 13px Inter,sans-serif}.growth-band small{display:block;margin-top:7px;color:#9c8b7b;font-size:10px}.affection-band strong{color:#a3605d}.inner-band strong{color:#64755c}.fine-progress{height:4px;overflow:hidden;background:#e9ddce;border-radius:4px}.fine-progress i{display:block;height:100%;background:#b88a4b;border-radius:4px}.affection-band .fine-progress i{background:#c77e79}.inner-band .fine-progress i{background:#829075}.overview-grid{display:grid;grid-template-columns:1.05fr .95fr;gap:16px}.next-unlock{position:relative;background:#f2e4cf;border-color:#dbc4a4}.soft-label{display:inline-block;margin-top:12px;color:#9a7952;font-size:11px}.next-unlock h3,.inner-note h3{margin:7px 0 10px;font:500 23px/1.3 'Noto Serif SC',serif}.next-unlock>p:not(.section-kicker),.inner-note>p:not(.section-kicker){color:#806e5d;line-height:1.75;font-size:13px}.next-unlock>button,.quiet-empty button{margin:14px 0 0;padding:8px 13px;border:1px solid #a8804d;background:#6f5033;color:#fff6e8;border-radius:8px;cursor:pointer}.remaining{display:flex;align-items:baseline;gap:9px;margin-top:15px}.remaining strong{color:#9b6832;font:500 29px Georgia,serif}.remaining span{color:#947c64;font-size:11px}.inner-note{background:#f7f2e8}.inner-note.locked{opacity:.72}.note-status{display:block;margin-top:15px;padding-top:12px;border-top:1px solid #e4d8c7;color:#a18b72;font-size:10px}.section-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;margin-bottom:15px}.section-heading h3{margin:5px 0 0;font:500 20px 'Noto Serif SC',serif}.section-heading>span{color:#9b8875;font-size:10px;text-align:right}.reward-list article{display:grid;grid-template-columns:8px 1fr auto;gap:12px;align-items:start;padding:12px 0;border-bottom:1px solid #eee2d3}.reward-list article:last-child{border:0}.reward-mark{width:5px;height:5px;margin-top:6px;border-radius:50%;background:#b98b4d}.reward-list strong{color:#66503e;font-size:13px}.reward-list p{margin:4px 0 0;color:#988572;font-size:11px;line-height:1.55}.reward-list b{color:#a47337;font-size:11px;white-space:nowrap}.quiet-empty{display:flex;align-items:center;justify-content:center;gap:20px;min-height:145px;text-align:left}.quiet-empty img{width:112px;height:112px;object-fit:contain}.quiet-empty strong{font:500 17px 'Noto Serif SC',serif;color:#715942}.quiet-empty p{margin:7px 0;color:#9a8672;font-size:12px;line-height:1.7}.preference-list{display:flex;flex-wrap:wrap;gap:8px}.preference-list button{display:flex;gap:8px;align-items:center;margin:0;padding:8px 11px;border:1px solid #ddcdb8;border-radius:999px;background:#fffdf8;color:#806c58;cursor:pointer}.preference-list button.active{background:#6d5237;border-color:#6d5237;color:#fff4e2}.preference-list button:disabled{cursor:not-allowed;opacity:.42}.preference-list button.active:disabled{opacity:1}.preference-list i{font-size:9px;font-style:normal}.field-hint{margin:12px 0 0;color:#9a8774;font-size:11px;line-height:1.65}.set-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.set-grid>button{margin:0;padding:13px;text-align:left;background:var(--paper);border:1px solid var(--line);border-radius:14px;color:var(--ink);cursor:pointer;transition:transform .16s,border-color .16s}.set-grid>button:hover{transform:translateY(-2px);border-color:#b89563}.set-grid>button.complete{border-color:#b88a4b}.set-art{display:flex;justify-content:center;align-items:center;height:76px}.set-art img{width:72px;height:72px;object-fit:contain;margin:0 -9px}.set-title{display:flex;justify-content:space-between;margin:8px 0}.set-title strong{font:500 16px 'Noto Serif SC',serif}.set-title span{color:#a67c43;font-size:11px}.set-grid small{display:block;margin-top:8px;color:#998570;font-size:10px}.return-section>article{display:flex;gap:16px;padding:12px 0;border-bottom:1px solid #eee1d0}.return-section>article:last-child{border:0}.return-section img{width:72px;height:72px;object-fit:contain}.return-section strong{font:500 16px 'Noto Serif SC',serif}.return-section p{margin:6px 0;color:#806c59;font:400 13px/1.75 'Noto Serif SC',serif}.return-section time{color:#a28f7c;font-size:10px}.gift-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.gift-grid>button{position:relative;margin:0;padding:14px 10px;background:var(--paper);border:1px solid var(--line);border-radius:14px;color:var(--ink);cursor:pointer;transition:transform .16s,border-color .16s}.gift-grid>button:hover{transform:translateY(-2px);border-color:#b89563}.gift-grid img{width:76px;height:76px;object-fit:contain}.gift-grid strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.gift-grid small{color:#a08a74;font-size:10px}.gift-count{position:absolute;right:9px;top:8px;color:#a8783e;font-size:11px}.gift-empty{background:var(--paper);border:1px solid var(--line);border-radius:16px}.chapter-strip h3{margin:7px 0 20px;font:500 21px 'Noto Serif SC',serif}.chapter-line{height:4px;background:#e6d8c6}.chapter-line i{display:block;height:100%;background:#b78a4c}.chapter-labels{display:flex;justify-content:space-between;margin-top:11px;color:#b09d88;font-size:10px}.chapter-labels span.active{color:#755532;font-weight:600}.thread-compose{display:flex;gap:8px}.thread-compose input{flex:1;min-width:0;padding:11px 13px;border:1px solid #ddcdb9;border-radius:9px;background:#fffdf8;color:#59483a}.thread-compose button,.summary-section>button{margin:0;padding:9px 16px;border:1px solid #705236;border-radius:9px;background:#705236;color:#fff5e6;cursor:pointer}.thread-row{display:grid;grid-template-columns:1fr auto auto;gap:8px;align-items:center;padding:13px 0;border-bottom:1px solid #eee2d3}.thread-row p{margin:0 0 4px;color:#695341}.thread-row time{color:#a38e77;font-size:10px}.thread-row button{margin:0;padding:6px 9px;border:1px solid #d5c2a8;border-radius:7px;background:#f7edde;color:#75583c}.thread-row .quiet{background:transparent;color:#9d8872}.summary-section textarea{box-sizing:border-box;width:100%;min-height:120px;padding:13px;resize:vertical;border:1px solid #ddcdb9;border-radius:10px;background:#fffdf8;color:#59483a;line-height:1.7}.summary-section>button{margin-top:10px}.setting-options{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.setting-options.two{grid-template-columns:repeat(2,1fr)}.setting-options button{display:grid;gap:7px;margin:0;padding:15px;text-align:left;border:1px solid #dfcfba;border-radius:11px;background:#fffdf8;color:#705a46;cursor:pointer}.setting-options button.active{border-color:#8d6841;background:#efe1cd}.setting-options strong{font:500 15px 'Noto Serif SC',serif}.setting-options span{color:#9b8670;font-size:11px;line-height:1.55}.danger-zone{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px}.danger-zone h3{margin:0 0 5px;font:500 17px 'Noto Serif SC',serif}.danger-zone p{margin:0;color:#9b8674;font-size:11px}.danger-zone>button{margin:0;padding:7px 13px;border:1px solid #c79a8d;border-radius:8px;background:transparent;color:#a26055}.reset-warning{width:100%;padding:12px;background:#f3dfd7}.reset-warning button{margin:8px 8px 0 0}.journey-detail-mask{position:fixed;z-index:120;inset:0;display:grid;place-items:center;padding:20px;background:#211812b8}.journey-detail{position:relative;width:min(420px,100%);max-height:85vh;overflow:auto;padding:26px;background:#fff9ef;border:1px solid #d8bd98;border-radius:18px;color:#493a2e}.journey-detail h3{margin:7px 0 12px;color:#735234;font:500 24px 'Noto Serif SC',serif}.journey-detail>p:not(.section-kicker){color:#8d7660;line-height:1.65}.detail-close{position:absolute;right:12px;top:10px;margin:0;padding:4px 10px;background:transparent;border:0;color:#967e65;font-size:22px}.detail-art{display:block;width:110px;height:110px;margin:0 auto 12px;object-fit:contain}.journey-detail dl>div{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid #eadccb}.journey-detail dt{color:#9a836a}.journey-detail dd{margin:0;color:#9d6f37}.set-items{padding:0;list-style:none}.set-items li{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid #eadccb}.set-items b{color:#a77b42}.set-reward{margin-top:16px;padding:12px;text-align:center;color:#8d6537;background:#efe1cd;border-radius:8px}.detail-set-art{display:flex;justify-content:center}.detail-set-art img{width:90px;height:90px;object-fit:contain;margin:0 -8px}.journey-error{color:#a65f52}.journey-book :focus-visible{outline:2px solid #a87b42;outline-offset:2px}
@media(max-width:640px){.journey-hero{height:272px}.hero-copy{left:20px;top:25px;width:76%}.hero-copy h2{font-size:28px}.hero-note{font-size:12px}.hero-level{right:14px;top:14px;min-width:68px;padding:8px}.hero-level strong{font-size:20px}.hero-facts{flex-wrap:wrap;max-width:240px;margin-top:20px}.hero-next{left:20px;right:20px}.growth-band{grid-template-columns:1fr}.growth-band>div{border-right:0;border-bottom:1px solid var(--line)}.overview-grid{grid-template-columns:1fr}.section-heading{align-items:flex-start}.section-heading>span{max-width:45%;line-height:1.5}.set-grid{grid-template-columns:repeat(2,1fr)}.gift-grid{grid-template-columns:repeat(2,1fr)}.setting-options,.setting-options.two{grid-template-columns:1fr}.paper-panel{padding:16px}.quiet-empty{gap:8px}.quiet-empty img{width:90px;height:90px}.chapter-labels{font-size:9px}.thread-row{grid-template-columns:1fr auto}.thread-row .quiet{grid-column:2}.journey-tabs button span{display:none}}
.inner-archive{padding:0;overflow:hidden}.inner-archive summary{display:flex;align-items:center;justify-content:space-between;padding:18px 20px;cursor:pointer;list-style:none}.inner-archive summary::-webkit-details-marker{display:none}.inner-archive summary strong{display:block;margin-top:5px;font:500 17px 'Noto Serif SC',serif}.inner-archive summary>b{color:#a47740;font:500 18px Georgia,serif}.archive-pages{padding:0 20px 18px}.archive-pages article{position:relative;padding:14px 14px 14px 20px;border-left:2px solid #b88a4b;background:#f6eddf}.archive-pages article+article{margin-top:9px}.archive-pages article.locked{border-left-color:#c8b9a7;opacity:.62}.archive-pages span{color:#a37a43;font-size:9px}.archive-pages h4{margin:5px 0;color:#6c523b;font:500 15px 'Noto Serif SC',serif}.archive-pages p{margin:0;color:#8d7760;font-size:12px;line-height:1.7}
@media(max-width:640px){.hero-copy{width:84%}.hero-level{display:none}}
.self-note{margin:0 0 15px;padding:4px 0 4px 16px;border-left:2px solid #b88a4b;color:#755c44;font:400 15px/1.85 'Noto Serif SC',serif}.self-note.forming{color:#9a8773}.preference-list.owned>span{display:flex;gap:8px;align-items:center;padding:8px 11px;border:1px solid #b99970;border-radius:999px;background:#efe1cd;color:#6d5035}.preference-list.owned i{font-size:9px;font-style:normal;color:#a47c4d}.preference-reason{margin-top:14px}.preference-reason summary{color:#9a7446;font-size:11px;cursor:pointer}.preference-reason p{margin:9px 0 0;padding:12px;background:#f4eadb;color:#816b55;font:400 13px/1.8 'Noto Serif SC',serif}.self-traits{display:flex;flex-wrap:wrap;gap:8px 16px;margin-top:13px;color:#92775c;font-size:11px}
.journey-page>*,.paper-panel,.section-heading>div{min-width:0;box-sizing:border-box}.section-heading>span{overflow-wrap:anywhere}.self-note,.self-traits{overflow-wrap:anywhere}
.rules-panel ul{margin:0;padding-left:18px;color:#8b745e;font-size:12px;line-height:1.9}.rules-panel li+li{margin-top:5px}
.detail-done{width:100%;margin-top:18px;padding:11px;border:1px solid #a47b48;border-radius:9px;background:#705236;color:#fff6e8;cursor:pointer}
</style>
